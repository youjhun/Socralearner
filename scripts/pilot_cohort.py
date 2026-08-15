#!/usr/bin/env python3
"""코호트 한 장 — 참가자들의 주간 롤업을 모아 표로 본다 (유지훈 쪽에서 실행).

왜 필요한가 (2026-08-03):
`pilot_rollup.py`가 각자의 저장소에서 수치를 만들고 `pilot-report.yml`이 내보내지만,
그것만으로는 아무도 읽지 않는다. 저장소를 하나씩 열어 JSON을 보는 것은 사람이 못 할
일이고, 안 하면 측정을 붙인 의미가 없다.

이 스크립트가 한 줄씩 답한다: **누가 돌아왔고, 누가 멈췄고, 어디서 멈췄나.**

## 두 입력 경로 (proof-system §8.1)

  · 공개(pull) — 각 저장소의 `pilot/rollup.json`을 공개 API로 읽는다.
  · 비공개(push) — 중앙 저장소에 올라온 `[롤업]` Issue를 읽는다.

둘을 섞어도 된다(일부는 공개, 일부는 비공개인 전환기가 실제로 온다).

## 읽지 못한 사람을 지우지 않는다

롤업이 없는 참가자는 표에서 빠지는 게 아니라 **`—`로 남는다.** 그만둔 사람이 조용히
사라지면 남은 사람만 보이고 완료율이 부풀려진다 — 파일럿에서 가장 알아야 할 표본이
바로 그 사람이다.

실행:
    python3 scripts/pilot_cohort.py --file fleet.txt
    python3 scripts/pilot_cohort.py --central youjhun/Topdown
    python3 scripts/pilot_cohort.py --file fleet.txt --central youjhun/Topdown --week 2026-W32
    GITHUB_TOKEN=... python3 scripts/pilot_cohort.py ...   # 비공개·한도 여유
"""
import argparse
import json
import os
import re
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_fleet import _get, fetch_file  # noqa: E402  — fleet 읽기 경로는 하나만 둔다

ROLLUP_PATH = "pilot/rollup.json"


def from_repos(repos):
    """공개 저장소들의 pilot/rollup.json. 저장소 이름은 표에 싣지 않는다."""
    out, unread = [], 0
    for repo in repos:
        try:
            raw = fetch_file(repo, ROLLUP_PATH)
        except urllib.error.HTTPError as e:
            print(f"  ⚠️  {repo} 읽기 실패 (HTTP {e.code}) — 비공개면 push 경로를 쓴다",
                  file=sys.stderr)
            unread += 1
            continue
        if raw is None:
            print(f"  ⚠️  {repo} 에 {ROLLUP_PATH} 없음 — 아직 켜지 않았거나 세션이 없다",
                  file=sys.stderr)
            unread += 1
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            print(f"  ⚠️  {repo} 의 롤업을 해석하지 못했다", file=sys.stderr)
            unread += 1
    return out, unread


def from_central(central, max_pages=10):
    """중앙 저장소의 `[롤업]` Issue 본문에 실린 JSON 블록.

    ⚠️ 2026-08-15 감사: 예전에는 **한 페이지(100건)만** 읽었다. 중앙 저장소가 개발이 활발한
    레포라 몇 주 지나면 오래된 롤업이 첫 100건 밖으로 밀려나고, 그러면 관문 ③의 주차 이력이
    **조용히 잘린다**(끊긴 게 아니라 안 보이는 것인데 끊김으로 읽힌다). GitHub `/issues`는
    PR도 함께 돌려주므로 그것도 거른다 — PR이 목록을 밀어내는 주범이다.
    """
    out = []
    for page in range(1, max_pages + 1):
        try:
            raw = _get(f"https://api.github.com/repos/{central}/issues"
                       f"?state=all&per_page=100&page={page}",
                       accept="application/vnd.github+json")
        except urllib.error.HTTPError as e:
            print(f"  ⚠️  중앙 저장소 {central} 읽기 실패 (HTTP {e.code})", file=sys.stderr)
            return out
        batch = json.loads(raw)
        if not batch:
            break
        out += _rollups_in(batch)
        if len(batch) < 100:
            break
    else:
        print(f"  ⚠️  Issue {max_pages}페이지를 다 읽었다 — 더 오래된 롤업이 남아 있을 수 있다.",
              file=sys.stderr)
    return out


