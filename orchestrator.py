"""
orchestrator.py — Runs the 3-layer collective analysis for a single candidate
diff: independent first pass -> cross-read & challenge -> converge & synthesize.

Also implements starvation mode: when no fresh signal has surfaced in a while,
re-examine an archived LATENT/DISCARD candidate under a rotated lens.
"""

import random
import time

from config import CONSENSUS_THRESHOLD
from models import ROSTER, call_model, parse_json_response
from prompts import (
    CORE_METHODOLOGY,
    TARGET_LENSES,
    LAYER1_TASK,
    LAYER2_TASK,
    LAYER3_TASK,
    STARVATION_PREAMBLE,
    RE_EXAMINATION_ANGLES,
    FRESH_SCAN_FOCUS_PREAMBLE,
)

# Picked ONCE per pipeline run (module import), so every candidate examined
# in this run shares the same rotating extra focus, but the NEXT run (next
# cron trigger) will very likely roll a different one. This is what makes
# repeated scans of the same target look from a different angle each time,
# rather than every run applying an identical lens.
RUN_FOCUS = random.choice(RE_EXAMINATION_ANGLES)


def _lens_for(candidate: dict) -> str:
    """Pick the target lens based on which repo/source the candidate came from,
    plus this run's rotating extra focus on top of it."""
    key = candidate.get("lens_key", "xnu")
    base_lens = TARGET_LENSES.get(key, TARGET_LENSES["xnu"])
    extra_focus = FRESH_SCAN_FOCUS_PREAMBLE.format(focus=RUN_FOCUS)
    return base_lens + "\n\n" + extra_focus


def run_layer1(candidate: dict) -> dict:
    """Each of the 6 models independently analyzes the diff. No blackboard yet."""
    lens = _lens_for(candidate)
    results = {}

    for entry in ROSTER:
        prompt = LAYER1_TASK.format(
            core=CORE_METHODOLOGY,
            lens=lens,
            repo=candidate["repo"],
            message=candidate["message"],
            description=candidate["description"],
            diff=candidate["diff"][:6000],
        )
        raw = call_model(entry, prompt)
        parsed = parse_json_response(raw)
        if parsed:
            results[entry["id"]] = parsed
        time.sleep(2)  # be polite to free-tier rate limits across 6 calls

    return results


def _format_blackboard(layer1_results: dict) -> str:
    """Render all Layer-1 outputs into a readable transcript for Layer 2."""
    lines = []
    for model_id, verdict in layer1_results.items():
        lines.append(
            f"### Analyst: {model_id}\n"
            f"Suspicious: {verdict.get('suspicious')}\n"
            f"Category: {verdict.get('category')}\n"
            f"Confidence: {verdict.get('confidence')}\n"
            f"Entry point: {verdict.get('entry_point')}\n"
            f"Sink: {verdict.get('sink')}\n"
            f"Reasoning: {verdict.get('reasoning_chain')}\n"
            f"Classification: {verdict.get('classification')}\n"
        )
    return "\n".join(lines)


def run_layer2(candidate: dict, layer1_results: dict) -> dict:
    """Each model reads everyone's Layer-1 output and strengthens/challenges/
    synthesizes/holds."""
    lens = _lens_for(candidate)
    blackboard = _format_blackboard(layer1_results)
    results = {}

    for entry in ROSTER:
        prompt = LAYER2_TASK.format(
            core=CORE_METHODOLOGY,
            lens=lens,
            repo=candidate["repo"],
            diff=candidate["diff"][:6000],
            blackboard=blackboard,
        )
        raw = call_model(entry, prompt)
        parsed = parse_json_response(raw)
        if parsed:
            results[entry["id"]] = parsed
        time.sleep(2)

    return results


def _format_full_record(layer1_results: dict, layer2_results: dict) -> str:
    """Render the complete Layer-1 + Layer-2 deliberation for Layer 3."""
    lines = ["## LAYER 1 — Independent first passes:\n"]
    lines.append(_format_blackboard(layer1_results))
    lines.append("\n## LAYER 2 — Cross-read & challenge:\n")
    for model_id, verdict in layer2_results.items():
        lines.append(
            f"### Analyst: {model_id}\n"
            f"Action: {verdict.get('action')}\n"
            f"Responding to: {verdict.get('responding_to')}\n"
            f"Suspicious: {verdict.get('suspicious')}\n"
            f"Updated reasoning: {verdict.get('updated_reasoning')}\n"
            f"Classification: {verdict.get('classification')}\n"
        )
    return "\n".join(lines)


