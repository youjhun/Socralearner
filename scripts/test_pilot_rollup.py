#!/usr/bin/env python3
"""pilot_rollup 회귀 테스트 — 가짜 학습 저장소를 만들어 실제로 롤업해 본다.

실행: python3 scripts/test_pilot_rollup.py

지켜야 하는 것은 둘이다.

  ① **원문이 밖으로 나가지 않는다.** 이 롤업은 남의 개인 저장소에서 돌아 유지훈에게
     간다. 개념 이름 하나만 새어도 그 사람이 무엇을 공부하는지가 드러난다. 그래서
     가짜 저장소에 표시 문자열을 심고, 결과 JSON에 **한 조각도** 없음을 확인한다.
  ② **숫자를 지어내지 않는다.** 세션이 1회면 간격 중앙값은 0이 아니라 없는 것이고,
     전이를 안 한 세션은 실패가 아니라 시도 0이다. 여기서 0으로 메우면 파일럿이
     "전이 실패율 0%"처럼 보인다.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilot_rollup as rollup  # noqa: E402

FAILED = []

# 결과에 절대 나오면 안 되는 표시 문자열 — 개념명·목표·원문·경로.
SECRETS = [
    "공통공간패턴",
    "뇌파 분류기 재현",
    "감각운동리듬",
    "내가 이해한 것은 분산의 비를 최대화한다는 것",
    "secret-lab-repo",
]


def check(name, cond, detail=""):
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def note(date, *, transfer=None, retention=None, artifact=None, weak=2):
    fm = ["---", f'title: "{date} 세션"', f"created: {date}"]
    if artifact:
        fm.append(f"artifact: {artifact}")
    fm.append("---")
    parts = fm + [
        "",
        "# 뇌파 분류기 재현",
        "",
        "## 오늘 직접 학습한 지식",
        "1. 내가 이해한 것은 분산의 비를 최대화한다는 것",
        "",
        "## 취약 영역",
    ]
    parts += [f"- 감각운동리듬 {i}" for i in range(weak)]
    if transfer:
        parts += ["", "## 전이 시도", "- 과제: 처음 보는 다른 데이터", f"- 결과: {transfer}"]
    if retention:
        parts += ["", "## 7일 재검증", "- 대상: 공통공간패턴", f"- 결과: {retention}"]
    parts += ["", "## 다음 복습 질문", "1. 왜 일반화 고유값인가", ""]
    return "\n".join(parts)


def build_repo(root):
    write(root, "daily/2026-08-03-csp.md", note("2026-08-03", transfer="통과", weak=2))
    write(root, "daily/2026-08-04-csp2.md", note("2026-08-04", retention="흐려짐", weak=3))
    write(
        root,
        "daily/2026-08-06-csp3.md",
        note("2026-08-06", transfer="실패", artifact="https://github.com/secret-lab-repo/x", weak=1),
    )
    write(root, CONCEPTS := "concepts.json", json.dumps({
        "concepts": [
            {"id": "csp", "label": "공통공간패턴", "domain": "신호처리",
             "state": "설명가능", "prereq": ["cov"], "sources": [{"file": "daily/x.md"}]},
            {"id": "cov", "label": "공분산 행렬", "domain": "선형대수",
             "state": "암기", "prereq": [], "sources": []},
            {"id": "smr", "label": "감각운동리듬", "domain": "신경공학",
             "state": "미학습", "prereq": ["csp"], "sources": []},
        ],
        "drills": [],
    }, ensure_ascii=False))
    del CONCEPTS


def main():
    root = tempfile.mkdtemp(prefix="pilot-rollup-")
    try:
        build_repo(root)
        data = rollup.rollup(root, "P03", week="2026-W32", today="2026-08-07")
        blob = json.dumps(data, ensure_ascii=False)

        print("① 원문이 새지 않는다")
        for s in SECRETS:
            check(f"'{s[:16]}…' 없음", s not in blob)
        check("저장소 경로가 없음", root not in blob)
        check("파일 경로가 없음", "daily/" not in blob, blob)
        check("`label` 키 자체가 없음", "label" not in blob)

        print("\n② 세션 지표")
        check("이번 주 세션 3", data["sessions_week"] == 3, str(data["sessions_week"]))
        check("누적 세션 3", data["sessions_total"] == 3)
        check("복귀함(2회 이상)", data["returned"] is True)
        check("첫 세션 08-03", data["first_session"] == "2026-08-03", str(data["first_session"]))
        check("마지막 세션 08-06", data["last_session"] == "2026-08-06")
        check("연속일 1 (08-06 단독)", data["streak_days"] == 1, str(data["streak_days"]))
        check("간격 중앙값 1.5일", data["session_gap_median_days"] == 1.5,
              str(data["session_gap_median_days"]))

        print("\n③ 전이·재검증·산출물")
        check("전이 시도 2", data["transfer"]["attempts"] == 2, str(data["transfer"]))
        check("전이 통과 1", data["transfer"]["passed"] == 1)
        check("전이 실패 1", data["transfer"]["failed"] == 1)
        check("전이 부분 0", data["transfer"]["partial"] == 0)
        check("재검증 1회", data["retention"]["checks"] == 1, str(data["retention"]))
        check("흐려짐 1", data["retention"]["faded"] == 1)
        check("산출물 1", data["artifacts_total"] == 1)
        check("첫 산출물 08-06", data["first_artifact"] == "2026-08-06")
        check("미해결 병목은 최근 세션 기준 1", data["open_blockers"] == 1,
              str(data["open_blockers"]))

        print("\n④ 개념 상태 분포")
        check("개념 3", data["concepts_total"] == 3)
        check("설명가능 1", data["explained"] == 1)
        check("암기 1", data["memorized"] == 1)
        check("미학습 1", data["unlearned"] == 1)
        check("선수관계 2", data["prereq_edges"] == 2, str(data["prereq_edges"]))
        check("분야 3", data["domains"] == 3, str(data["domains"]))
        check("근거 있는 개념 1", data["with_evidence"] == 1)

        print("\n⑤ 숫자를 지어내지 않는다")
        empty = tempfile.mkdtemp(prefix="pilot-empty-")
        try:
            zero = rollup.rollup(empty, "P04", week="2026-W32", today="2026-08-07")
            check("세션 0도 관측치로 남는다", zero["sessions_total"] == 0)
            check("이탈자도 롤업이 나온다", zero["participant"] == "P04")
            check("세션 0이면 간격은 None (0 아님)", zero["session_gap_median_days"] is None)
            check("세션 0이면 복귀 False", zero["returned"] is False)
            check("concepts.json 없어도 죽지 않는다", zero["concepts_total"] == 0)
            check("전이 시도 0", zero["transfer"]["attempts"] == 0)

            one = tempfile.mkdtemp(prefix="pilot-one-")
            try:
                write(one, "daily/2026-08-05-a.md", note("2026-08-05"))
                single = rollup.rollup(one, "P05", week="2026-W32", today="2026-08-07")
                check("세션 1회면 간격은 None", single["session_gap_median_days"] is None)
                check("세션 1회면 복귀 False", single["returned"] is False)
                check("전이 절이 없으면 시도 0 (실패 아님)",
                      single["transfer"]["attempts"] == 0 and single["transfer"]["failed"] == 0)
            finally:
                shutil.rmtree(one, ignore_errors=True)
        finally:
            shutil.rmtree(empty, ignore_errors=True)

        print("\n⑥ 전송 허용 키와 롤업 키가 갈라지지 않는다")
        import pilot_report_send as send  # noqa: PLC0415 — 이 검사에서만 필요

        missing = set(data) - send.ALLOWED_KEYS
        stale = send.ALLOWED_KEYS - set(data)
        check("롤업의 모든 키가 전송 허용 목록에 있다", not missing, str(sorted(missing)))
        check("전송 허용 목록에 죽은 키가 없다", not stale, str(sorted(stale)))

        print("\n⑦ 익명 ID를 강제한다")
        for bad in ("youjhun", "friend1/study", "P0", ""):
            try:
                rollup.rollup(root, bad, week="2026-W32", today="2026-08-07")
                check(f"{bad!r} 거부", False, "통과해 버렸다")
            except SystemExit:
                check(f"{bad!r} 거부", True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILED:
        print(f"❌ 실패 {len(FAILED)}: " + ", ".join(FAILED))
        return 1
    print("✅ 전부 통과 — 밖으로 나가는 것은 수치뿐이다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
