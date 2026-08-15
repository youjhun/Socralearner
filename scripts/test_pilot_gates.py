#!/usr/bin/env python3
"""pilot_gates 회귀 테스트 — **관문이 저절로 통과하지 않는지** 확인한다.

실행: python3 scripts/test_pilot_gates.py

지켜야 하는 것은 둘이다.

  ① **모르는 것이 통과가 되지 않는다.** 개입 원장이 없으면 자립 비율은 0%도 100%도
     아니라 *측정 불가*이고, 측정 불가는 통과가 아니다. 여기가 무너지면 관문 전체가
     장식이 된다 — 아무것도 재지 않고 통과하니까.
  ② **연속은 합계가 아니다.** 어느 주에 6명, 다음 주에 1명은 "2주 연속"이 아니다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilot_gates as g  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


def rows(spec):
    """spec: {주차: {참가자: 이번주 세션 수}} → 롤업 행 목록."""
    out = []
    for week, people in spec.items():
        for pid, n in people.items():
            out.append({
                "participant": pid, "week": week, "generated_on": "2026-08-15",
                "sessions_week": n, "sessions_total": n * 2,
            })
    return out


def main():
    print("① 연속은 합계가 아니다")
    weeks = g.by_week(rows({
        "2026-W30": {"P01": 1, "P02": 1, "P03": 1, "P04": 1},
        "2026-W31": {"P01": 1, "P02": 0, "P03": 0, "P04": 0},   # 끊김
        "2026-W32": {"P01": 1, "P02": 1, "P03": 1, "P04": 1},
    }))
    run, detail = g.consecutive_active(weeks, 4, 4)
    check("끊긴 주 앞은 세지 않는다", run == 1, f"run={run}")
    check("주차 표는 오래된 순으로 나온다", detail[0][0] == "2026-W30", str(detail))

    unbroken = g.by_week(rows({
        f"2026-W{w}": {f"P0{i}": 1 for i in range(1, 5)} for w in (29, 30, 31, 32)
    }))
    run2, _ = g.consecutive_active(unbroken, 4, 4)
    check("끊기지 않으면 4주가 센다", run2 == 4, f"run={run2}")

    # 2026-08-15 감사 F-5: 롤업이 **아예 없는 주**를 건너뛰면 W30–W32가 "연속"이 된다.
    gap = g.by_week(rows({
        "2026-W30": {f"P0{i}": 1 for i in range(1, 5)},
        "2026-W32": {f"P0{i}": 1 for i in range(1, 5)},
    }))
    run_gap, detail_gap = g.consecutive_active(gap, 4, 4)
    check("빠진 주는 끊김으로 본다", run_gap == 1, f"run={run_gap}")
    check("빠진 주가 표에 0으로 나온다", ("2026-W31", 0) in detail_gap, str(detail_gap))

    thin = g.by_week(rows({f"2026-W{w}": {"P01": 1, "P02": 1} for w in (31, 32)}))
    run3, _ = g.consecutive_active(thin, 4, 4)
    check("활성이 기준 미만이면 0주", run3 == 0, f"run={run3}")

    print("\n② 모르는 것은 통과가 아니다")
    ratio, total, helped = g.autonomy(weeks, None)
    check("개입 원장이 없으면 None (0%도 100%도 아니다)", ratio is None)

    ratio, total, helped = g.autonomy(weeks, {"P01": 0, "P02": 0, "P03": 0, "P04": 0})
    check("개입 0이면 자립 100%", ratio == 1.0, str(ratio))

    full = {"P01": 4, "P02": 0, "P03": 0, "P04": 0}
    ratio, total, _ = g.autonomy(weeks, full)
    check("개입이 있으면 그만큼 깎인다", 0 < ratio < 1, str(ratio))

    # 원장 오기(개입 > 세션)로 음수가 나오면 표가 거짓말을 한다.
    ratio, _, _ = g.autonomy(weeks, {**full, "P01": 9999})
    check("개입 수가 세션을 넘어도 음수가 되지 않는다", ratio == 0.0, str(ratio))

    # 2026-08-15 감사 F-3: **일부만 적힌 원장은 계산하지 않는다.** 빠진 사람을 0으로 치면
    # 자립률이 위로 편향되고, 편향 방향이 하필 **관문을 여는 쪽**이다.
    ratio, _, _ = g.autonomy(weeks, {"P01": 2})
    check("한 명이라도 안 적혔으면 측정 불가", ratio is None, str(ratio))
    ratio, _, _ = g.autonomy(weeks, {**full, "P03": None})
    check("`-`로 미기록을 적어도 측정 불가", ratio is None, str(ratio))

    print("\n③ 원장 파서")
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("# 개입 원장\nP01: 2\nP02: 0   # 손 안 댐\nP03: -\n아무말\nP0: 5\n")
    try:
        led = g.read_interventions(path)
        check("P01/P02/P03만 읽는다", led == {"P01": 2, "P02": 0, "P03": None}, str(led))
        check("`-`는 미기록(None)이지 0이 아니다", led["P03"] is None and led["P02"] == 0)
        check("없는 파일은 None", g.read_interventions(path + ".nope") is None)
        check("경로가 없으면 None", g.read_interventions(None) is None)
    finally:
        os.unlink(path)

    print("\n④ 기준 숫자가 문서와 같다")
    check("참가자 10명", g.GATE_PARTICIPANTS == 10)
    check("자립 70%", g.GATE_AUTONOMY_RATIO == 0.70)
    check("주간 활성 4명", g.GATE_ACTIVE_LEARNERS == 4)
    check("4주 연속", g.GATE_CONSECUTIVE_WEEKS == 4)

    print()
    if FAILED:
        print(f"❌ 실패 {len(FAILED)}: " + ", ".join(FAILED))
        return 1
    print("✅ 전부 통과 — 관문은 재야만 열린다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
