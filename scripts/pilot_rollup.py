#!/usr/bin/env python3
"""파일럿 주간 롤업 — 내 학습 저장소에서 **수치만** 뽑는다.

왜 필요한가 (2026-08-03):
파일럿 참가자는 각자 자기 GitHub 저장소에서 공부한다. 중앙 서버도 행동 로그도 없어서,
"세팅은 했는데 안 쓰는 사람"과 "쓰다가 막힌 사람"을 구별할 방법이 없었다. 그렇다고 남의
저장소를 통째로 들여다보는 것은 이 시스템이 하려는 일의 반대다.

그래서 저장소 **안에서** 익명 수치를 계산하고, 그 수치만 밖으로 내보낸다.

## 절대 내보내지 않는 것 (계약 — test_pilot_rollup.py가 강제한다)

    노트 원문 · 개념 이름 · 목표/트랙 텍스트 · 저장소 이름 · 사용자명 · 파일 경로

개념 *이름*이 필요해지면 그때 따로 동의를 받는다. 기본값은 이름 없는 수치다.

## 계산하지 않는 것

**막힌 길목**은 여기서 세지 않는다. `concepts.json`의 선수관계에서 Topdown의
`@topdown/graph`가 이미 계산한다 — 같은 것을 파이썬으로 다시 만들면 두 숫자가 갈라진다.
여기서는 노드 수와 상태 분포까지만 싣고 해석은 Topdown에 맡긴다.

**학습 시간(분)은 셀 수 없다.** 러너는 세션이 *끝날 때* 기록하므로 시작 시각이 어디에도
없다. 대신 세션 수·간격·연속일을 센다 — 이건 커밋 시각이라는 원자료가 있다.
전체 경계는 Topdown `docs/experiments/proof-log.md` §측정 경계.

실행:
    python3 scripts/pilot_rollup.py --participant P01
    python3 scripts/pilot_rollup.py --participant P01 --week 2026-W32
    python3 scripts/pilot_rollup.py --participant P01 --out pilot/rollup.json
"""
import argparse
import datetime
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_learning_note import pop_section  # noqa: E402  — 절 추출은 하나만 둔다

DAILY_DIR = "daily"
CONCEPTS_PATH = "concepts.json"

TRANSFER_SECTION = "전이 시도"
RETENTION_SECTION = "7일 재검증"
WEAK_SECTION = "취약 영역"

# 러너가 쓰는 판정어 → 롤업 키. 여기 없는 말은 세지 않는다(조용히 통과시키지 않고 `기타`로).
TRANSFER_VERDICTS = {"통과": "passed", "부분": "partial", "실패": "failed"}
RETENTION_VERDICTS = {"유지": "retained", "흐려짐": "faded", "소실": "lost"}

# 참가자 ID 형식. 실명·저장소명이 흘러 들어가는 것을 입구에서 막는다.
PARTICIPANT_RE = re.compile(r"^P\d{2,3}$")


# --------------------------------------------------------------------------- 읽기


def session_dates(root):
    """`daily/YYYY-MM-DD-*.md` 파일명에서 세션 날짜를 뽑는다 — 파일명만 본다."""
    d = os.path.join(root, DAILY_DIR)
    if not os.path.isdir(d):
        return []
    dates = []
    for name in os.listdir(d):
        if not name.endswith(".md"):
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        if m:
            dates.append(m.group(1))
    return sorted(dates)


def read_notes(root):
    """(날짜, 본문) 목록. 본문은 여기서만 쓰이고 롤업에는 들어가지 않는다."""
    d = os.path.join(root, DAILY_DIR)
    if not os.path.isdir(d):
        return []
    notes = []
    for name in sorted(os.listdir(d)):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        if not name.endswith(".md") or not m:
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            notes.append((m.group(1), f.read()))
    return notes


def verdict_of(body, section, table):
    """`## <section>`의 `- 결과: X` 한 줄을 판정 키로 바꾼다. 절이 없으면 None."""
    _, text = pop_section(body, section)
    if not text.strip():
        return None
    m = re.search(r"^\s*[-*]?\s*결과\s*[:：]\s*(.+)$", text, re.M)
    if not m:
        return "기타"
    said = m.group(1).strip()
    for word, key in table.items():
        if word in said:
            return key
    return "기타"


def has_artifact(body):
    """frontmatter의 `artifact:` — 값이 자리표시자(<...>)면 없는 것으로 친다."""
    m = re.search(r"^artifact\s*:\s*(.+)$", body, re.M)
    if not m:
        return False
    value = m.group(1).strip()
    return bool(value) and not value.startswith("<")


def count_weak(body):
    _, text = pop_section(body, WEAK_SECTION)
    return sum(1 for l in text.splitlines() if re.match(r"^\s*[-*]\s*\S", l))


