"""
pipeline.py — Entry point. Wires together:
  1. GitHub scanning (new candidates)
  2. 3-layer collective analysis (orchestrator)
  3. Findings archive (so LATENT/DISCARD candidates aren't lost)
  4. Starvation-mode trigger (re-examine archive under a new lens if no
     REPORTABLE result has surfaced in STARVATION_HOURS)

Run by GitHub Actions on a schedule. Designed to do a BOUNDED amount of work
per run (free-tier API limits), not an unbounded crawl.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from config import STARVATION_HOURS
from github_scanner import scan_all_targets
from orchestrator import analyze_candidate, run_starvation_round, pick_next_reexamination_angle, RUN_FOCUS

FINDINGS_LOG = Path("findings/findings_log.json")
ARCHIVE = Path("findings/archive.json")
META = Path("state/meta.json")


def _load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_finding(candidate: dict) -> None:
    """Append a completed analysis (with its layer1/2/3 + verdict) to the log."""
    log = _load_json(FINDINGS_LOG, [])
    entry = {
        "timestamp": _now(),
        "repo": candidate["repo"],
        "sha": candidate.get("sha"),
        "url": candidate.get("url"),
        "message": candidate.get("message"),
        "verdict": candidate["verdict"],
        "layer1": candidate["layer1"],
        "layer2": candidate["layer2"],
        "layer3": candidate["layer3"],
    }
    log.append(entry)
    _save_json(FINDINGS_LOG, log)


def _archive_for_reexamination(candidate: dict, focus_used: str) -> None:
    """Store a LATENT/DISCARD candidate so starvation mode can revisit it
    later under a different lens."""
    archive = _load_json(ARCHIVE, [])
    archive.append({
        "repo": candidate["repo"],
        "sha": candidate.get("sha"),
        "message": candidate.get("message"),
        "description": candidate.get("description"),
        "lens_key": candidate.get("lens_key"),
        "diff": candidate.get("diff"),
        "url": candidate.get("url"),
        "last_outcome": candidate["verdict"]["collective_outcome"],
        "focus_used": [focus_used],
        "times_reexamined": 0,
    })
    _save_json(ARCHIVE, archive)


def _update_archive_after_reexam(sha: str, new_outcome: str, focus_used: str) -> None:
    archive = _load_json(ARCHIVE, [])
    for item in archive:
        if item["sha"] == sha:
            item["last_outcome"] = new_outcome
            item["focus_used"].append(focus_used)
            item["times_reexamined"] += 1
    _save_json(ARCHIVE, archive)


def _hours_since_last_reportable(meta: dict) -> float:
    last = meta.get("last_reportable_at")
    if not last:
        return 999.0  # never found one -> treat as long-starved
    delta = datetime.now(timezone.utc) - datetime.fromisoformat(last)
    return delta.total_seconds() / 3600.0


def main():
    meta = _load_json(META, {"last_reportable_at": None, "last_run_at": None})

    print(f"[INFO] This run's rotating extra focus: {RUN_FOCUS}")
    print("[INFO] Scanning targets for new commits...")
    candidates = scan_all_targets()
    print(f"[INFO] {len(candidates)} fresh candidate(s) found.")

    found_reportable_this_run = False

    # --- Normal mode: analyze fresh candidates ---
    for candidate in candidates:
        result = analyze_candidate(candidate)
        outcome = result["verdict"]["collective_outcome"]
        print(f"[RESULT] {candidate['repo']}@{candidate['sha'][:8]} -> {outcome}")

        _log_finding(result)

        if outcome == "REPORTABLE":
            found_reportable_this_run = True
            meta["last_reportable_at"] = _now()
            # TODO: hook up a notification here (Telegram/email) if desired
        else:
            # LATENT or DISCARD candidates go into the archive for possible
            # future re-examination under a different lens.
            focus_used = "initial pass (target-specific lens)"
            _archive_for_reexamination(result, focus_used)

    # --- Starvation mode: no fresh candidates, or no REPORTABLE result lately ---
    starved_hours = _hours_since_last_reportable(meta)
    if not found_reportable_this_run and starved_hours >= STARVATION_HOURS:
        print(f"[INFO] {starved_hours:.1f}h since last REPORTABLE finding -> entering starvation mode.")
        archive = _load_json(ARCHIVE, [])
        # Pick a small number of archived candidates that haven't been
        # re-examined too many times yet, oldest-least-reexamined first.
        archive_sorted = sorted(archive, key=lambda x: x["times_reexamined"])
        for item in archive_sorted[:2]:  # bounded: at most 2 per run
            new_angle = pick_next_reexamination_angle(item["times_reexamined"])
            prior_focus = ", ".join(item["focus_used"])
            print(f"[INFO] Re-examining {item['repo']}@{item['sha'][:8]} with new focus: {new_angle}")

            result = run_starvation_round(item, prior_focus=prior_focus, new_focus=new_angle)
            outcome = result["verdict"]["collective_outcome"]
            print(f"[RESULT] (re-exam) {item['repo']}@{item['sha'][:8]} -> {outcome}")

            _log_finding(result)
            _update_archive_after_reexam(item["sha"], outcome, new_angle)

            if outcome == "REPORTABLE":
                meta["last_reportable_at"] = _now()
                # TODO: notification hook
    else:
        print(f"[INFO] {starved_hours:.1f}h since last REPORTABLE finding -> starvation mode not triggered yet.")

    meta["last_run_at"] = _now()
    _save_json(META, meta)
    print("[INFO] Pipeline run complete.")


if __name__ == "__main__":
    main()
