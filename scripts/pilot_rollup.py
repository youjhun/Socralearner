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
# Parking Lot과 논문 meta가 사는 두 뿌리. Topdown의 `MATERIAL_ROOTS`와 같은 값이다.
MATERIAL_ROOTS = ("papers", "materials")

# 논문 흐름 5단계 — `ingest_learning_note.FLOW_STEPS`와 같아야 한다.
# 여기서 다시 적는 이유: 이 스크립트는 참가자 저장소에서 단독 실행될 수 있고, 그때
# import가 깨지면 롤업 전체가 죽는다. 대신 아래 test가 두 값이 같은지 확인한다.
FLOW_STEPS = ("문제", "한계", "방법", "실험", "결과")

TRANSFER_SECTION = "전이 시도"
RETENTION_SECTION = "7일 재검증"
WEAK_SECTION = "취약 영역"

# 러너가 쓰는 판정어 → 롤업 키. 여기 없는 말은 세지 않는다(조용히 통과시키지 않고 `기타`로).
TRANSFER_VERDICTS = {"통과": "passed", "부분": "partial", "실패": "failed"}
RETENTION_VERDICTS = {"유지": "retained", "흐려짐": "faded", "소실": "lost"}

# 참가자 ID 형식. 실명·저장소명이 흘러 들어가는 것을 입구에서 막는다.
PARTICIPANT_RE = re.compile(r"^P\d{2,3}$")


# --------------------------------------------------------------------------- 읽기


def daily_files(root):
    """`daily/` 아래의 세션 노트 — **하위 폴더까지** 훑는다.

    ⚠️ 2026-08-15 수정. 여기는 `os.listdir`로 `daily/` 바로 밑만 봤는데, 인제스터는
    트랙이 있으면 **`daily/<track>/`에 쓴다**(`ingest_learning_note.py`의 `note_path`).
    러너는 트랙이 둘 이상이면 세션 시작에 "오늘은 어느 트랙?"을 묻는다 — 즉 **트랙을
    쓰는 것이 정상 경로**다.

    그래서 과목 서랍을 만든 참가자는 세션이 아무리 많아도 **롤업에 0으로 잡혔다.**
    공부를 정리해서 한 사람일수록 안 한 것처럼 보이는, 정확히 거꾸로 된 측정이었고,
    이 값 위에 북극성 지표(주간 활성 학습자)가 올라가 있었다.

    파일명만 본다는 성질은 그대로다 — 폴더 이름(=트랙 이름)은 읽지 않는다. 트랙 이름은
    그 사람이 무엇을 공부하는지를 드러내므로 롤업에 실리면 안 된다.
    """
    d = os.path.join(root, DAILY_DIR)
    if not os.path.isdir(d):
        return []
    out = []
    for base, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for name in sorted(files):
            m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
            if name.endswith(".md") and m:
                out.append((m.group(1), os.path.join(base, name)))
    # 날짜 우선, 같은 날짜면 경로로 — 트랙이 섞여도 순서가 흔들리지 않는다.
    return sorted(out)


def paper_session_files(root):
    """`papers|materials/<slug>/sessions/YYYY-MM-DD-*.md` — **논문 세션도 세션이다.**

    ⚠️ 2026-08-15 감사가 잡았다. `[논문]` Issue는 `build_paper_session`으로 갈라져
    `papers/<slug>/sessions/`에 쓰고 **daily 노트를 만들지 않는다**(`ingest_learning_note.py`
    main의 early return). 그런데 롤업은 `daily/`만 셌다.

    결과가 `daily/<track>/` 사고와 **같은 모양**이었다 — 그때는 과목을 정리한 사람이,
    이번엔 **논문을 읽은 사람이** 안 한 것처럼 보였다. 과제군은 학습/논문 두 트랙으로
    고정돼 있는데(proof-log §과제군) 북극성 지표는 한 트랙만 세고 있었다:
    논문 트랙 전용 참가자는 `sessions_*` 0 · `returned` false · **영원히 비활성**.

    slug(=논문 제목에서 나온다)는 읽지 않는다. 날짜만 뽑는다.
    """
    out = []
    for base in MATERIAL_ROOTS:
        d = os.path.join(root, base)
        if not os.path.isdir(d):
            continue
        for slug in sorted(os.listdir(d)):
            sdir = os.path.join(d, slug, "sessions")
            if not os.path.isdir(sdir):
                continue
            for name in sorted(os.listdir(sdir)):
                m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
                if name.endswith(".md") and m:
                    out.append((m.group(1), os.path.join(sdir, name)))
    return sorted(out)