def concept_states(root):
    """concepts.json → 상태 분포. **이름은 읽지 않는다.**"""
    path = os.path.join(root, CONCEPTS_PATH)
    out = {"concepts_total": 0, "explained": 0, "memorized": 0, "unlearned": 0,
           "prereq_edges": 0, "domains": 0, "with_evidence": 0}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return out

    concepts = data.get("concepts") or []
    out["concepts_total"] = len(concepts)
    domains = set()
    for c in concepts:
        state = c.get("state") or "미학습"
        if state == "설명가능":
            out["explained"] += 1
        elif state == "암기":
            out["memorized"] += 1
        else:
            out["unlearned"] += 1
        out["prereq_edges"] += len(c.get("prereq") or [])
        if c.get("sources"):
            out["with_evidence"] += 1
        domains.add(c.get("domain") or "미분류")
    # 분야 *수*만 센다 — 분야 이름은 연구 주제를 드러낸다.
    out["domains"] = len(domains - {"미분류"})
    return out


# --------------------------------------------------------------------------- 계산


def iso_week(date_str):
    y, w, _ = datetime.date.fromisoformat(date_str).isocalendar()
    return f"{y}-W{w:02d}"


def streak_days(dates):
    """마지막 세션에서 거꾸로 이어지는 연속 학습일."""
    if not dates:
        return 0
    uniq = sorted({datetime.date.fromisoformat(d) for d in dates}, reverse=True)
    run, prev = 1, uniq[0]
    for d in uniq[1:]:
        if (prev - d).days != 1:
            break
        run, prev = run + 1, d
    return run


def gap_median(dates):
    """세션 사이 간격(일)의 중앙값. 세션이 1회 이하면 None — 0으로 속이지 않는다."""
    uniq = sorted({datetime.date.fromisoformat(d) for d in dates})
    if len(uniq) < 2:
        return None
    gaps = [(b - a).days for a, b in zip(uniq, uniq[1:])]
    return round(statistics.median(gaps), 1)


def rollup(root, participant, week=None, today=None):
    """저장소 → 익명 롤업 dict. 여기서 나온 것만 밖으로 나간다."""
    if not PARTICIPANT_RE.match(participant or ""):
        raise SystemExit(
            f"참가자 ID 형식이 아니다: {participant!r} — P01 처럼 익명 ID여야 한다. "
            "실명·저장소 이름을 쓰지 않는 것이 이 롤업의 전제다."
        )

    all_dates = session_dates(root)
    today = today or datetime.date.today().isoformat()
    week = week or iso_week(today)

    notes = read_notes(root)
    week_notes = [(d, b) for d, b in notes if iso_week(d) == week]
    week_dates = [d for d, _ in week_notes]

    transfer = {"attempts": 0, "passed": 0, "partial": 0, "failed": 0, "기타": 0}
    retention = {"checks": 0, "retained": 0, "faded": 0, "lost": 0, "기타": 0}
    artifact_dates = []

    for date, body in notes:
        t = verdict_of(body, TRANSFER_SECTION, TRANSFER_VERDICTS)
        if t:
            transfer["attempts"] += 1
            transfer[t] += 1
        r = verdict_of(body, RETENTION_SECTION, RETENTION_VERDICTS)
        if r:
            retention["checks"] += 1
            retention[r] += 1
        if has_artifact(body):
            artifact_dates.append(date)

    # 미해결 병목은 **가장 최근 세션**의 취약 영역 줄 수다(누적이 아니라 현재 상태).
    open_blockers = count_weak(notes[-1][1]) if notes else 0

    return {
        "participant": participant,
        "week": week,
        "generated_on": today,
        "schema": 1,

        "sessions_week": len(week_dates),
        "sessions_total": len(all_dates),
        "session_dates_week": week_dates,
        "first_session": all_dates[0] if all_dates else None,
        "last_session": all_dates[-1] if all_dates else None,
        "returned": len({*all_dates}) >= 2,
        "streak_days": streak_days(all_dates),
        "session_gap_median_days": gap_median(all_dates),

        "transfer": transfer,
        "retention": retention,

        "artifacts_total": len(artifact_dates),
        "first_artifact": artifact_dates[0] if artifact_dates else None,
        "open_blockers": open_blockers,

        **concept_states(root),
    }


# --------------------------------------------------------------------------- CLI


def main():
    ap = argparse.ArgumentParser(description="파일럿 주간 롤업 — 익명 수치만")
    ap.add_argument("--participant", required=True, help="익명 ID (P01 형식)")
    ap.add_argument("--week", help="ISO 주차 (예: 2026-W32). 기본은 오늘이 속한 주")
    ap.add_argument("--root", default=".", help="학습 저장소 경로")
    ap.add_argument("--today", help="오늘 날짜 고정 (테스트용)")
    ap.add_argument("--out", help="JSON을 쓸 경로. 없으면 표준출력")
    args = ap.parse_args()

    data = rollup(args.root, args.participant, args.week, args.today)
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(
            f"✅ {args.out} — {data['week']} · 세션 {data['sessions_week']}"
            f"(누적 {data['sessions_total']}) · 개념 {data['concepts_total']}"
            f"(설명가능 {data['explained']}) · 전이 {data['transfer']['passed']}/"
            f"{data['transfer']['attempts']} · 산출물 {data['artifacts_total']}"
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
