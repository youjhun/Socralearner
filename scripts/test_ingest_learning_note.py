#!/usr/bin/env python3
"""ingest_learning_note 회귀 테스트 — 파일럿 증거 필드가 노트까지 살아남는가.

실행: python3 scripts/test_ingest_learning_note.py

이 테스트가 지키는 것 (2026-08-03 파일럿 계약):
  ① `artifact:` 지시행이 frontmatter로 올라가고 본문에서는 사라진다
     — `time_to_first_artifact`의 유일한 원자료라, 본문에 묻히면 셀 수 없다.
  ② `## 전이 시도` · `## 7일 재검증`이 **손대지 않은 채** daily 노트에 남는다
     — 수집기가 이 절들을 모르므로 통과만 하면 된다. 그 "모름"을 못박아 둔다.
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
"""

BODY_MINIMAL = """## 목표
- 기초 잡기

## 오늘 직접 학습한 지식
1. 사인파의 정의

## 취약 영역
- 아직 없음

## 다음 복습 질문
1. 진폭이란
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

    print()
    if FAILED:
        print(f"❌ 실패 {len(FAILED)}: " + ", ".join(FAILED))
        return 1
    print("✅ 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
