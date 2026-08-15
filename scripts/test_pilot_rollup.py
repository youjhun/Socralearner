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

    # Parking Lot 두 벌 — 논문 하나, 자료 하나. 항목 이름은 그 사람이 무엇을 모르는지를
    # 그대로 드러내므로 여기 심어 두고 결과 JSON에 없음을 확인한다.
    write(root, "papers/csp-2000/parking-lot.md",
          "# Parking Lot\n\n"
          "- [x] 프레셰 평균 — 해소함\n"
          "- [ ] 감각운동리듬 대역\n"
          "- <항목>\n")           # 자리표시자는 항목이 아니다
    write(root, "materials/lecture-3/parking-lot.md",
          "- [X] 공분산 추정\n- 탄젠트 공간\n")   # 체크 없는 줄도 항목이다

    # 논문 흐름 — 한 편은 완주(5/5), 한 편은 세 단계까지.
    write(root, "papers/csp-2000/meta.yaml",
          "# 논문 서지\n"
          "slug: csp-2000\ntitle: 공통공간패턴\n"
          "flow: 문제, 한계, 방법, 실험, 결과\nupdated: 2026-08-06\n")
    write(root, "papers/riemann-2017/meta.yaml",
          "slug: riemann-2017\ntitle: 감각운동리듬\n"
          "flow: 문제, 한계, 방법\nupdated: 2026-08-06\n")
    # flow가 아직 없는 논문 — 0단계로 세어야지 죽으면 안 된다.
    write(root, "papers/new-paper/meta.yaml", "slug: new-paper\nupdated: 2026-08-06\n")


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

        print("\n③-2 트랙 서랍에 든 세션도 세어진다 (2026-08-15 회귀)")
        # 인제스터는 트랙이 있으면 `daily/<track>/`에 쓴다. 여기를 flat하게 읽던 동안
        # **과목 서랍을 만든 참가자는 세션이 0으로 잡혔다** — 정리해서 공부한 사람일수록
        # 안 한 것처럼 보이는 측정이었고, 그 위에 북극성 지표가 올라가 있었다.
        nested = tempfile.mkdtemp(prefix="pilot-nested-")
        try:
            write(nested, "daily/2026-08-03-a.md", note("2026-08-03"))
            write(nested, "daily/electronics/2026-08-04-b.md", note("2026-08-04"))
            write(nested, "daily/linear-algebra/2026-08-05-c.md", note("2026-08-05"))
            n = rollup.rollup(nested, "P06", week="2026-W32", today="2026-08-07")
            check("트랙 폴더의 세션이 누적에 든다", n["sessions_total"] == 3,
                  str(n["sessions_total"]))
            check("트랙 폴더의 세션이 이번 주에도 든다", n["sessions_week"] == 3)
            check("트랙 이름은 결과에 나오지 않는다",
                  "electronics" not in json.dumps(n) and "linear-algebra" not in json.dumps(n))
            check("간격도 트랙을 가로질러 계산된다", n["session_gap_median_days"] == 1.0,
                  str(n["session_gap_median_days"]))
        finally:
            shutil.rmtree(nested, ignore_errors=True)

        print("\n③-3 논문 세션도 세션이다 (2026-08-15 감사 회귀)")
        # `[논문]` Issue는 papers/<slug>/sessions/ 로 갈라져 daily 노트를 만들지 않는다.
        # daily/만 세던 동안 **논문 트랙 참가자는 영원히 비활성**이었다.
        paper = tempfile.mkdtemp(prefix="pilot-paper-")
        try:
            write(paper, "papers/csp-2000/sessions/2026-08-03-intro.md", note("2026-08-03"))
            write(paper, "papers/csp-2000/sessions/2026-08-05-method.md", note("2026-08-05"))
            write(paper, "materials/lecture-3/sessions/2026-08-06-ch2.md", note("2026-08-06"))
            pr = rollup.rollup(paper, "P08", week="2026-W32", today="2026-08-07")
            check("논문 세션이 누적에 든다", pr["sessions_total"] == 3, str(pr["sessions_total"]))
            check("논문 세션이 이번 주에도 든다", pr["sessions_week"] == 3)
            check("논문만 읽어도 '복귀함'이 된다", pr["returned"] is True)
            check("논문 slug가 결과에 나오지 않는다", "csp-2000" not in json.dumps(pr))
        finally:
            shutil.rmtree(paper, ignore_errors=True)

        print("\n④-2 Parking Lot · 논문 흐름 (2026-08-15 두 트랙)")
        check("파킹랏 항목 4 (자리표시자 제외)", data["parking"]["items"] == 4,
              str(data["parking"]))
        check("해소 2 (대소문자 X도 해소)", data["parking"]["resolved"] == 2)
        check("파킹랏 파일 2 (papers + materials)", data["parking"]["files"] == 2)
        check("논문 3편", data["paper_flow"]["papers"] == 3, str(data["paper_flow"]))
        check("흐름 완주 1편", data["paper_flow"]["complete"] == 1)
        check("통과 단계 합 8 (5+3+0)", data["paper_flow"]["steps_total"] == 8)
        check("'문제'는 2편에서 통과", data["paper_flow"]["by_step"]["문제"] == 2)
        check("'결과'는 1편에서만", data["paper_flow"]["by_step"]["결과"] == 1)
        # 참가자 저장소에서 단독 실행되므로 import 없이 상수를 다시 적었다 — 갈리면 잡는다.
        import ingest_learning_note as ingest  # noqa: PLC0415 — 이 검사에서만 필요
        check("FLOW_STEPS가 인제스터와 같다", rollup.FLOW_STEPS == ingest.FLOW_STEPS,
              f"{rollup.FLOW_STEPS} vs {ingest.FLOW_STEPS}")

        print("\n④-3 turns 실측 · 두 트랙 완료 판정 (2026-08-15)")
        check("아무도 안 적었으면 recorded 0, 중앙값 None (0 아님)",
              data["turns"] == {"recorded": 0, "median": None, "max": None}, str(data["turns"]))
        turnsy = tempfile.mkdtemp(prefix="pilot-turns-")
        try:
            for d, t in (("2026-08-03", 12), ("2026-08-04", 20), ("2026-08-05", 44)):
                body = note(d).replace(f"created: {d}", f"created: {d}\nturns: {t}")
                write(turnsy, f"daily/{d}-x.md", body)
            write(turnsy, "daily/2026-08-06-noturns.md", note("2026-08-06"))
            t = rollup.rollup(turnsy, "P07", week="2026-W32", today="2026-08-07")["turns"]
            check("적힌 세션만 센다 (분모를 흐리지 않는다)", t["recorded"] == 3, str(t))
            check("중앙값", t["median"] == 20.0, str(t))
            # 원가는 턴 수의 제곱으로 자라므로 가장 긴 세션이 평균보다 중요하다.
            check("가장 긴 세션을 남긴다", t["max"] == 44)
        finally:
            shutil.rmtree(turnsy, ignore_errors=True)

        # 완료 판정 — 조건은 2026-08-15에 고정됐고 코드가 대신 기억한다.
        check("학습 트랙: 설명가능 1개면 미완료", data["track_learning_done"] is False)
        # 완료 조건은 **"그 논문의"** 파킹랏 절반 해소다 — 합산이면 A에서 푼 것이 B를 채운다.
        check("논문 트랙: 자료 하나가 절반 넘게 해소되면 완료",
              data["track_paper_done"] is True,
              f"flow={data['paper_flow']['complete']} best={data['parking_best_ratio']}")
        check("자료별 최고 비율이 근거로 나온다", data["parking_best_ratio"] == 0.5,
              str(data["parking_best_ratio"]))
        check("합산 비율도 남는다(밀어 두는 습관을 보는 값)",
              data["parking_resolved_ratio"] == 0.5, str(data["parking_resolved_ratio"]))
        split = rollup.track_completion(
            {"explained": 0}, {"items": 10, "resolved": 5, "best_ratio": 0.2}, {"complete": 1})
        check("합산은 절반이어도 자료별로 못 넘으면 미완료",
              split["track_paper_done"] is False, str(split))
        done = rollup.track_completion(
            {"explained": 5}, {"items": 10, "resolved": 5, "best_ratio": 0.5}, {"complete": 1})
        check("학습 트랙: 설명가능 5개면 완료", done["track_learning_done"] is True)
        half = rollup.track_completion(
            {"explained": 0}, {"items": 10, "resolved": 4, "best_ratio": 0.4}, {"complete": 1})
        check("논문 트랙: 절반 미만 해소면 미완료", half["track_paper_done"] is False)
        noflow = rollup.track_completion(
            {"explained": 0}, {"items": 2, "resolved": 2, "best_ratio": 1.0}, {"complete": 0})
        check("논문 트랙: 다섯 칸을 못 채웠으면 미완료", noflow["track_paper_done"] is False)
        empty = rollup.track_completion(
            {"explained": 0}, {"items": 0, "resolved": 0, "best_ratio": None}, {"complete": 1})
        check("파킹랏이 비었으면 0으로 나누지 않고 미완료", empty["track_paper_done"] is False)

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
