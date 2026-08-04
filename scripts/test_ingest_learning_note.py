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
import os
import sys

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

    print()
    if FAILED:
        print(f"❌ 실패 {len(FAILED)}: " + ", ".join(FAILED))
        return 1
    print("✅ 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
