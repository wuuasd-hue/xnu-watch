"""
github_scanner.py — Hedef repolardaki yeni commit'leri/diff'leri ceker.

State yonetimi: her repo icin "son gorulen commit SHA" state/seen.json'da
saklanir, boylece her calismada sadece YENI commit'ler islenir (tekrar
tekrar ayni seyi taramayiz, API kotasini bosa harcamayiz).
"""

import json
import os
from pathlib import Path

import requests

from config import WATCH_TARGETS, MAX_CANDIDATES_PER_RUN

GITHUB_API = "https://api.github.com"
STATE_FILE = Path("state/seen.json")


def _headers():
    token = os.environ.get("GH_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _fetch_recent_commits(repo: str, since_sha: str | None) -> list[dict]:
    """Repo icin son commit'leri ceker (en yeni 20 ile sinirli)."""
    url = f"{GITHUB_API}/repos/{repo}/commits"
    resp = requests.get(url, headers=_headers(), params={"per_page": 20}, timeout=30)
    if resp.status_code != 200:
        print(f"[WARN] {repo} commit listesi alinamadi: {resp.status_code} {resp.text[:200]}")
        return []
    commits = resp.json()
    if not since_sha:
        # Ilk calisma: sadece en yeni 5 commit'i al, gecmise bogulma
        return commits[:5]
    # since_sha'dan sonraki commit'leri filtrele
    fresh = []
    for c in commits:
        if c["sha"] == since_sha:
            break
        fresh.append(c)
    return fresh


def _fetch_commit_diff(repo: str, sha: str) -> str:
    """Tek bir commit'in diff/patch icerigini ceker."""
    url = f"{GITHUB_API}/repos/{repo}/commits/{sha}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    if resp.status_code != 200:
        return ""
    data = resp.json()
    files = data.get("files", [])
    diff_text = ""
    for f in files:
        patch = f.get("patch", "")
        if patch:
            diff_text += f"\n--- {f['filename']} ---\n{patch[:4000]}\n"  # her dosya max 4000 char
    return diff_text


def _touches_watched_path(repo_target: dict, repo: str, sha: str) -> bool:
    """Commit, config'te belirtilen path'lerden birine dokunuyor mu kontrol eder."""
    paths = repo_target.get("paths", [])
    if not paths:
        return True  # path filtresi yoksa tum repo izlenir
    url = f"{GITHUB_API}/repos/{repo}/commits/{sha}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    if resp.status_code != 200:
        return False
    files = resp.json().get("files", [])
    for f in files:
        filename = f.get("filename", "")
        if any(filename.startswith(p) for p in paths):
            return True
    return False


def scan_all_targets() -> list[dict]:
    """
    Tum hedefleri tarar, yeni ve ilgili commit'leri "aday" olarak dondurur.
    Her aday: {repo, sha, message, diff, description, url}
    """
    state = _load_state()
    candidates = []

    for target in WATCH_TARGETS:
        repo = target["repo"]
        since_sha = state.get(repo)
        commits = _fetch_recent_commits(repo, since_sha)

        if not commits:
            continue

        # State'i guncelle: en yeni commit'i kaydet
        state[repo] = commits[0]["sha"]

        for c in commits:
            sha = c["sha"]
            if not _touches_watched_path(target, repo, sha):
                continue
            diff = _fetch_commit_diff(repo, sha)
            if not diff.strip():
                continue
            candidates.append({
                "repo": repo,
                "sha": sha,
                "message": c["commit"]["message"][:300],
                "diff": diff,
                "description": target["description"],
                "lens_key": target["lens_key"],
                "url": c["html_url"],
            })
            if len(candidates) >= MAX_CANDIDATES_PER_RUN:
                break

        if len(candidates) >= MAX_CANDIDATES_PER_RUN:
            break

    _save_state(state)
    return candidates


if __name__ == "__main__":
    results = scan_all_targets()
    print(f"{len(results)} aday bulundu.")
    for r in results:
        print(f"- {r['repo']} @ {r['sha'][:8]}: {r['message'][:60]}")
