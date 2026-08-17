#!/usr/bin/env python3
"""ingest_learning_note 회귀 테스트 — 파일럿 증거 필드가 노트까지 살아남는가.

실행: python3 scripts/test_ingest_learning_note.py

이 테스트가 지키는 것 (2026-08-03 파일럿 계약):
  ① `artifact:` 지시행이 frontmatter로 올라가고 본문에서는 사라진다
     — `time_to_first_artifact`의 유일한 원자료라, 본문에 묻히면 셀 수 없다.
  ② `## 전이 시도` · `## 7일 재검증`이 **손대지 않은 채** daily 노트에 남는다
     — 수집기가 이 절들을 모르므로 통과만 하면 된다. 그 "모름"을 못박아 둔다.
  ④ `## 취약 영역` · `## 다음 복습 질문`이 **STATUS.md로 승격된다** (2026-08-04)
     — 러너의 노트 서식에는 `### 오늘 할 것`밖에 없어서 STATUS의 나머지 세 절이
     영영 자리표시자로 남아 있었다. 모델에게 같은 내용을 두 번 쓰게 하는 대신
     CI가 노트에서 유도한다. 러너가 직접 쓴 절은 덮지 않는다.

  ③ 두 절이 **없어도 경고가 뜨지 않는다** — 안 한 전이는 안 한 것이지 결함이 아니다.
     여기서 자동 보정이 끼면 매 세션 잔소리가 붙고, 그러면 사람이 형식을 버린다.
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_learning_note as ingest  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


BODY_FULL = """artifact: https://github.com/me/study/blob/main/fourier.ipynb

## 목표
- 위상 이동을 복소평면 회전으로 설명하기

## 오늘 직접 학습한 지식
1. 위상 이동은 복소지수의 회전이다

## 취약 영역
- 음의 주파수

## 전이 시도
- 과제: 처음 보는 구형파에서 위상 이동 방향 추론
- 결과: 통과

## 7일 재검증
- 대상: 컨볼루션 정리
- 결과: 흐려짐

## 다음 복습 질문
1. 왜 곱셈이 회전인가

## 현재 이해 수준
- 회전으로는 설명하는데 음의 주파수는 아직 손이 안 간다

## 미해결 질문
- 실신호에서 음의 주파수가 물리적으로 무엇인가
"""

BODY_MINIMAL = """## 목표
- 기초 잡기

## 오늘 직접 학습한 지식
1. 사인파의 정의

## 취약 영역
- 아직 없음

## 다음 복습 질문
1. 진폭이란

## 현재 이해 수준
- 사인파를 식으로는 적는다

## 미해결 질문
- 위상이 왜 필요한가
"""


def payload(body, number=7):
    return {
        "number": number,
        "title": "[학습] 2026-08-03 fourier-phase — 위상 이해",
        "body": body,
        "comments": [],
    }


def main():
    print("파일럿 증거 필드")

    note = ingest.build_note(payload(BODY_FULL), "2026-08-03")
    content = note["content"]
    head, _, rest = content.partition("---\n")
    frontmatter, _, body = rest.partition("\n---")

    # ① artifact 지시행
    check(
        "artifact가 frontmatter에 올라간다",
        "artifact: https://github.com/me/study/blob/main/fourier.ipynb" in frontmatter,
        frontmatter,
    )
    check(
        "artifact 지시행이 본문에는 남지 않는다",
        not body.lstrip().startswith("artifact:"),
        body[:80],
    )

    # ② 두 절이 원문 그대로 살아남는다
    check("`## 전이 시도` 절이 노트에 남는다", "## 전이 시도" in body)
    check("전이 결과 줄이 그대로 남는다", "- 결과: 통과" in body)
    check("`## 7일 재검증` 절이 노트에 남는다", "## 7일 재검증" in body)
    check("재검증 결과 줄이 그대로 남는다", "- 결과: 흐려짐" in body)
    check(
        "전이 과제 원문이 요약되지 않는다",
        "처음 보는 구형파에서 위상 이동 방향 추론" in body,
    )

    # 기존 계약이 깨지지 않았는가 (회귀)
    check("정규 헤딩이 있으면 자동 보정이 없다", note["missing"] == [], str(note["missing"]))
    check("slug가 제목에서 나온다", note["slug"] == "fourier-phase", note["slug"])
    check("날짜가 제목에서 나온다", note["date"] == "2026-08-03", note["date"])

    # ③ 없어도 조용하다
    print("\n전이·재검증이 없는 세션")
    bare = ingest.build_note(payload(BODY_MINIMAL, number=8), "2026-08-03")
    check("자동 보정 경고가 없다", bare["missing"] == [], str(bare["missing"]))
    check("전이 절을 만들어 넣지 않는다", "전이 시도" not in bare["content"])
    check("재검증 절을 만들어 넣지 않는다", "7일 재검증" not in bare["content"])
    check(
        "artifact가 없으면 frontmatter에 키가 생기지 않는다",
        "artifact:" not in bare["content"],
    )

    # ④ STATUS 승격
    print("\nSTATUS 승격 (노트 → STATUS.md)")
    derived = ingest.build_note(payload(BODY_FULL, number=9), "2026-08-03")["status_patch"]
    check("취약 영역이 '지금 약한 것'으로 승격된다", "음의 주파수" in derived.get("지금 약한 것", ""))
    check("다음 복습 질문이 승격된다", "왜 곱셈이 회전인가" in derived.get("다음 복습 질문", ""))
    check(
        "승격된 항목은 번호 목록이 된다",
        derived.get("지금 약한 것", "").startswith("1. "),
        derived.get("지금 약한 것", ""),
    )

    RUNNER_WROTE = BODY_FULL + """
## STATUS 갱신
### 지금 약한 것
1. 러너가 직접 고른 약점
"""
    kept = ingest.build_note(payload(RUNNER_WROTE, number=10), "2026-08-03")["status_patch"]
    check(
        "러너가 직접 쓴 절은 덮어쓰지 않는다",
        kept.get("지금 약한 것", "").strip() == "1. 러너가 직접 고른 약점",
        kept.get("지금 약한 것", ""),
    )

    # 자동 보정된 자리표시자가 승격되면 "약점 없음"이 약점으로 쌓인다.
    placeholder = ingest.build_note(payload(BODY_MINIMAL, number=11), "2026-08-03")["status_patch"]
    check(
        "자동 보정 자리표시자는 승격하지 않는다",
        "이번 세션 기록 없음" not in "".join(placeholder.values()),
        str(placeholder),
    )

    # ⑤ 논문 세션 (`[논문]`) — 2026-08-04에 열린 경로
    print("\n논문 세션")
    PAPER_BODY = """runner: paper-gpt

## 내가 설명한 것
- temporal variability는 시행 간 상관의 낮음이다

## 정제본 갱신
### Methods
- 시행 간 상관의 낮음으로 정의 (p.4)

## 주석
> "we define temporal variability as ..." (p.4)

## READING_STATUS 갱신
### Progress
- Methods 완료
"""
    paper = ingest.build_paper_session(
        {"number": 42, "title": "[논문] eeg-variability-mi-bci — Methods", "body": PAPER_BODY,
         "comments": []},
        "2026-08-04",
    )
    check("논문 slug가 제목에서 나온다", paper["slug"] == "eeg-variability-mi-bci", paper["slug"])
    check("섹션 이름이 제목 뒤쪽에서 나온다", paper["section"] == "Methods", paper["section"])
    check("정제본 갱신이 paper.md로 간다", "paper.md" in paper["section_patches"])
    check("주석이 annotations.md로 간다", "annotations.md" in paper["section_patches"])
    check("READING_STATUS 패치가 잡힌다", "Progress" in paper["reading_patch"])
    check(
        "패치 절은 세션 원문에서 빠진다",
        "정제본 갱신" not in paper["body"] and "READING_STATUS" not in paper["body"],
    )
    check("세션 원문은 남는다", "시행 간 상관의 낮음이다" in paper["body"])

    # ⑥ 논문별 저장소 — meta.yaml · Parking Lot · 아티팩트 (2026-08-04)
    #    러너의 논문 루프가 실제로 만드는 산출물이 받는 곳 없이 세션 원문에 묻히면,
    #    다음 세션의 러너가 못 찾고 같은 선수지식을 매번 다시 미룬다.
    print("\n논문별 저장소")
    RICH_BODY = PAPER_BODY + """
