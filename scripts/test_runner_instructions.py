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
BUDGET = 7000       # 우리 예산 — 남는 1,000자는 `# 이 학습자` 블록 몫

# 모드 대본은 지침 박스가 아니라 저장소 파일이다(러너가 readFile로 읽는다).
# 그래서 길이 예산을 먹지 않고, 고쳐도 지침을 다시 붙여넣지 않아도 된다.
MODES = ("runner/paper-mode.md", "runner/exam-mode.md", "runner/topics.md",
         "runner/subject-mode.md", "runner/research-mode.md")

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
    "[학습]",
    "[설정]",
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

check(f"`# 이 학습자` 블록 자리가 남는다 ({HARD_LIMIT - len(base)}자)",
      len(base) < HARD_LIMIT, "한도를 이미 넘었다")

missing = [c for c in CONTRACT if c not in base]
check("CI가 읽는 계약 문자열이 전부 살아 있다", not missing, f"사라진 것: {missing}")

# 모드 대본은 파일로 존재해야 하고, 지침은 그 파일을 읽으라고 말해야 한다.
# 둘 중 하나가 빠지면 러너는 논문/시험 세션에서 대본 없이 진행한다(조용한 실패).
for rel in MODES:
    path = ROOT / rel
    check(f"모드 대본이 있다 — {rel}", path.exists(), "파일이 없다")
    check(f"지침이 {rel}를 읽으라고 말한다", rel in base, "진입점이 없어 대본이 죽는다")

# 논문 모드가 CI에 넘기는 절 이름 — ingest_learning_note.py의 PAPER_SECTIONS와 짝이다.
paper_mode = (ROOT / "runner" / "paper-mode.md").read_text(encoding="utf-8")
paper_contract = ("## 메타", "## 정제본 갱신", "## 주석", "## Parking Lot",
                  "## 아티팩트", "## READING_STATUS 갱신", "[논문]")
missing = [c for c in paper_contract if c not in paper_mode]
check("논문 모드의 절 이름이 전부 살아 있다", not missing, f"사라진 것: {missing}")

# `[자료]` Issue 규약은 과목 모드 대본이 갖는다(지침에서 여기로 옮겼다).
subject_mode = (ROOT / "runner" / "subject-mode.md").read_text(encoding="utf-8")
check("과목 모드가 `[자료]` 증류 규약을 갖고 있다", "[자료]" in subject_mode,
      "증류 Issue 규약이 사라지면 materials/가 영영 안 만들어진다")

# 연구 모드는 새 Issue 종류를 만들지 않는다 — 기존 `[학습]` + `artifact:`를 쓴다.
# 여기서 새 접두어를 지어내면 CI 게이트가 모르는 Issue가 되어 조용히 사라진다.
research_mode = (ROOT / "runner" / "research-mode.md").read_text(encoding="utf-8")
check("연구 모드가 기존 쓰기 계약을 쓴다",
      "artifact:" in research_mode and "[학습]" in research_mode,
      "새 Issue 접두어를 만들면 CI가 못 받는다")
check("연구 모드가 반증 조건을 요구한다", "반증 조건" in research_mode,
      "반증 조건이 없으면 무엇이 나와도 '맞았다'가 된다")

# ── Action 스키마 ─────────────────────────────────────────────────────────
#
# 2026-08-04 사고: 읽기 경로가 `contents/{path}` 하나였다. 경로 파라미터는 클라이언트가
# 퍼센트 인코딩하므로 `runner/paper-mode.md`가 `runner%2Fpaper-mode.md`로 나가 404가 났다.
# 하위 폴더 파일을 하나도 못 읽고, GPT는 액션을 포기하고 웹 검색으로 넘어갔다.
# 사람 눈으로는 멀쩡해 보이는 스키마라, 이 불변식은 기계가 지켜야 한다.
SCHEMA = ROOT / "runner" / "action-schema.yaml"
if SCHEMA.exists():
    schema_text = SCHEMA.read_text(encoding="utf-8")
    body = schema_text[schema_text.index("openapi:"):]
    paths = re.findall(r"^  (/\S+):", body, re.M)
    check("스키마에 읽기·쓰기 경로가 있다", len(paths) >= 5, f"{len(paths)}개")

    # `{...}` 파라미터가 통째로 한 URL 세그먼트여야 한다. 슬래시를 품는 파라미터
    # (`{path}` 같은 것)는 인코딩되어 반드시 404가 난다.
    bad = [p for p in paths if re.search(r"\{[^}]*(path|filepath|full)[^}]*\}", p)]
    check("슬래시를 품는 경로 파라미터가 없다", not bad, f"{bad} — 폴더를 URL에 고정해라")

    # 지침·대본이 부르는 액션 이름이 스키마에 실제로 있어야 한다.
    op_ids = set(re.findall(r"operationId:\s*(\w+)", body))
    referenced = set()
    for rel in ("runner/instructions.md", *MODES):
        text = (ROOT / rel).read_text(encoding="utf-8")
        referenced |= {m for m in re.findall(r"`(read\w+|listPapers|createNote|appendNote|closeNote)`", text)}
    missing_ops = sorted(referenced - op_ids)
    check("지침이 부르는 액션이 스키마에 전부 있다", not missing_ops, f"없는 것: {missing_ops}")

if ADDENDUM.exists():
    text = ADDENDUM.read_text(encoding="utf-8")
    check("toeic addendum은 붙여넣기가 아니라 모드 파일을 가리킨다",
          "runner/exam-mode.md" in text, "옛 '이어서 붙여넣기' 안내가 남아 있다")

print()
if failures:
    sys.exit(f"실패 {len(failures)}건")
print("전부 통과")
