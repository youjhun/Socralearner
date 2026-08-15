#!/usr/bin/env python3
"""관문 판정기 — **인앱 러너를 착수해도 되는가**에 한 줄로 답한다 (유지훈 쪽에서 실행).

왜 필요한가 (2026-08-15):
관문 셋은 이미 숫자로 정해져 있다(Topdown `docs/experiments/proof-log.md` §관문). 그런데
`pilot_cohort.py`는 **이번 주 한 장**만 그린다 — "4주 연속"은 한 장으로는 절대 안 보이고,
"자립 세션 비율"은 개입 원장이 참가자 저장소에 없어서 아예 계산되지 않았다.

기준을 정해 놓고 재는 도구가 없으면, 판정은 결국 그때그때의 인상이 된다. 그리고 인상은
결과를 본 뒤에 기준을 맞추는 쪽으로 흐른다.

## 판정하는 것

  ② 파일럿 지표 — 참가자 N명, **개입 없이 시작한 세션 ≥ 70%**
  ③ 북극성    — **주간 활성 학습자 ≥ 4명이 4주 연속**

①(원가)은 여기서 판정하지 않는다. 그것은 저장소가 아니라 계산이고, 정본은 Topdown
`apps/web/src/lib/business/`다 — 같은 것을 두 번 구현하지 않는다.

## 개입 원장

`--interventions` 로 넘긴다. 이 파일은 **참가자 저장소에 없다** — 유지훈이 "내가 대신
해 준 것"을 적은 것이고, 그 사람의 저장소에 남길 성질이 아니다(proof-log §개입 원장).
없으면 ②는 `측정 불가`다. **0%로 치지 않는다** — 안 적은 것과 개입이 없었던 것은 다르고,
0으로 메우면 관문이 저절로 통과한다.

형식 (YAML 흉내지만 파서는 이 파일 안에 있다 — 의존성 0):

    P01: 2          # 그 참가자에게 개입한 세션 수 (누적)
    P02: 0

실행:
    python3 scripts/pilot_gates.py --file fleet.txt --interventions ../Topdown/docs/experiments/interventions.yaml
    python3 scripts/pilot_gates.py --central youjhun/Topdown --weeks 4
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pilot_cohort import from_central, from_repos  # noqa: E402  — 읽기 경로는 하나만 둔다

# proof-log.md §관문 (2026-08-15 고정). 여기 숫자를 고치면 그 문서도 함께 고친다.
GATE_PARTICIPANTS = 10
GATE_AUTONOMY_RATIO = 0.70
GATE_ACTIVE_LEARNERS = 4
GATE_CONSECUTIVE_WEEKS = 4

PARTICIPANT_RE = re.compile(r"^P\d{2,3}$")


def read_interventions(path):
    """`P01: 2` 줄만 읽는다. 없으면 None — **0이 아니다.**"""
    if not path:
        return None
    if not os.path.exists(path):
        print(f"  ⚠️  개입 원장이 없다: {path}", file=sys.stderr)
        return None
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            m = re.match(r"^(P\d{2,3})\s*:\s*(\d+)$", line)
            if m:
                out[m.group(1)] = int(m.group(2))
    return out


def by_week(rows):
    """주차 → {참가자: 롤업}. 같은 주차가 여러 개면 최신 생성분."""
    weeks = {}
    for r in rows:
        w, pid = r.get("week"), r.get("participant")
        if not w or not PARTICIPANT_RE.match(str(pid or "")):
            continue
        cur = weeks.setdefault(w, {}).get(pid)
        if cur is None or (r.get("generated_on") or "") >= (cur.get("generated_on") or ""):
            weeks[w][pid] = r
    return weeks


def consecutive_active(weeks, need_learners, need_weeks):
    """**연속** 주수를 센다 — 합계가 아니다.

    합계로 세면 "어느 주엔 6명, 다음 주엔 1명"이 통과한다. 관문 ③이 재려는 것은 총량이
    아니라 **끊기지 않음**이므로 최근 주차부터 거꾸로 이어지는 길이만 센다.
    """
    # 표는 **전 주차**를 담는다 — 끊긴 지점 앞을 지우면 "왜 끊겼나"를 볼 수 없다.
    detail = [
        (w, sum(1 for r in weeks[w].values() if (r.get("sessions_week") or 0) > 0))
        for w in sorted(weeks)
    ]
    run = 0
    for _, active in reversed(detail):
        if active < need_learners:
            break
        run += 1
    return run, detail


def autonomy(weeks, interventions):
    """개입 없이 시작한 세션의 비율. 원장이 없으면 None."""
    if interventions is None:
        return None, 0, 0
    total = 0
    for pid in {p for w in weeks.values() for p in w}:
        latest = max(
            (weeks[w][pid] for w in weeks if pid in weeks[w]),
            key=lambda r: r.get("generated_on") or "",
            default=None,
        )
        if latest:
            total += latest.get("sessions_total") or 0
    helped = sum(interventions.values())
    if total == 0:
        return None, 0, helped
    # 개입 수가 세션 수를 넘으면(원장 오기) 음수 비율이 나오지 않게 자른다.
    return max(0.0, (total - helped) / total), total, helped


def verdict(ok):
    return "✅ 통과" if ok else "⛔ 아직"


def main():
    ap = argparse.ArgumentParser(description="파일럿 관문 판정")
    ap.add_argument("repos", nargs="*")
    ap.add_argument("--file", help="공개 학습 저장소 목록 파일")
    ap.add_argument("--central", help="비공개 참가자의 롤업이 모이는 저장소")
    ap.add_argument("--interventions", help="개입 원장 경로 (없으면 관문 ②는 측정 불가)")
    ap.add_argument("--weeks", type=int, default=GATE_CONSECUTIVE_WEEKS)
    args = ap.parse_args()

    repos = list(args.repos)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            repos += [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not repos and not args.central:
        ap.error("저장소 목록(또는 --file)이나 --central 중 하나는 필요하다")

    rows = from_repos(repos)[0] if repos else []
    if args.central:
        rows += from_central(args.central)

    weeks = by_week(rows)
    if not weeks:
        print("읽은 롤업이 없다 — 판정할 수 없다.")
        return 1

    people = {p for w in weeks.values() for p in w}
    run, detail = consecutive_active(weeks, GATE_ACTIVE_LEARNERS, args.weeks)
    ratio, sessions, helped = autonomy(weeks, read_interventions(args.interventions))

    print("\n파일럿 관문 — 인앱 러너 착수 조건 (Topdown proof-log.md §관문)\n")

    # ② ────────────────────────────────────────────────────────────────────
    enough_people = len(people) >= GATE_PARTICIPANTS
    if ratio is None:
        gate2 = False
        line2 = "측정 불가 — 개입 원장이 없다(0%로 치지 않는다)"
    else:
        gate2 = enough_people and ratio >= GATE_AUTONOMY_RATIO
        line2 = (f"자립 {ratio:.0%} (세션 {sessions} 중 개입 {helped}) · "
                 f"참가자 {len(people)}/{GATE_PARTICIPANTS}명")
    print(f"  ② 파일럿 지표   {verdict(gate2)}  {line2}")

    # ③ ────────────────────────────────────────────────────────────────────
    gate3 = run >= args.weeks
    print(f"  ③ 북극성       {verdict(gate3)}  주간 활성 {GATE_ACTIVE_LEARNERS}명 이상이 "
          f"{run}주 연속 (필요 {args.weeks}주)")
    for w, active in detail[-args.weeks - 2:]:
        mark = "●" if active >= GATE_ACTIVE_LEARNERS else "○"
        print(f"       {mark} {w}  활성 {active}명")

    print(f"\n  ① 원가는 여기서 판정하지 않는다 — Topdown docs/business/cost-model.md")
    print(f"\n  종합: {'✅ ②③ 통과 — ①을 확인하고 착수' if gate2 and gate3 else '⛔ 아직 — 관찰을 계속한다'}")

    # 통과했을 때 0. CI에서 쓰면 "아직"이 실패로 잡히지 않게 --weeks 0으로 끌 수 있다.
    return 0 if (gate2 and gate3) else 2


if __name__ == "__main__":
    sys.exit(main())