## 메타
- title: EEG variability in MI-BCI
- year: 2025
- understanding: 기능적 이해
- 지어낸키: 버려야 한다

## Parking Lot
- Fréchet mean — 평균의 일반화, 계산법은 미룸
- SPD manifold

## 아티팩트
### Euclidean vs Fréchet mean
- 유클리드 평균은 직선 위, Fréchet은 곡면 위
"""
    rich = ingest.build_paper_session(
        {"number": 43, "title": "[논문] eeg-variability-mi-bci — Methods", "body": RICH_BODY,
         "comments": []},
        "2026-08-04",
    )
    check("메타가 키로 파싱된다", rich["meta"].get("year") == "2025", str(rich["meta"]))
    check("이해 단계가 잡힌다", rich["meta"].get("understanding") == "기능적 이해")
    check("모르는 키는 버린다", "지어낸키" not in rich["meta"], str(rich["meta"]))
    check("Parking Lot 절이 잡힌다", "Fréchet mean" in rich["parking"])
    check("아티팩트 절이 잡힌다", "### Euclidean vs Fréchet mean" in rich["artifacts"])
    check(
        "새 절들은 세션 원문에서 빠진다",
        "Parking Lot" not in rich["body"] and "## 아티팩트" not in rich["body"],
    )

    # ⑥-b `root:` 지시행 — 앱의 읽기 화면이 파킹랏·주석을 저장소로 올리게 되면서 열었다
    #     (2026-08-14, 유지훈: *"파킹랏이나 주석이 … 항상 gpt가 읽을 수 있는 온라인으로"*).
    #     렉처노트·교재는 `materials/`에 사는데 파킹랏을 받는 곳이 `papers/`밖에 없어서,
    #     자료에 남긴 표시는 러너가 볼 수 없었다.
    print("\n[논문] root: 지시행")
    MARKS_BODY = """root: materials
slug: ee202-lec08

앱 읽기 화면에서 남긴 표시 2건 — 파킹랏 1 · 주석 1.

## Parking Lot
- phasor domain — 3쪽 · 왜 j가 붙나

