#!/usr/bin/env python3
"""러너 지침이 ChatGPT 지침 칸에 **통째로** 들어가는지 지킨다.

왜 필요한가 (2026-08-04):
Custom GPT의 Instructions 칸은 **8,000자**가 한도다. 넘으면 오류가 뜨는 게 아니라
붙여넣기가 **조용히 잘린다** — 잘린 뒤쪽이 하필 쓰기 계약(본문 형식)이라 GPT가
Issue를 이상한 헤딩으로 써도 아무도 모른다. 실제로 지침이 10,640자까지 자라 있었다.
길이는 사람이 눈으로 재는 것이 아니라 기계가 재야 한다.

재는 것 두 가지:
  · 회색 박스(붙여넣는 본문)가 예산 안인가
  · 시험 트랙(박스 − 논문 대본 + toeic addendum)도 한도 안인가
  · CI가 읽는 계약 문자열(헤딩 이름·Issue 제목·액션 이름)이 살아 있는가

실행:
    python3 scripts/test_runner_instructions.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTRUCTIONS = ROOT / "runner" / "instructions.md"
ADDENDUM = ROOT / "presets" / "toeic" / "runner-addendum.md"

HARD_LIMIT = 8000   # ChatGPT Custom GPT Instructions 칸의 실제 한도
BUDGET = 7400       # 우리 예산 — 남는 600자는 `# 이 학습자` 블록 몫

# CI(scripts/ingest_learning_note.py 등)가 이 이름으로 노트를 읽는다.
# 하나라도 사라지면 그 절은 영영 파일로 만들어지지 않는다.
CONTRACT = (
    "## 목표",
    "## 예측 — 내가 먼저 답한 것",
    "## 오늘 직접 학습한 지식",
    "## 교정 및 보완",
    "## 퀴즈",
    "## 취약 영역",
    "## 전이 시도",
    "## 7일 재검증",
    "## 다음 복습 질문",
    "## 현재 이해 수준",
    "## 미해결 질문",
    "## STATUS 갱신",
    "### 오늘 할 것",
    "## 개념 지도",
    "## 드릴 항목",
    "## 이해도 승급",
    "## 정제본 갱신",
    "## 주석",
    "## READING_STATUS 갱신",
    "[학습]",
    "[자료]",
    "[논문]",
    "createNote",
    "appendNote",
    "closeNote",
    "readFile",
    "artifact:",
)

failures = []


def check(label, ok, detail=""):
    print(f"{'✅' if ok else '❌'} {label}{'' if ok else ' — ' + detail}")
    if not ok:
        failures.append(label)


def block(path):
    """마크다운 파일의 첫 회색 박스(붙여넣는 본문)를 꺼낸다."""
    blocks = re.findall(r"\n```\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    if not blocks:
        sys.exit(f"회색 박스를 찾지 못했다: {path}")
    return blocks[0]


base = block(INSTRUCTIONS)
check(f"지침 본문이 예산 안 ({len(base)} ≤ {BUDGET}자)", len(base) <= BUDGET,
      f"{len(base) - BUDGET}자 초과 — 늘린 만큼 다른 줄을 줄여라")

if ADDENDUM.exists():
    addendum = block(ADDENDUM)
    # 시험 트랙은 논문 대본을 빼고 addendum을 이어 붙인다(지침 머리말의 안내와 같다).
    i, j = base.index("# 논문·연구실 모드"), base.index("# 세션 진행")
    exam = len(base) - (j - i) + len(addendum)
    check(f"시험 트랙 붙여넣기도 한도 안 ({exam} < {HARD_LIMIT}자)", exam < HARD_LIMIT,
          "논문 대본을 빼도 넘는다 — addendum이나 본문을 줄여야 한다")

missing = [c for c in CONTRACT if c not in base]
check("CI가 읽는 계약 문자열이 전부 살아 있다", not missing, f"사라진 것: {missing}")

print()
if failures:
    sys.exit(f"실패 {len(failures)}건")
print("전부 통과")