def session_files(root):
    """세션 노트 전부 — 학습(`daily/`)과 논문(`<root>/<slug>/sessions/`) 양쪽."""
    return sorted(daily_files(root) + paper_session_files(root))


def session_dates(root):
    """세션 날짜 목록 — 파일명에서만 뽑는다. **두 트랙을 모두 센다.**"""
    return [date for date, _ in session_files(root)]


def read_notes(root):
    """(날짜, 본문) 목록. 본문은 여기서만 쓰이고 롤업에는 들어가지 않는다.

    두 트랙의 세션 원문을 모두 읽는다 — `turns:`·전이·재검증은 논문 세션에도 적힌다.
    """
    notes = []
    for date, path in session_files(root):
        with open(path, encoding="utf-8") as f:
            notes.append((date, f.read()))
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


def turns_of(body):
    """frontmatter의 `turns:` — 이 세션의 대화 왕복 수. 없으면 None(0이 아니다).

    왜 세나 (2026-08-15): 학습자 1명 월 LLM 원가 추정에서 **가장 큰 불확실성**이 이 값이다
    (Topdown `docs/business/cost-model.md` §7). 대화형 러너는 매 턴 이력 전체를 다시
    보내므로 입력 토큰이 턴 수의 **제곱**으로 자란다 — 20턴 가정이 실제로 40턴이면 원가는
    2배가 아니라 약 4배다.

    없으면 0이 아니라 None인 이유는 이 파일의 다른 값과 같다 — 안 적힌 것과 0은 다르고,
    0으로 메우면 "짧은 세션"이 실제보다 많아 보인다(그러면 원가를 낙관하게 된다).
    """
    m = re.search(r"^turns\s*:\s*(\d{1,3})\s*$", body, re.M)
    return int(m.group(1)) if m else None


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


def parking(root):
    """Parking Lot — **몇 개를 밀어 뒀고 몇 개를 풀었나.** 항목 이름은 읽지 않는다.

    왜 이 지표인가 (2026-08-15, 논문 트랙 완료 조건 ②): "모르는 것을 그냥 넘겼는가"를
    사람 판정 없이 잴 수 있는 **유일한** 지표다. 넘기는 사람은 두 모습으로 나타난다 —
    아예 안 적거나(목록이 빔), 적기만 하고 안 푼다(쌓이기만 함). 둘 다 파일만 세면 나온다.
    게다가 이것은 학습자가 **스스로 적은 빚**이라 잘 보이려고 꾸밀 이유가 없다.

    항목 이름은 그 사람이 무엇을 모르는지를 그대로 드러내므로 **수만 내보낸다.**
    """
    out = {"items": 0, "resolved": 0, "files": 0, "best_ratio": None}
    ratios = []
    for base in MATERIAL_ROOTS:
        d = os.path.join(root, base)
        if not os.path.isdir(d):
            continue
        for slug in sorted(os.listdir(d)):
            path = os.path.join(d, slug, "parking-lot.md")
            if not os.path.isfile(path):
                continue
            out["files"] += 1
            items = resolved = 0
            with open(path, encoding="utf-8") as f:
                for line in f:
                    # Topdown `parkingLot.ts`의 `parseLine`과 같은 규칙 — 글머리표 뒤에
                    # 공백이 있어야 하고, `- <항목>` 자리표시자는 항목이 아니다.
                    m = re.match(r"^\s*[-*]\s+(?:\[([ xX])\]\s*)?(.+?)\s*$", line)
                    if not m or m.group(2).startswith("<"):
                        continue
                    items += 1
                    if (m.group(1) or "").lower() == "x":
                        resolved += 1
            out["items"] += items
            out["resolved"] += resolved
            if items:
                ratios.append(resolved / items)

    # ⚠️ 2026-08-15 감사 지적: 완료 조건은 **"그 논문의"** Parking Lot 절반 이상 해소다
    # (proof-log §과제군). 전부 합쳐 나누면 **A 논문에서 푼 항목이 B 논문의 완료 조건을
    # 채운다.** 그래서 자료별 비율을 따로 내고 **가장 높은 것**을 완료 판정에 쓴다 —
    # "적어도 한 편은 절반 넘게 풀었나"가 그 조건의 뜻이기 때문이다.
    # 합계(`items`/`resolved`)는 "얼마나 밀어 두고 얼마나 푸는 사람인가"를 보는 값으로 남긴다.
    out["best_ratio"] = round(max(ratios), 2) if ratios else None
    return out