## 주석
> "impedance is the ratio of phasors"
— 저항과 무엇이 다른가 (4쪽)
"""
    marks = ingest.build_paper_session(
        {"number": 51, "title": "[논문] ee202-lec08 — 읽기 표시 2026-08-14",
         "body": MARKS_BODY, "comments": []},
        "2026-08-14",
    )
    check("root: materials가 잡힌다", marks["root"] == "materials", marks["root"])
    check("root 지시행은 세션 원문에서 빠진다", "root:" not in marks["body"], marks["body"][:80])
    check("slug 지시행이 제목보다 이긴다", marks["slug"] == "ee202-lec08", marks["slug"])
    check("파킹랏 항목이 잡힌다", "phasor domain" in marks["parking"])
    check("주석이 annotations.md로 간다", "annotations.md" in marks["section_patches"])

    check("root:가 없으면 papers가 기본이다", paper["root"] == "papers", paper["root"])

    # 모르는 뿌리는 **기본값으로 떨어뜨린다.** 거부하면 러너가 오타 하나로 세션 기록을
    # 잃는다. 그리고 이 값이 `os.path.join`의 첫 칸이 되므로 경로 탈출은 절대 통과하면 안 된다.
    for bad in ("../../etc", "daily", ".github", "/papers", "papers/../..", ""):
        got = ingest.parse_root(bad)
        check(f"모르는 뿌리는 papers로 떨어진다 ({bad!r})", got == "papers", got)
    check("papers는 그대로", ingest.parse_root("papers") == "papers")
    check("materials는 그대로", ingest.parse_root("materials") == "materials")
    check("앞뒤 공백·슬래시를 다듬는다", ingest.parse_root("  materials/  ") == "materials")

    # 실제로 `materials/<slug>/`에 쓰는지 — 경로가 갈리는 지점이라 파일로 확인한다.
    import tempfile as _tf
    _cwd = os.getcwd()
    with _tf.TemporaryDirectory() as tmp2:
        os.chdir(tmp2)
        try:
            touched, _applied, extra = ingest.write_paper_session(
                marks, {"number": 51}, "2026-08-14")
            parking_path = os.path.join("materials", "ee202-lec08", "parking-lot.md")
            check("세션이 materials/ 아래로 간다",
                  touched[0].startswith(os.path.join("materials", "ee202-lec08")), touched[0])
            check("파킹랏이 materials/<slug>/parking-lot.md에 생긴다",
                  os.path.exists(parking_path), str(touched))
            check("papers/ 아래에는 아무것도 안 생긴다",
                  not os.path.exists(os.path.join("papers", "ee202-lec08")))
            text = open(parking_path, encoding="utf-8").read()
            check("파킹랏 항목이 담긴다", "phasor domain" in text, text)
            check("새 항목으로 센다", extra["parked"][0] == 1, str(extra["parked"]))
            annot = open(os.path.join("materials", "ee202-lec08", "annotations.md"),
                         encoding="utf-8").read()
            check("주석이 Issue 번호 블록으로 감싸인다", "<!-- issue:51 -->" in annot, annot[:120])

            # 같은 Issue를 다시 돌려도 중복이 안 쌓인다(코멘트마다 CI가 다시 돈다).
            ingest.write_paper_session(marks, {"number": 51}, "2026-08-14")
            again = open(os.path.join("materials", "ee202-lec08", "annotations.md"),
                         encoding="utf-8").read()
            check("재실행에도 주석이 한 벌이다",
                  again.count("impedance is the ratio of phasors") == 1, again)
            twice = open(parking_path, encoding="utf-8").read()
            check("재실행에도 파킹랏이 한 벌이다", twice.count("phasor domain") == 1, twice)
        finally:
            os.chdir(_cwd)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "parking-lot.md")
        ingest.merge_parking_lot(path, "- Fréchet mean — 미룸\n- DTW", "p", "2026-08-04")
        # 같은 항목이 다시 걸려도 목록이 부풀지 않아야 한다.
        added, resolved = ingest.merge_parking_lot(
            path, "- [x] Fréchet mean — 배웠다\n- SPD manifold", "p", "2026-08-05")
        text = open(path, encoding="utf-8").read()
        check("Parking Lot 항목이 중복되지 않는다", text.count("Fréchet mean") == 1, text)
        check("해소는 [x]로 표시된다", "- [x] Fréchet mean" in text, text)
        check("새 항목만 새로 센다", (added, resolved) == (1, 1), f"{added},{resolved}")
        check("미해소 항목은 남는다", "- [ ] DTW" in text, text)

        # 한 번 해소된 것을 다시 미해결로 내리지 않는다(러너가 옛 목록을 그대로 붙일 때).
        ingest.merge_parking_lot(path, "- Fréchet mean", "p", "2026-08-06")
        check("해소는 되돌아가지 않는다", "- [x] Fréchet mean" in
              open(path, encoding="utf-8").read())

        meta_path = os.path.join(tmp, "meta.yaml")
        ingest.merge_meta(meta_path, {"title": "T", "year": "2025"}, "p", "2026-08-04")
        ingest.merge_meta(meta_path, {"understanding": "비판적 이해"}, "p", "2026-08-05")
        meta = open(meta_path, encoding="utf-8").read()
        check("meta.yaml은 키 단위로 병합된다", "title: T" in meta and "비판적 이해" in meta, meta)

        # flow만 합집합 — 여러 세션에 걸쳐 통과한 단계가 덮어써지면 완료 판정이 안 난다.
        flow_path = os.path.join(tmp, "meta-flow.yaml")
        ingest.merge_meta(flow_path, {"flow": "한계, 문제"}, "p", "2026-08-15")
        ingest.merge_meta(flow_path, {"flow": "방법"}, "p", "2026-08-16")
        flow_meta = open(flow_path, encoding="utf-8").read()
        check("flow는 세션을 넘어 쌓인다", "flow: 문제, 한계, 방법" in flow_meta, flow_meta)
        # 다른 키를 적은 세션이 flow를 지우면 안 된다(러너는 이번에 통과한 것만 적는다).
        ingest.merge_meta(flow_path, {"understanding": "기능적 이해"}, "p", "2026-08-17")
        check("flow는 안 적은 세션에도 남는다",
              "flow: 문제, 한계, 방법" in open(flow_path, encoding="utf-8").read())
        check("모르는 단계 이름은 버린다", ingest.merge_flow(None, "요약, 결론") == "")

        # ⑦ Position 절 — 이미 세션을 한 번 돌린(=템플릿 갱신 전에 만들어진) 파일에도
        #    뒤늦게 절이 생겨야 다음 세션의 패치가 조용히 버려지지 않는다.
        reading_path = os.path.join(tmp, "READING_STATUS.md")
        with open(reading_path, "w", encoding="utf-8") as f:
            f.write(
                "---\ntitle: x\nupdated: 2026-08-01\n---\n\n"
                "## Progress\n\n- (아직 없음)\n\n"
                "## Current Understanding\n\n- (아직 없음)\n\n"
                "## Next Session\n\n- (다음 세션의 시작점 한 줄)\n"
            )
        migrated = ingest.ensure_position_section(reading_path)
        check("Position 절이 없는 기존 파일에 붙는다", migrated,
              open(reading_path, encoding="utf-8").read())
        check("Progress 절은 그대로 남는다",
              "## Progress" in open(reading_path, encoding="utf-8").read())

        again = ingest.ensure_position_section(reading_path)
        check("이미 있으면 다시 손대지 않는다(멱등)", again is False)
        check("절이 중복되지 않는다",
              open(reading_path, encoding="utf-8").read().count("## Position") == 1)

        ingest.apply_section_patch(
            {"Position": '- cs224n-lec08: "attention은 모든 위치를 동시에 고려한다"'},
            "2026-08-08", path=reading_path)
        out = open(reading_path, encoding="utf-8").read()
        check("마이그레이션 뒤에는 Position 패치가 실제로 적용된다",
              "attention은 모든 위치를 동시에 고려한다" in out, out)

        fresh_path = os.path.join(tmp, "READING_STATUS_fresh.md")
        ingest.ensure_status_file(fresh_path, ingest.READING_STATUS_TEMPLATE, "2026-08-08")
        check("새로 만든 파일은 처음부터 Position 절을 가진다",
              "## Position" in open(fresh_path, encoding="utf-8").read())

        # ⑧ 자료 삭제 — 이 저장소에서 **파일을 지우는 유일한 경로**다. 앱도 자기 쪽에서
        #    막지만 Issue는 사람이 손으로도 만들 수 있으므로 여기가 마지막 관문이다.
        print("\n자료 삭제 — 모양 가드")
        good, bad = ingest.parse_delete_targets(
            "- papers/attn-demo\n- materials/피어싱-논문\n- `papers/quoted`\n"
        )
        check("정상 경로를 읽는다", good == [
            ("papers", "attn-demo"), ("materials", "피어싱-논문"), ("papers", "quoted"),
        ], str(good))
        check("정상만 있으면 버린 것이 없다", bad == [], str(bad))

        # 이 목록이 통과하면 CI가 repo 루트에서 그것을 지운다.
        danger = (
            "- papers/..\n"
            "- papers/../../etc\n"
            "- ../papers/x\n"
            "- daily/2026-08-01\n"
            "- .github/workflows\n"
            "- papers/a/b\n"
            "- papers/\n"
            "- /etc/passwd\n"
            "- papers/a b\n"
        )
        d_ok, d_bad = ingest.parse_delete_targets(danger)
        check("경로 탈출·다른 뿌리를 전부 막는다", d_ok == [], str(d_ok))
        check("막은 것을 보고한다(조용히 버리지 않는다)", len(d_bad) == 9, str(d_bad))

        check("안내용 인용줄은 대상이 아니다",
              ingest.parse_delete_targets("> papers/x 를 지운다\n")[0] == [])

        # 실제로 지운다 — 폴더 통째로 + 옛 단일 파일 + 진도 파일의 그 slug 줄.
        del_dir = os.path.join(tmp, "delete-case")
        os.makedirs(os.path.join(del_dir, "papers", "gone", "sessions"))
        os.makedirs(os.path.join(del_dir, "papers", "keep"))
        os.makedirs(os.path.join(del_dir, "materials"))
        for p, body in [
            (["papers", "gone", "source.md"], "원문"),
            (["papers", "gone", "paper.md"], "정제본"),
            (["papers", "gone", "sessions", "2026-08-01-methods.md"], "세션"),
            (["papers", "keep", "source.md"], "남아야 한다"),
            (["materials", "old-single.md"], "옛 단일 파일"),
        ]:
            with open(os.path.join(del_dir, *p), "w", encoding="utf-8") as f:
                f.write(body)
        with open(os.path.join(del_dir, "papers", "READING_STATUS.md"), "w", encoding="utf-8") as f:
            f.write(
                "# 논문 읽기 상태\n\n## Progress\n\n- gone: 3장까지 읽음\n- keep: 1장\n\n"
                "## Position\n\n- gone: \"인용문\"\n"
            )

        cwd = os.getcwd()
        try:
            os.chdir(del_dir)
            removed, missing, touched = ingest.delete_materials(
                [("papers", "gone"), ("materials", "old-single"), ("papers", "없는것")]
            )
        finally:
            os.chdir(cwd)

        check("폴더가 통째로 사라진다", not os.path.exists(os.path.join(del_dir, "papers", "gone")))
        check("옛 단일 파일도 지운다",
              not os.path.exists(os.path.join(del_dir, "materials", "old-single.md")))
        check("다른 자료는 멀쩡하다",
              os.path.exists(os.path.join(del_dir, "papers", "keep", "source.md")))
        check("지운 것을 보고한다", sorted(removed) == ["materials/old-single", "papers/gone"], str(removed))
        check("이미 없던 것을 구별한다", missing == ["papers/없는것"], str(missing))

        status_after = open(os.path.join(del_dir, "papers", "READING_STATUS.md"), encoding="utf-8").read()
        check("진도 파일에서 그 slug 줄이 빠진다", "gone:" not in status_after, status_after)
        check("다른 자료의 진도는 남는다", "- keep: 1장" in status_after, status_after)
        check("절 구조는 그대로다",
              "## Progress" in status_after and "## Position" in status_after, status_after)
        check("진도 파일을 고쳤다고 보고한다", len(touched) == 1, str(touched))

        art_dir = os.path.join(tmp, "artifacts")
        os.makedirs(art_dir)
        written = ingest.write_artifacts(
            art_dir, rich["artifacts"], "p", "2026-08-04", 43)
        check("아티팩트가 제목마다 파일이 된다", len(written) == 1, str(written))
        check("아티팩트 본문이 남는다",
              "곡면 위" in open(written[0], encoding="utf-8").read())

    # ⑦ `[설정]` → topics.yaml (2026-08-04)
    #    사람이 YAML을 손으로 쓰면 문법이 깨지고, 무엇보다 분야를 고정하지 않는다.
    print("\n연구 주제 설정")
    SETTING_BODY = """## 주제