def run_layer3(candidate: dict, layer1_results: dict, layer2_results: dict) -> dict:
    """One final synthesis pass per model; we keep all 6 final verdicts and
    let the aggregator (below) decide the collective outcome."""
    lens = _lens_for(candidate)
    full_record = _format_full_record(layer1_results, layer2_results)
    results = {}

    for entry in ROSTER:
        prompt = LAYER3_TASK.format(
            core=CORE_METHODOLOGY,
            lens=lens,
            repo=candidate["repo"],
            diff=candidate["diff"][:6000],
            full_record=full_record,
        )
        raw = call_model(entry, prompt)
        parsed = parse_json_response(raw)
        if parsed:
            results[entry["id"]] = parsed
        time.sleep(2)

    return results


def aggregate_final_verdict(layer3_results: dict) -> dict:
    """
    Collapse 6 Layer-3 syntheses into one collective outcome.
    A candidate is REPORTABLE only if at least CONSENSUS_THRESHOLD (4/6)
    models independently land on REPORTABLE after full deliberation.
    """
    reportable_votes = [v for v in layer3_results.values() if v.get("final_verdict") == "REPORTABLE"]
    latent_votes = [v for v in layer3_results.values() if v.get("final_verdict") == "LATENT"]

    if len(reportable_votes) >= CONSENSUS_THRESHOLD:
        # Pick the highest-confidence REPORTABLE hypothesis as the representative one
        best = max(reportable_votes, key=lambda v: v.get("confidence", 0))
        outcome = "REPORTABLE"
    elif len(reportable_votes) + len(latent_votes) >= CONSENSUS_THRESHOLD:
        best = max(reportable_votes + latent_votes, key=lambda v: v.get("confidence", 0))
        outcome = "LATENT"
    else:
        best = max(layer3_results.values(), key=lambda v: v.get("confidence", 0)) if layer3_results else {}
        outcome = "DISCARD"

    return {
        "collective_outcome": outcome,
        "reportable_vote_count": len(reportable_votes),
        "total_models_responded": len(layer3_results),
        "representative_hypothesis": best.get("best_hypothesis", ""),
        "representative_reasoning": best.get("why_this_won", ""),
        "next_step_for_human": best.get("next_step_for_human", ""),
        "category": best.get("category", "none"),
        "confidence": best.get("confidence", 0),
    }


def analyze_candidate(candidate: dict) -> dict:
    """Full 3-layer pipeline for one candidate. Returns the candidate enriched
    with all layer outputs and the final aggregated verdict."""
    print(f"[INFO] Layer 1 (independent) for {candidate['repo']}@{candidate.get('sha', '?')[:8]}")
    l1 = run_layer1(candidate)

    print(f"[INFO] Layer 2 (cross-read & challenge)")
    l2 = run_layer2(candidate, l1)

    print(f"[INFO] Layer 3 (converge & synthesize)")
    l3 = run_layer3(candidate, l1, l2)

    verdict = aggregate_final_verdict(l3)

    candidate["layer1"] = l1
    candidate["layer2"] = l2
    candidate["layer3"] = l3
    candidate["verdict"] = verdict
    return candidate


def run_starvation_round(archived_candidate: dict, prior_focus: str, new_focus: str) -> dict:
    """
    Re-examine an archived LATENT/DISCARD candidate under a different lens.
    Same 3-layer pipeline, but Layer 1's prompt is prefixed with the
    starvation preamble explaining the angle shift.
    """
    preamble = STARVATION_PREAMBLE.format(prior_focus=prior_focus, new_focus=new_focus)
    # Inject the preamble into the description so it flows into Layer 1's context
    enriched = dict(archived_candidate)
    enriched["description"] = preamble + "\n\n" + archived_candidate.get("description", "")
    return analyze_candidate(enriched)


def pick_next_reexamination_angle(times_reexamined: int) -> str:
    """Rotates through RE_EXAMINATION_ANGLES so repeated starvation rounds
    don't ask the same question twice in a row."""
    return RE_EXAMINATION_ANGLES[times_reexamined % len(RE_EXAMINATION_ANGLES)]