def _rollups_in(issues):
    out = []
    for issue in issues:
        # PR은 Issue 목록에 섞여 오지만 롤업이 아니다.
        # 값이 아니라 **키 유무**로 본다 — 빈 객체가 오면 truthy 검사는 통과해 버린다.
        if "pull_request" in issue:
            continue
        if not (issue.get("title") or "").startswith("[롤업]"):
            continue
        m = re.search(r"```json\s*(\{.*?\})\s*```", issue.get("body") or "", re.S)
        if not m:
            continue
        try:
            out.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return out


def pick(rows, week):
    """참가자별로 요청 주차의 롤업 하나. 같은 주차가 여러 개면 최신 생성분."""
    best = {}
    for r in rows:
        if week and r.get("week") != week:
            continue
        pid = r.get("participant")
        if not pid:
            continue
        cur = best.get(pid)
        if cur is None or (r.get("generated_on") or "") >= (cur.get("generated_on") or ""):
            best[pid] = r
    return best


def fmt(v):
    return "—" if v is None else str(v)


def main():
    ap = argparse.ArgumentParser(description="파일럿 코호트 한 장")
    ap.add_argument("repos", nargs="*", help="공개 학습 저장소 owner/name 목록")
    ap.add_argument("--file", help="저장소 목록 파일 (한 줄에 하나, # 주석 허용)")
    ap.add_argument("--central", help="비공개 참가자의 롤업이 모이는 저장소 (owner/name)")
    ap.add_argument("--week", help="ISO 주차 (예: 2026-W32). 기본은 모든 주차 중 최신")
    ap.add_argument("--expect", type=int, help="코호트 인원 — 읽히지 않은 수를 함께 보고한다")
    args = ap.parse_args()

    repos = list(args.repos)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            repos += [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not repos and not args.central:
        ap.error("저장소 목록(또는 --file)이나 --central 중 하나는 필요하다")

    rows, unread = from_repos(repos) if repos else ([], 0)
    if args.central:
        rows += from_central(args.central)

    week = args.week or (max((r.get("week") or "" for r in rows), default="") or None)
    picked = pick(rows, week)

    print(f"\n파일럿 코호트 — {week or '(주차 없음)'}\n")
    if not picked:
        print("  읽은 롤업이 없다. 참가자 저장소에 PILOT_PARTICIPANT를 켰는지 확인한다.")
        return 0

    head = ("참가자", "세션", "누적", "복귀", "간격", "연속", "개념", "설명가능",
            "전이", "재검증", "산출물", "병목")
    print("  " + " ".join(h.ljust(6) for h in head))
    print("  " + "-" * (7 * len(head)))
    for pid in sorted(picked):
        r = picked[pid]
        t, ret = r.get("transfer") or {}, r.get("retention") or {}
        cells = (
            pid,
            fmt(r.get("sessions_week")),
            fmt(r.get("sessions_total")),
            "O" if r.get("returned") else "X",
            fmt(r.get("session_gap_median_days")),
            fmt(r.get("streak_days")),
            fmt(r.get("concepts_total")),
            fmt(r.get("explained")),
            f"{t.get('passed', 0)}/{t.get('attempts', 0)}",
            f"{ret.get('retained', 0)}/{ret.get('checks', 0)}",
            fmt(r.get("artifacts_total")),
            fmt(r.get("open_blockers")),
        )
        print("  " + " ".join(str(c).ljust(6) for c in cells))

    # 분모를 흐리지 않는다 — 읽히지 않은 사람도 관측치다.
    print()
    n = len(picked)
    silent = unread + (max(0, args.expect - n - unread) if args.expect else 0)
    print(f"  롤업을 읽은 참가자 {n}명" + (f" / 코호트 {args.expect}명" if args.expect else ""))
    if silent:
        print(f"  ⚠️  롤업이 없는 참가자 {silent}명 — 이들은 표에서 빠진 게 아니라 "
              "**아직 관측되지 않은 것**이다. 세션 0인지, 집계를 안 켰는지, 비공개로 "
              "바꿔 pull이 끊긴 것인지 구별해서 proof-log에 적는다.")
    active = [p for p, r in picked.items() if (r.get("sessions_week") or 0) > 0]
    print(f"  이번 주 세션이 있었던 참가자 {len(active)}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