### hbm | HBM (고대역폭 메모리)
query: high bandwidth memory stacked DRAM
seed: 10.1109/ISSCC.2022.9731621
exclude: breast milk | lactation

### old | 안 볼 주제
remove: true
"""
    topics = ingest.build_topics(
        {"number": 50, "title": "[설정] topics — 첫 세션", "body": SETTING_BODY, "comments": []})
    check("주제 id·라벨이 갈린다", topics[0]["id"] == "hbm" and "고대역폭" in topics[0]["label"],
          str(topics[0]))
    check("씨앗 논문이 잡힌다", topics[0].get("seed", "").startswith("10."), str(topics[0]))
    check("삭제 지시가 잡힌다", topics[1].get("remove") is True, str(topics[1]))

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "topics.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 내 주석은 살아남아야 한다\nwindow_days: 14\n\ntopics:\n"
                    "  - id: old\n    label: \"안 볼 주제\"\n    query: \"x\"\n"
                    "  - id: keep\n    label: \"러너가 안 적은 주제\"\n    query: \"y\"\n")
        added, updated, removed = ingest.merge_topics(topics, path=path)
        out = open(path, encoding="utf-8").read()
        check("새 주제가 추가된다", "hbm" in added and "id: hbm" in out, out)
        check("remove가 실제로 지운다", removed == ["old"] and "id: old" not in out, out)
        check("러너가 안 적은 주제는 남는다", "id: keep" in out, out)
        check("파일 위쪽 주석·설정이 살아남는다",
              "내 주석은 살아남아야 한다" in out and "window_days: 14" in out, out)

        # scan_papers가 이 파일을 실제로 읽을 수 있어야 한다 — 형식이 어긋나면
        # 주제가 통째로 사라지고 "이번 주 0편"으로만 보인다.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import scan_papers  # noqa: E402
        cfg = scan_papers.load_yaml(path)
        ids = [t.get("id") for t in cfg.get("topics") or []]
        check("scan_papers가 그대로 읽는다", "hbm" in ids and "keep" in ids, str(ids))
        hbm = next(t for t in cfg["topics"] if t.get("id") == "hbm")
        check("씨앗이 왕복해서 살아남는다", hbm.get("seed", "").startswith("10."), str(hbm))
        check("배제어가 실제로 거른다",
              scan_papers.drop_excluded(
                  [{"title": "Human breast milk composition", "abstract": ""},
                   {"title": "HBM thermal throttling", "abstract": ""}], hbm)[1] == 1)
        check("분야 고정이 있으면 필터가 붙는다",
              "primary_topic.field.id:fields/22" in scan_papers._filter_of({"field": "fields/22"}))
        check("고정이 없으면 필터가 비어 있다", scan_papers._filter_of({"query": "x"}) == "")

    # ⑧ 학습 트랙 — 과목이 `daily/` 한 폴더에 섞이지 않게 (2026-08-04)
    print("\n학습 트랙")
    TRACK_BODY = """## 트랙

### electronics | 전자공학
mode: 진도
goal: 회로 해석을 스스로 설명하기

### old | 안 쓰는 트랙
remove: true
"""
    tracks = ingest.build_tracks(
        {"number": 60, "title": "[설정] tracks — 과목 분리", "body": TRACK_BODY, "comments": []})
    check("트랙 id·라벨이 갈린다",
          tracks[0]["id"] == "electronics" and tracks[0]["label"] == "전자공학", str(tracks[0]))
    check("모드·목표가 잡힌다", tracks[0].get("mode") == "진도", str(tracks[0]))

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "tracks.yaml")
        ingest.merge_tracks(tracks, path=path)
        loaded = ingest.load_tracks(path)
        check("쓴 것을 그대로 다시 읽는다", [t["id"] for t in loaded] == ["electronics"], str(loaded))

        # 러너는 사람이 말한 이름(한글 라벨)을 그대로 적기 쉽다 — id로 맞춰 준다.
        check("라벨로도 트랙을 찾는다", ingest.resolve_track("전자공학", loaded) == "electronics")
        check("id로도 찾는다", ingest.resolve_track("electronics", loaded) == "electronics")
        # 없는 트랙을 만들어 내면 유령 폴더가 생겨 다음 세션부터 기록이 갈라진다.
        check("없는 이름은 만들지 않는다", ingest.resolve_track("영어", loaded) is None)

        # 트랙이 있으면 그 폴더로, 없으면 예전처럼 루트로.
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            os.makedirs("daily", exist_ok=True)
            p1 = ingest.target_path("2026-08-04", "rc", 1, "electronics")
            check("트랙 세션은 daily/<track>/으로 간다",
                  p1 == os.path.join("daily", "electronics", "2026-08-04-rc.md"), p1)
            p2 = ingest.target_path("2026-08-04", "rc", 2, None)
            check("트랙이 없으면 예전처럼 daily/ 루트",
                  p2 == os.path.join("daily", "2026-08-04-rc.md"), p2)

            # 트랙 도입 전 노트를 다시 수집해도 파일이 둘로 갈라지면 안 된다.
            os.makedirs(os.path.join("daily", "electronics"), exist_ok=True)
            old = os.path.join("daily", "2026-08-01-old.md")
            with open(old, "w", encoding="utf-8") as f:
                f.write("---\nsource_issue: 7\n---\n")
            check("옛 노트를 다시 수집하면 같은 파일에 덮어쓴다",
                  ingest.target_path("2026-08-04", "old", 7, "electronics") == old)

            # 노트는 쌓이는데 그래프만 비어 가는 실패를 막는다 — 조용해서 알아채기 어렵다.
            with open(os.path.join("daily", "electronics", "2026-08-05-n.md"),
                      "w", encoding="utf-8") as f:
                f.write("---\nsource_issue: 8\n---\n# 트랙 노트\n")
            sys.path.insert(0, os.path.join(cwd, "scripts"))
            import build_concepts  # noqa: E402
            found = [p for p, _ in build_concepts._daily_notes("daily")]
            check("개념 빌더가 서랍 안을 본다",
                  os.path.join("daily", "electronics", "2026-08-05-n.md") in found, str(found))
            check("개념 빌더가 평평한 노트도 그대로 본다", old in found, str(found))
        finally:
            os.chdir(cwd)

    # `[설정]` → subjects.yaml (2026-08-05)
    # 러너가 개념 지도 소제목을 매번 새로 지어 같은 것이 여러 조각으로 갈라졌다
    # (파일럿: "회로 등가화 6 · 전자회로 5 · 전자회로 기초 4"). 합치는 표는
    # build_concepts가 이미 읽는데 **채울 쓰기 경로가 없었다.**
    print("\n분야 묶기")
    SUBJECT_BODY = """## 분야

### 전자회로
- 회로 등가화
- 전자회로 기초