def paper_flow(root):
    """논문 흐름 5단계 — 몇 편에서 어느 단계까지 통과했나. **제목·slug는 읽지 않는다.**

    `understanding`의 4단계는 어디서 막혔는지를 뭉갠다(방법은 알고 실험 설계를 못 읽는
    사람과 그 반대가 같은 「부분 이해」다). 다섯 칸으로 세면 **사람마다 다른 구멍**이
    보이고, 그것이 다음 개선의 재료다.

    `complete`(5/5)가 논문 트랙 완료 조건 ①이다.
    """
    out = {"papers": 0, "complete": 0, "steps_total": 0,
           "by_step": {step: 0 for step in FLOW_STEPS}}
    # 두 뿌리를 다 본다 — 앱에서 종류를 「자료」로 고르면 논문도 `materials/<slug>/`에
    # 앉는다(2026-08-15 감사). `papers/`만 보면 그 사람의 flow가 영원히 0이고,
    # 논문 트랙 완료 판정이 영원히 false가 된다.
    metas = []
    for base in MATERIAL_ROOTS:
        d = os.path.join(root, base)
        if os.path.isdir(d):
            metas += [os.path.join(d, s, "meta.yaml") for s in sorted(os.listdir(d))]
    for path in metas:
        if not os.path.isfile(path):
            continue
        out["papers"] += 1
        steps = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    continue
                key, sep, value = line.partition(":")
                if sep and key.strip() == "flow":
                    steps = {w.strip() for w in re.split(r"[,·/]|\s+", value)} & set(FLOW_STEPS)
                    break
        for step in steps:
            out["by_step"][step] += 1
        out["steps_total"] += len(steps)
        if len(steps) == len(FLOW_STEPS):
            out["complete"] += 1
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


def turns_summary(counts):
    """대화 왕복 수의 요약. **적힌 세션만** 센다 — 분모를 흐리지 않는다.

    `recorded`가 `sessions_total`보다 작으면 아직 이행 중이라는 뜻이고, 그 사실이 보여야
    "평균 18턴"을 얼마나 믿을지 사람이 판단할 수 있다.
    """
    if not counts:
        return {"recorded": 0, "median": None, "max": None}
    return {
        "recorded": len(counts),
        "median": round(statistics.median(counts), 1),
        # 원가는 제곱으로 자라므로 **가장 긴 세션**이 평균보다 중요하다.
        "max": max(counts),
    }


# 파일럿 두 트랙의 완료 조건 (Topdown `docs/experiments/proof-log.md` §과제군, 2026-08-15 고정)
LEARNING_TRACK_CONCEPTS = 5      # 개념 5개를 자료 없이 설명
PAPER_TRACK_PARKING_RATIO = 0.5  # 밀어 둔 것의 절반 이상 해소


def track_completion(states, park, flow):
    """**완료했는가**를 롤업이 직접 답한다 — 원자료만 던지지 않는다.

    왜 여기서 판정하나: 조건을 사람이 매번 머리로 맞추면 주마다 다르게 센다. 조건은
    2026-08-15에 고정됐고(주제는 자유, 크기와 완료 기준만 통일), 그 판정을 코드에 두면
    "이번 주엔 좀 후하게 봤다"가 불가능해진다.

    두 트랙 모두 **노트를 썼는가**를 완료로 치지 않는다 — AI가 대신 써 준 것이 완료로
    잡히면 학습이 일어났는지 알 수 없다(`proof-system.md` §3).
    """
    # **자료 하나 기준**으로 본다 — 합산 비율을 쓰면 A 논문에서 푼 것이 B 논문의 조건을 채운다.
    best = park.get("best_ratio")
    pooled = (park["resolved"] / park["items"]) if park["items"] else 0.0
    return {
        "track_learning_done": states["explained"] >= LEARNING_TRACK_CONCEPTS,
        "track_paper_done": flow["complete"] >= 1 and (best or 0.0) >= PAPER_TRACK_PARKING_RATIO,
        # 판정의 근거를 함께 싣는다 — 참/거짓만 보내면 왜 아닌지 물어보러 와야 한다.
        "parking_best_ratio": best,
        "parking_resolved_ratio": round(pooled, 2),
    }


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
    turn_counts = []

    for date, body in notes:
        t_n = turns_of(body)
        if t_n is not None:
            turn_counts.append(t_n)
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
        # 3 = turns 실측 · 두 트랙 완료 판정 추가 · daily 하위 폴더 집계 수정 (2026-08-15)
        "schema": 3,

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

        "parking": parking(root),
        "paper_flow": paper_flow(root),
        "turns": turns_summary(turn_counts),

        **concept_states(root),
        **track_completion(concept_states(root), parking(root), paper_flow(root)),
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
            f" · 파킹랏 {data['parking']['resolved']}/{data['parking']['items']} 해소"
            f" · 논문흐름 완주 {data['paper_flow']['complete']}/{data['paper_flow']['papers']}"
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
