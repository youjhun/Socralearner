#!/usr/bin/env python3
"""누가 최신인가 — 쓰는 사람들의 저장소 상태를 한 번에 본다.

왜 필요한가 (2026-08-03):
자동 동기화를 붙였지만 **자동 동기화 자체는 각 저장소에 한 번 설치돼야** 돈다(닭-달걀).
그래서 "애들 각각 레포에 적용 자동으로 되는지"를 확인하려면 저장소를 하나씩 열어 봐야
했다. 사람이 못 할 일이고, 안 하면 누가 옛 버전을 쓰는지 모른 채 버그 보고가 재현되지
않는다.

이 스크립트가 공개 API로 한 줄씩 답한다:
  · `template-sync` 워크플로가 설치돼 있나
  · 엔진 파일이 템플릿과 같은가 (다르면 몇 개가 뒤처졌나)
  · 마지막으로 동기화된 것이 언제인가

읽기만 한다. 남의 저장소를 고치지 않는다.

실행:
    python3 scripts/check_fleet.py friend1/my-learning friend2/study
    python3 scripts/check_fleet.py --file fleet.txt      # 한 줄에 하나씩
    GITHUB_TOKEN=... python3 scripts/check_fleet.py ...  # 비공개 저장소·한도 여유
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

TEMPLATE = os.environ.get("TEMPLATE_REPO", "youjhun/Socralearner")

# 뒤처졌는지 판단할 엔진 파일들. 전부 볼 필요는 없다 — 이것들이 다르면 동기화가 안 된 것이다.
WATCH = (
    "scripts/build_concepts.py",
    "scripts/scan_papers.py",
    "scripts/sync_from_template.py",
    "runner/instructions.md",
)
SYNC_WORKFLOW = ".github/workflows/template-sync.yml"


def _get(url, accept="application/vnd.github.raw"):
    req = urllib.request.Request(url, headers={
        "User-Agent": "socralearner-fleet-check",
        "Accept": accept,
    })
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def fetch_file(repo, path):
    """파일 내용(bytes) 또는 None(없음). 404는 정상적인 답이다."""
    try:
        return _get(f"https://api.github.com/repos/{repo}/contents/{path}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def digest(data):
    return hashlib.sha256(data).hexdigest()[:12] if data is not None else None


def last_sync(repo):
    """가장 최근의 '템플릿 업데이트' 커밋 날짜 — 없으면 None."""
    try:
        raw = _get(f"https://api.github.com/repos/{repo}/commits?per_page=30",
                   accept="application/vnd.github+json")
    except urllib.error.HTTPError:
        return None
    for c in json.loads(raw):
        msg = (c.get("commit", {}).get("message") or "").splitlines()[0]
        if msg.startswith("템플릿 업데이트"):
            return (c["commit"]["author"]["date"] or "")[:10]
    return None


def check(repo, template_digests):
    row = {"repo": repo, "error": None, "installed": False, "stale": [], "last": None}
    try:
        row["installed"] = fetch_file(repo, SYNC_WORKFLOW) is not None
        for path, want in template_digests.items():
            got = digest(fetch_file(repo, path))
            if got != want:
                row["stale"].append(path)
        row["last"] = last_sync(repo)
    except urllib.error.HTTPError as e:
        row["error"] = f"HTTP {e.code}" + (" (비공개? 토큰이 필요할 수 있다)" if e.code in (403, 404) else "")
    except Exception as e:  # noqa: BLE001
        row["error"] = str(e)[:60]
    return row


def verdict(row):
    """한 줄 판정 — 무엇을 해 주면 되는지까지."""
    if row["error"]:
        return f"❓ 확인 불가 — {row['error']}"
    if not row["installed"]:
        return "🔴 자동 동기화 미설치 — MIGRATION.md의 파일 3개를 넣어 줘야 한다"
    if row["stale"]:
        return f"🟡 뒤처짐 {len(row['stale'])}개 — 설치는 됐다. Run workflow 한 번이면 따라온다"
    return "🟢 최신"


def main():
    ap = argparse.ArgumentParser(description="쓰는 사람들의 저장소가 최신인지 한 번에 확인")
    ap.add_argument("repos", nargs="*", help="owner/name 목록")
    ap.add_argument("--file", help="저장소 목록 파일 (한 줄에 하나, # 주석 허용)")
    args = ap.parse_args()

    repos = list(args.repos)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            repos += [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not repos:
        ap.error("확인할 저장소를 하나 이상 주세요 (또는 --file)")

    print(f"기준 템플릿: {TEMPLATE}\n")
    template_digests = {}
    for path in WATCH:
        data = fetch_file(TEMPLATE, path)
        if data is not None:
            template_digests[path] = digest(data)
    print(f"엔진 파일 {len(template_digests)}개를 기준으로 비교한다.\n")

    rows = [check(r, template_digests) for r in repos]
    width = max(len(r["repo"]) for r in rows)
    for row in rows:
        last = f"  (마지막 동기화 {row['last']})" if row["last"] else ""
        print(f"  {row['repo']:<{width}}  {verdict(row)}{last}")
        for path in row["stale"]:
            print(f"  {'':<{width}}      · {path}")

    need = [r["repo"] for r in rows if not r["error"] and not r["installed"]]
    stale = [r["repo"] for r in rows if not r["error"] and r["installed"] and r["stale"]]
    print()
    if need:
        print(f"설치가 필요한 곳 {len(need)}: " + ", ".join(need))
    if stale:
        print(f"설치는 됐지만 뒤처진 곳 {len(stale)}: " + ", ".join(stale))
        print("  → 각자 Actions → template-sync → Run workflow (또는 다음 월요일에 자동)")
    if not need and not stale and not any(r["error"] for r in rows):
        print("전부 최신이다. 👏")
    return 0


if __name__ == "__main__":
    sys.exit(main())