### 신호처리
"""
    subj_issue = {"number": 70, "title": "[설정] subjects", "body": SUBJECT_BODY, "comments": []}
    subjects = ingest.build_subjects(subj_issue)
    check("대표 이름과 별칭이 갈린다",
          subjects[0]["name"] == "전자회로" and "회로 등가화" in subjects[0]["aliases"],
          str(subjects[0]))
    check("별칭 없는 분야도 유효하다",
          any(s["name"] == "신호처리" for s in subjects), str(subjects))
    check("`## 분야` Issue는 트랙·주제로 새지 않는다",
          ingest.build_tracks(subj_issue) == [] and ingest.build_topics(subj_issue) == [])

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "subjects.yaml")
        ingest.merge_subjects(subjects, path=path)
        # 별칭은 합집합이다 — 이번에 안 적은 것을 지우면 지난번 묶음이 다시 갈라진다.
        added, updated, removed = ingest.merge_subjects(
            [{"name": "전자회로", "aliases": ["회로이론"]}], path=path)
        out = open(path, encoding="utf-8").read()
        check("새 별칭이 더해진다", "회로이론" in out and updated == ["전자회로"], out)
        check("지난 별칭이 살아남는다", "회로 등가화" in out and "전자회로 기초" in out, out)
        check("안 적은 분야는 남는다", "신호처리" in out, out)
        check("주석이 살아남는다", out.lstrip().startswith("#"), out[:80])

        # build_concepts가 이 출력을 실제로 읽어 합쳐야 의미가 있다(CI 왕복 계약).
        cwd2 = os.getcwd()
        try:
            os.chdir(tmp)
            sys.path.insert(0, os.path.join(cwd2, "scripts"))
            import build_concepts  # noqa: E402
            alias = build_concepts.load_subjects()
            merged, n = build_concepts.normalize_domains(
                {"테브난": "회로 등가화", "노턴": "전자회로 기초", "푸리에": "신호처리"}, alias)
            check("그래프 빌더가 실제로 합친다",
                  merged["테브난"] == "전자회로" and merged["노턴"] == "전자회로" and n == 2,
                  str(merged))
            check("다른 분야는 안 건드린다", merged["푸리에"] == "신호처리", str(merged))
        finally:
            os.chdir(cwd2)

    # `지금 약한 것`은 교체가 아니라 누적 (2026-08-05)
    # 이번 세션에서 안 다룬 약점이 지워지면 러너는 그것을 다시 만나지 못한다.
    print("\n약점 누적")
    STATUS_TEMPLATE = """---
updated: 2026-08-02
---
## 지금 약한 것 (top 5 — 세션은 여기서 시작)
> 전체는 [[mastery.md]]. 아직 `설명가능`이 아닌 것부터.
- (첫 세션의 스캔에서 채워진다)

## 다음 복습 질문
1.
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "STATUS.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(STATUS_TEMPLATE)

        ingest.apply_section_patch({"지금 약한 것": "1. KCL 근거\n2. KVL 순에너지"},
                                   "2026-08-03", path=path)
        out = open(path, encoding="utf-8").read()
        check("자리표시자는 실제 항목이 들어오면 사라진다", "첫 세션의 스캔" not in out, out)
        check("안내용 인용은 남는다", "전체는 [[mastery.md]]" in out, out)

        # 다음 세션이 전혀 다른 주제를 다뤄도 지난 약점은 남아 있어야 한다.
        ingest.apply_section_patch({"지금 약한 것": "1. Rth 계산 순서\n2. Norton 변환"},
                                   "2026-08-04", path=path)
        out = open(path, encoding="utf-8").read()
        check("지난 약점이 살아남는다", "KCL 근거" in out and "KVL 순에너지" in out, out)
        check("새 약점이 앞에 온다", out.index("Rth 계산 순서") < out.index("KCL 근거"), out)

        ingest.apply_section_patch({"지금 약한 것": "1. KCL 근거"}, "2026-08-05", path=path)
        out = open(path, encoding="utf-8").read()
        check("같은 약점이 중복되지 않는다", out.count("KCL 근거") == 1, out)

        # 상한이 없으면 STATUS.md가 커져 러너가 매 세션 통째로 읽는 비용이 오른다.
        ingest.apply_section_patch(
            {"지금 약한 것": "\n".join(f"{i}. 새 약점 {i}" for i in range(1, 8))},
            "2026-08-06", path=path)
        section = open(path, encoding="utf-8").read().split("## 지금 약한 것")[1].split("##")[0]
        check("상한 5개를 넘지 않는다",
              len([l for l in section.splitlines() if l.strip()[:2].rstrip(".").isdigit()]) == 5,
              section)

        # 다른 절은 예전대로 교체여야 한다 — 복습 질문은 그 세션이 고른 것이다.
        ingest.apply_section_patch({"다음 복습 질문": "1. 왜 Open Circuit인가"},
                                   "2026-08-06", path=path)
        ingest.apply_section_patch({"다음 복습 질문": "1. 왜 Short Circuit인가"},
                                   "2026-08-07", path=path)
        check("복습 질문은 여전히 교체된다",
              "왜 Open Circuit인가" not in open(path, encoding="utf-8").read())

    # ── `[자료]` 라벨은 사실을 말한다 ────────────────────────────────────────
    #
    # 2026-08-09: 앱에서 PDF를 파싱해 초안만 만들고 세션 없이 닫으면 본문 전체가 원문인데도
    # frontmatter가 조건 없이 `distilled`를 적고 있었다(실측 102KB, `## ` 헤딩은
    # `러너에게`·`원문` 둘뿐). 조용한 거짓말이라 저작권 판단까지 오도한다.
    print("\n[자료] 증류 라벨")
    APP_DRAFT = {"number": 7, "title": "[자료] 2026-08-09 piercing — Threshold Crossing",
                 "body": "## 러너에게\n읽어라\n\n## 원문\n" + "본문 " * 50}
    REAL = {"number": 8, "title": "[자료] 2026-08-09 cs224n — Lecture 8",
            "body": "## 요약\n목차 수준의 지도\n\n## 개념 지도\n- 어텐션 ← 내적\n\n"
                    "## 빈칸 문제\n1. ___은 쿼리와 키의 내적이다."}

    drafted = ingest.build_material(APP_DRAFT, "2026-08-09")
    drafted_src = drafted["files"]["source.md"]
    check("증류 없는 원문에 distilled가 안 붙는다", "distilled]" not in drafted_src)
    check("source가 증류를 주장하지 않는다", "증류 없음" in drafted_src)
    check("build_material이 판정을 돌려준다", drafted["distilled"] is False)

    # 증류가 없어도 **원문은 약속한 자리에 그냥 저장된다**(유지훈 2026-08-10).
    # 증류 성공 여부로 경로가 바뀌면 앱이 화면에 적은 `<root>/<slug>/source.md`가 거짓이
    # 되고, 러너의 `read_doc`이 404를 받는다 — 도구를 버리게 만드는 그 실패다.
    check("증류가 없어도 원문은 source.md에 남는다", set(drafted["files"]) == {"source.md"})
    check("빈 distilled.md를 만들지 않는다(자료)", "distilled.md" not in drafted["files"])
    check("원문이 온전하다", "본문 본문" in drafted_src)
    # 증류본이 없으면 머리말이 갈 곳이 없다 — 버리지 않고 원문 앞에 둔다.
    check("머리말이 보존된다", "읽어라" in drafted_src)
    check("증류 없는 자료도 폴더형", drafted["flat"] is None)

    # 손으로 쓴 노트에는 `## 원문` 경계가 없다 — 나눌 것이 없으니 그때만 단일 파일이다.
    flat_only = ingest.build_material(
        {"number": 70, "title": "[자료] 2026-08-09 memo — 메모",
         "body": "## 러너에게\n읽어라\n\n경계가 없는 본문"}, "2026-08-09")
    check("경계가 없으면 단일 파일", flat_only["files"] is None)
    check("단일 파일은 raw로 적힌다", "tags: [material, raw]" in flat_only["flat"],
          flat_only["flat"][:200])

    real = ingest.build_material(REAL, "2026-08-09")
    check("실제 증류본은 distilled로 적힌다", "tags: [material, distilled]" in real["flat"],
          real["flat"][:200])
    check("실제 증류본의 source는 증류를 말한다", "자료 증류 →" in real["flat"])
    check("실제 증류본 판정", real["distilled"] is True)

    # 판정 기준 자체 — `## 개념 지도`가 파이프라인이 실제로 먹는 절이다.
    check("개념 지도가 있으면 증류", ingest.is_distilled("## 개념 지도\n- A ← B"))
    check("이모지·주석이 붙어도 잡는다", ingest.is_distilled("## 🗺️ 개념 지도 (초안)\n- A ← B"))
    check("요약만 있으면 증류가 아니다", not ingest.is_distilled("## 요약\n지도"))
    check("빈 본문은 증류가 아니다", not ingest.is_distilled(""))

    # ── 증류 / 원문 가르기 (앱이 `## 원문`을 경계로 초안을 만든다) ─────────────
    print("\n[자료] 증류·원문 가르기")
    check("경계가 없으면 안 가른다", ingest.split_source("## 요약\n지도")[1] is None)
    head, src = ingest.split_source("## 요약\n지도\n\n## 원문\n\n본문이다")
    check("경계 앞이 증류", "## 요약" in head and "본문이다" not in head)
    check("경계 뒤가 원문", src.strip() == "본문이다")

    APP_DISTILLED = {"number": 9, "title": "[자료] 2026-08-09 attention — Attention Is All You Need",
                     "body": "# Attention\n\n## 요약\n- 어텐션이 순환을 대체\n\n"
                             "## 개념 지도\n### 딥러닝\n- 어텐션 ← 내적\n\n"
                             "## 빈칸 문제\n1. ___\n\n## 원문\n\n### 1 Introduction\n\nRecurrent models…"}
    folded = ingest.build_material(APP_DISTILLED, "2026-08-09")
    dist, src_file = folded["files"]["distilled.md"], folded["files"]["source.md"]
    check("증류가 있으면 폴더형으로 나뉜다", set(folded["files"]) == {"distilled.md", "source.md"})
    check("증류본은 distilled", "tags: [material, distilled]" in dist)
    check("원문은 source", "tags: [material, source]" in src_file)
    check("개념 지도는 증류본에만 있다",
          "## 개념 지도" in dist and "## 개념 지도" not in src_file)
    check("원문이 그대로 보존된다", "Recurrent models" in src_file)
    # 원문 쪽에 개념 지도가 없어야 빌더가 같은 간선을 두 번 읽지 않는다(materials/** 전부를 본다).
    check("증류본에 원문이 섞이지 않는다", "Recurrent models" not in dist)
    check("자료는 materials/로 간다", folded["root"] == "materials")

    check("자료도 증류 없이 폴더형", set(
        ingest.build_material(APP_DRAFT, "2026-08-09")["files"]) == {"source.md"})

    # ── 원문 목차 — 어느 절을 열지 고르는 지도 ─────────────────────────────────
    print("\n[자료] 원문 목차")
    check("원문의 ### 제목을 긁는다",
          ingest.source_toc("### 1 Introduction\n글\n\n### 3.2.1 Scaled Dot\n글")
          == ["1 Introduction", "3.2.1 Scaled Dot"])
    check("제목이 없으면 빈 목록", ingest.source_toc("본문뿐이다") == [])
    check("증류본에 원문 목차가 실린다", "## 원문 목차" in dist and "- 1 Introduction" in dist)
    check("목차가 read_doc 쓰는 법을 알려준다", "`section`" in dist)
    # ⚠️ `split_source`의 경계는 `^##\s*원문\s*$`로 줄 끝까지 고정이다. `## 원문 목차`가
    #    경계로 오인되면 증류본이 원문 취급되어 파일이 잘못 갈린다.
    check("`## 원문 목차`는 원문 경계로 오인되지 않는다",
          ingest.split_source("## 원문 목차\n- A\n\n본문")[1] is None)
    no_toc = ingest.build_material(
        {"number": 11, "title": "[자료] 2026-08-09 x — X",
         "body": "## 개념 지도\n- A ← B\n\n## 원문\n\n제목 없는 원문이다"}, "2026-08-09")
    check("원문에 절이 없으면 목차 절을 안 만든다",
          "## 원문 목차" not in no_toc["files"]["distilled.md"])

    # ── 논문도 같은 방식 — `paper:` 지시행이 papers/<slug>/로 보낸다 ───────────
    print("\n[논문] 원문 보존 (자료와 같은 기계)")
    PAPER = {"number": 12, "title": "[자료] 2026-08-09 attention — Attention Is All You Need",
             "body": "paper: attention-is-all-you-need\n\n## 개념 지도\n- 어텐션 ← 내적\n\n"
                     "## 원문\n\n### 1 Introduction\n\nRecurrent models…"}
    paper = ingest.build_material(PAPER, "2026-08-09")
    check("논문은 papers/로 간다", paper["root"] == "papers")
    check("논문 slug는 지시행이 정한다", paper["slug"] == "attention-is-all-you-need")
    check("논문도 폴더형", set(paper["files"]) == {"distilled.md", "source.md"})
    check("지시행이 본문에 남지 않는다", "paper:" not in paper["files"]["source.md"])

    # 증류가 없어도 논문은 폴더다 — `papers/<slug>/`가 이미 폴더 규약이고, 빈 껍데기
    # distilled.md를 만드는 대신 source.md 하나만 둔다.
    paper_raw = ingest.build_material(
        {"number": 13, "title": "[자료] 2026-08-09 p — P",
         "body": "paper: p\n\n## 러너에게\n읽어라\n\n## 원문\n\n원문뿐"}, "2026-08-09")
    check("증류 없는 논문도 폴더형", paper_raw["files"] is not None)
    check("빈 distilled.md를 만들지 않는다", set(paper_raw["files"]) == {"source.md"})

    print("\n[자료] 같은 Issue를 다시 보내도 파일이 늘지 않는다")
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            os.makedirs("materials/old-single", exist_ok=True)
            with open("materials/plain.md", "w", encoding="utf-8") as f:
                f.write("---\nsource_issue: 42\n---\n")
            with open("materials/old-single/distilled.md", "w", encoding="utf-8") as f:
                f.write("---\nsource_issue: 43\n---\n")
            check("단일 파일형을 찾는다", ingest.existing_material_slug(42) == "plain")
            check("폴더형을 찾는다", ingest.existing_material_slug(43) == "old-single")
            check("없으면 None", ingest.existing_material_slug(99) is None)
        finally:
            os.chdir(cwd)

    print("\n[자료] 단일 파일 → 폴더형으로 올라갈 때 옛 파일이 남지 않는다")
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            os.makedirs("materials", exist_ok=True)
            # 전에 증류 없이 저장된 같은 자료(같은 Issue 번호).
            with open("materials/attention.md", "w", encoding="utf-8") as f:
                f.write("---\ntags: [material, raw]\nsource_issue: 9\n---\n\n원문뿐\n")
            with open("payload.json", "w", encoding="utf-8") as f:
                json.dump(APP_DISTILLED, f)
            argv = sys.argv
            sys.argv = ["ingest", "--payload", "payload.json", "--today", "2026-08-09"]
            try:
                ingest.main()
            finally:
                sys.argv = argv
            check("폴더형이 생겼다", os.path.isfile("materials/attention/distilled.md")
                  and os.path.isfile("materials/attention/source.md"))
            check("옛 단일 파일이 지워졌다", not os.path.exists("materials/attention.md"),
                  str(os.listdir("materials")))
        finally:
            os.chdir(cwd)

    # ── 자료 진도 — 논문의 READING_STATUS와 같은 기계 ────────────────────────
    #
    # 원문을 절 단위로 읽게 되면서 "오늘 어느 절부터인가"가 세션의 첫 물음이 됐다.
    # 기록이 없으면 러너가 daily에서 짐작하고, 짐작이 틀리면 이미 한 절을 또 한다.
    # ── 학습 설계도 — 순서의 SSOT (2026-08-10) ────────────────────────────────
    #
    # 이 파일은 `git add` 범위에 없어서 **손으로만 갱신됐다.** 그래서 `[다음]`·`[완료]`
    # 표시가 세션이 진행돼도 움직이지 않았다. 자료 진도와 같은 기계를 그대로 쓴다.
    print("\n[학습] 학습 설계도")
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            os.makedirs("daily")
            with open("STATUS.md", "w", encoding="utf-8") as f:
                f.write("---\n---\n## 지금 약한 것\n- x\n")
            with open("payload.json", "w", encoding="utf-8") as f:
                json.dump({
                    "number": 30, "title": "[학습] 2026-08-10 phase — 위상",
                    "body": "## 목표\n- 위상\n\n## 오늘 직접 학습한 지식\n1. 위상은 같은 주파수의 cos/sin 비율이다\n\n"
                            "## 학습 설계도\n### 학습 경로\n"
                            "| 단계 | 주제 | 왜 이 순서 | 검증 기준 |\n|---|---|---|---|\n"
                            "| 7 `[완료]` | 위상과 복소지수 | Fourier 뒤 | 진폭·위상 둘 다 필요한 이유 |\n",
                }, f)
            argv = sys.argv
            sys.argv = ["ingest", "--payload", "payload.json", "--today", "2026-08-10"]
            try:
                ingest.main()
            finally:
                sys.argv = argv

            # 파일이 없었으므로 견본이 먼저 생기고, 그 위에 절이 교체된다.
            spec = open("learning-spec.md", encoding="utf-8").read()
            check("설계도가 없으면 견본을 만든다", "kind: learning-spec" in spec, spec[:120])
            check("mode: topdown 이 적힌다", "mode: topdown" in spec)
            check("경로가 갱신된다", "위상과 복소지수" in spec, spec)
            check("완료 표시가 들어간다", "`[완료]`" in spec)
            note = open(f"daily/{os.listdir('daily')[0]}", encoding="utf-8").read()
            check("설계도 절은 세션 노트에 안 남는다", "학습 설계도" not in note)
        finally:
            os.chdir(cwd)

    # `[설정]`으로 처음 만드는 경로 — 새 사용자의 첫 파일이다.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            with open("payload.json", "w", encoding="utf-8") as f:
                json.dump({
                    "number": 31, "title": "[설정] 학습 설계도",
                    "body": "## 학습 설계도\n### 학습 목표\n- EEG 기반 조현병 분류를 스스로 설명한다\n"
                            "### 없는 절이다\n- 이건 버려져야 한다\n",
                }, f)
            argv = sys.argv
            sys.argv = ["ingest", "--payload", "payload.json", "--today", "2026-08-10",
                        "--report", "report.md"]
            try:
                ingest.main()
            finally:
                sys.argv = argv

            spec = open("learning-spec.md", encoding="utf-8").read()
            check("[설정]으로 설계도가 생긴다", "EEG 기반 조현병 분류" in spec, spec[:200])
            report = open("report.md", encoding="utf-8").read()
            check("생성이라고 보고한다", "생성" in report, report)
            # 없는 절에 보낸 패치는 조용히 버려진다 — 그것을 말해야 한다.
            check("건너뛴 절을 말한다", "없는 절이다" in report and "건너뜀" in report, report)
        finally:
            os.chdir(cwd)

    # ⚠️ 승급 조각의 자리 맞춤 (2026-08-17 실측) — MCP의 3열 표를 그대로 접으면 근거가
    #    중요도 칸에 앉고, 영문 상태가 원장→concepts.json까지 흘러 「설명가능」 판정에
    #    영영 안 잡힌다. 이 변환이 그 사슬의 입구다.
    print("\n[이해도 승급] MCP 3열 표 → 원장 6열")
    three_col = (
        "| 개념 | 승급 | 근거 |\n"
        "|---|---|---|\n"
        "| DTW | can_explain | 시험에서 유도함 |\n"
        "| SVD | memorized | 계산 수행 |\n"
        "| 새어휘 | unknown_state | 근거 |\n"
    )
    fixed = ingest.normalize_mastery_table(three_col, "2026-08-17", "daily/2026-08-17-dtw.md")
    check(
        "6열 머리가 consolidate와 바이트 동일하다 (동조)",
        fixed.splitlines()[0] == ingest.MASTERY_HEADER,
        fixed.splitlines()[0],
    )
    check(
        "상태가 원장 어휘로 번역된다 · 중요도는 비고 · 검증일=세션 날짜 · 증거=노트 링크",
        "| DTW | 설명가능 |  | 2026-08-17 | [[daily/2026-08-17-dtw]] | 시험에서 유도함 |" in fixed,
        fixed,
    )
    check("memorized → 암기", "| SVD | 암기 |" in fixed)
    check(
        "모르는 승급 어휘는 지어내지 않고 그대로 둔다",
        "| 새어휘 | unknown_state |" in fixed,
    )
    six_col = (
        "| 개념 | 상태 | 중요도 | 최근 검증일 | 증거 | 변화 메모 |\n"
        "|---|---|---|---|---|---|\n"
        "| p-value | 설명가능 | H | 2026-08-07 | [[daily/2026-08-07-eeg]] | 조건부 확률로 설명 |\n"
    )
    check(
        "옛 6열 표는 손대지 않는다",
        ingest.normalize_mastery_table(six_col, "2026-08-17", "daily/x.md") == six_col,
    )
    esc = "| 개념 | 승급 | 근거 |\n|---|---|---|\n| A | memorized | 좌\\|우 구분 |\n"
    check(
        "이스케이프된 파이프는 칸 경계가 아니다",
        "| A | 암기 |  | 2026-08-17 | [[daily/x]] | 좌\\|우 구분 |"
        in ingest.normalize_mastery_table(esc, "2026-08-17", "daily/x.md"),
    )

    # ⚠️ `[설정]` 절 사슬 (2026-08-17) — 한 Issue에 몇 절을 적든 전부 반영되고 보고가
    #    쌓인다. 전에는 ① 트랙만 dry-run 관문이 없어 확인 실행이 tracks.yaml을 썼고
    #    ② 뒤 절의 보고가 "w"로 앞 절 보고를 덮어 러너가 트랙 결과를 못 봤고
    #    ③ 지도·분야 뒤의 return이 함께 적은 절을 조용히 버렸다.
    print("\n[설정] 절 사슬 — dry-run 관문 · 보고 누적 · 이른 return 제거")
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_learning_note.py")

    def run_settings(body, extra):
        d = tempfile.mkdtemp()
        pj = os.path.join(d, "payload.json")
        with open(pj, "w", encoding="utf-8") as f:
            json.dump({"title": "[설정] 시험", "body": body, "number": 1}, f, ensure_ascii=False)
        r = subprocess.run(
            [sys.executable, script, "--payload", pj, "--today", "2026-08-17"] + extra,
            cwd=d, capture_output=True, text=True,
        )
        return d, r

    combo = "## 트랙\n### math | 수학\nmode: 진도\n\n## 주제\n### nep\nquery: neural entrainment\n"

    d, r = run_settings(combo, ["--dry-run"])
    check(
        "① 트랙 dry-run이 tracks.yaml을 쓰지 않는다",
        r.returncode == 0 and not os.path.exists(os.path.join(d, "tracks.yaml")),
        r.stdout + r.stderr,
    )
    check(
        "dry-run 출력에 두 절이 다 보인다",
        "[dry-run] tracks.yaml" in r.stdout and "[dry-run] topics.yaml" in r.stdout,
        r.stdout,
    )

    d, r = run_settings(combo, ["--report", "report.md"])
    rep_path = os.path.join(d, "report.md")
    rep_text = open(rep_path, encoding="utf-8").read() if os.path.exists(rep_path) else ""
    check(
        "트랙과 주제가 모두 반영된다",
        os.path.exists(os.path.join(d, "tracks.yaml")) and os.path.exists(os.path.join(d, "topics.yaml")),
        r.stdout + r.stderr,
    )
    check("② 보고에 트랙 절이 남는다 — 뒤 절이 덮지 않는다", "학습 트랙 갱신" in rep_text, rep_text)
    check("보고에 주제 절도 함께 남는다", "연구 주제 갱신" in rep_text, rep_text)

    d, r = run_settings(
        "## 지도\n### 감추기\n- 옛것\n\n## 분야\n### 시계열\n- 시계열 분석\n",
        ["--report", "report.md"],
    )
    rep_text = open(os.path.join(d, "report.md"), encoding="utf-8").read()
    check(
        "③ 지도+분야를 한 Issue에 적어도 둘 다 반영된다",
        os.path.exists(os.path.join(d, "concepts-overrides.yaml"))
        and os.path.exists(os.path.join(d, "subjects.yaml")),
        r.stdout + r.stderr,
    )
    check("보고도 둘 다 남는다", "지식 그래프 손보기" in rep_text and "분야 갱신" in rep_text, rep_text)

    d, r = run_settings("아무 절도 없다", [])
    check("어느 절도 없으면 여전히 실패로 말한다", r.returncode != 0, r.stdout)

    # ⚠️ 워크플로가 파일을 쓰고도 커밋하지 않는 조용한 실패 — 경계 주석과 `git add`가
    #    함께 갱신돼야 한다. 하나만 고치면 설계도가 영원히 저장소에 안 올라간다.
    print("\n[워크플로] 쓰는 경로가 전부 커밋 범위에 있다")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wf = open(os.path.join(repo_root, ".github", "workflows", "learning-note-ingest.yml"),
              encoding="utf-8").read()
    # 커밋 스텝의 `for p in … ; do git add …` 목록을 통째로 읽는다. 줄바꿈(`\`)이 있어서
    # 한 줄만 보면 안 된다 — 2026-08-15에 목록을 늘리며 여러 줄이 됐다.
    m = re.search(r"for p in (.+?); do\s*\n\s*git add", wf, re.S)
    add_scope = (m.group(1).replace("\\\n", " ") if m else "")
    #
    # 2026-08-15 실측: 셋이 빠져 있었고 `|| git add -A` 폴백이 그것을 가리고 있었다.
    # `mastery/` 조각이 가장 위험하다 — 안 남으면 한 세션의 승급을 복구할 곳이 없다.
    for want in ("daily", "materials", "papers", "STATUS.md", "mastery.md", "drills.md",
                 "concepts.json", "topics.yaml", "tracks.yaml", "learning-spec.md",
                 "subjects.yaml", "concepts-overrides.yaml", "mastery/**"):
        check(f"커밋 범위에 {want}", want in add_scope, add_scope or "(git add 목록을 못 찾음)")
    # 폴백에 기대면 목록이 틀려도 안 터진다 — 그래서 폴백이 목록을 대신하면 안 된다.
    check("`|| git add -A` 폴백에 기대지 않는다", "|| git add -A\n" not in wf and
          "|| git add -A " not in wf, "폴백이 아직 목록을 대신하고 있다")
    boundary = [l for l in wf.splitlines() if l.startswith("# 경계:")]
    check("경계 주석도 함께 갱신됐다",
          bool(boundary) and all(w in boundary[0] for w in ("learning-spec.md", "subjects.yaml")),
          boundary[0] if boundary else "(경계 주석을 못 찾음)")

    print("\n[학습] 자료 진도 갱신")
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            os.makedirs("daily")
            with open("STATUS.md", "w", encoding="utf-8") as f:
                f.write("---\n---\n## 지금 약한 것\n- x\n")
            with open("payload.json", "w", encoding="utf-8") as f:
                json.dump({
                    "number": 20, "title": "[학습] 2026-08-10 attn — 어텐션",
                    "body": "## 목표\n- 어텐션\n\n## 오늘 직접 학습한 지식\n1. 어텐션은 내적이다\n\n"
                            "## 자료 진도 갱신\n### Progress\n- cs224n §3.2.1 까지\n"
                            "### Next Session\n- cs224n §3.2.2\n",
                }, f)
            argv = sys.argv
            sys.argv = ["ingest", "--payload", "payload.json", "--today", "2026-08-10"]
            try:
                ingest.main()
            finally:
                sys.argv = argv

            status = open("materials/READING_STATUS.md", encoding="utf-8").read()
            check("자료 진도가 파일로 남는다", "cs224n §3.2.1 까지" in status, status)
            check("다음 세션 시작점도 남는다", "cs224n §3.2.2" in status)
            note = open(f"daily/{os.listdir('daily')[0]}", encoding="utf-8").read()
            check("진도 절은 세션 노트에 안 남는다(파일로 옮겨졌다)", "자료 진도 갱신" not in note)
        finally:
            os.chdir(cwd)

    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            os.makedirs("daily")
            with open("STATUS.md", "w", encoding="utf-8") as f:
                f.write("---\n---\n## 지금 약한 것\n- x\n")
            with open("payload.json", "w", encoding="utf-8") as f:
                json.dump({"number": 21, "title": "[학습] 2026-08-10 x — X",
                           "body": "## 목표\n- x\n\n## 오늘 직접 학습한 지식\n1. 배운 것이 있다\n"}, f)
            argv = sys.argv
            sys.argv = ["ingest", "--payload", "payload.json", "--today", "2026-08-10"]
            try:
                ingest.main()
            finally:
                sys.argv = argv
            # 절을 안 남긴 세션이 빈 진도 파일을 만들면 "진도가 없다"가 아니라 "0이다"로 읽힌다.
            check("진도 절이 없으면 파일을 만들지 않는다",
                  not os.path.exists("materials/READING_STATUS.md"))
        finally:
            os.chdir(cwd)

    # ── 지식 그래프 손보기 (`## 지도` → concepts-overrides.yaml) ──────────────
    #
    # 노드는 daily 노트에서 매번 다시 만들어지므로 진짜 "삭제"는 노트를 고치는 일이 된다.
    # 그건 기록을 거짓으로 만들기 때문에, 지도 위에 덮는 파일만 쓴다. 그 계약을 여기서 지킨다.
    import tempfile
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            issue = {"title": "[설정] 지도 정리", "body": (
                "## 지도\n"
                "### 감추기\n- 오늘 한 것\n- TODO\n"
                "### 이름 합치기\n- Fréchet 평균 → Fréchet mean\n- 옛 이름 -> 새 이름\n"
            )}
            got = ingest.build_overrides(issue)
            check("감출 이름을 읽는다", got["hidden"] == ["오늘 한 것", "TODO"], got)
            check("화살표는 → 와 -> 를 모두 받는다",
                  got["renamed"] == [
                      {"from": "Fréchet 평균", "to": "Fréchet mean"},
                      {"from": "옛 이름", "to": "새 이름"},
                  ], got)

            ingest.merge_overrides(got)
            text = open(ingest.OVERRIDES_PATH, encoding="utf-8").read()
            check("파일에 감춘 이름이 적힌다", "오늘 한 것" in text, text)

            # 두 번 와도 같은 항목이 쌓이지 않는다 — Issue는 재실행될 수 있다.
            again = ingest.merge_overrides(got)
            check("같은 것을 다시 보내도 늘지 않는다", again == ([], []), again)

            # 이 파일은 여러 세션에 걸쳐 자란다. 이번에 안 적은 것을 지우면 지난번에
            # 감춘 노드가 슬그머니 되살아난다.
            added_h, _ = ingest.merge_overrides({"hidden": ["새로 감출 것"], "renamed": []})
            text = open(ingest.OVERRIDES_PATH, encoding="utf-8").read()
            check("먼저 감춘 것은 그대로 남는다", "오늘 한 것" in text and added_h == ["새로 감출 것"], text)

            _, added_r = ingest.merge_overrides({"hidden": [], "renamed": [{"from": "A", "to": "A"}]})
            check("자기 자신으로 바꾸기는 받지 않는다", added_r == [], added_r)

            check("지도 절이 없으면 아무것도 안 한다",
                  ingest.build_overrides({"title": "[설정] x", "body": "## 주제\n- 아무거나"}) == {},
                  "")
        finally:
            os.chdir(cwd)

    print()
    if FAILED:
        print(f"❌ 실패 {len(FAILED)}: " + ", ".join(FAILED))
        return 1
    print("✅ 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
