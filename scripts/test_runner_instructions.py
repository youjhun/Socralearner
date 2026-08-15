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
         "runner/subject-mode.md", "runner/research-mode.md",
         "runner/concept-map.md")

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
    # 2026-08-05: 액션 3홉(createNote/appendNote/closeNote)과 읽기 8종이 MCP 도구
    # 2개로 바뀌었다. 제목 접두어(`[학습]`·`[설정]`)는 이제 **서버가** 붙이므로 지침에서
    # 사라졌고, 대신 지침이 부르는 도구 이름이 계약이다.
    "get_state",
    "read_doc",
    "save_session",
    "continuationToken",
    # 2026-08-15: `artifact`·`turns`는 이제 **필드**다. 예전에는 지침이 "본문 맨 첫 줄에
    # `artifact:`를 적어라"라고 했는데, MCP 경로에서는 본문을 **서버가 렌더하므로**
    # 러너가 적을 자리가 없었다(감사 F-1). 지시행을 찍는 것은 `mcp-core/render.ts`이고
    # 지침은 필드 이름만 알면 된다.
    "artifact",
    "turns",
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

# 첫 응답의 모양 — 다섯 박자 (2026-08-14)
#
# 유지훈: *"우리 처음 학습이나 읽기 시작할때 프롬프트가 한 줄 나오고 끝이다. … 복습겸 짧게
# 하고(이전에 여기까지 했고 이걸 배웠다. 오늘은 여기로 넘어갈 차례다. 오늘의 목표는 이걸
# 이해하는거야. 그리고 내용 정리후 소크라테스 질문.)"*
#
# 앱의 핸드오프(`lib/knowledge/runner.ts`)가 같은 형식을 싣지만, **버튼을 안 거치고
# ChatGPT에서 직접 "오늘 세션 시작"이라고 치는 경로**는 이 대본이 유일한 근거다.
for mode_name, text in (("논문 모드", paper_mode), ("과목 모드", subject_mode)):
    for needle, why in [
        ("첫 응답의 모양", "여는 형식 절이 사라지면 세션이 다시 질문 한 줄로 끝난다"),
        ("지난 자리", "복습이 없으면 «이전에 여기까지 했고»가 안 나온다"),
        ("오늘 자리", "오늘 어디로 넘어가는지를 말하지 않으면 위치 감각이 없다"),
        ("오늘 목표", "완료 조건이 없으면 «했다»를 판정할 수 없다"),
        ("짧은 정리", "정리 단계가 빠지면 유지훈이 고른 형식이 아니다"),
    ]:
        check(f"{mode_name}가 「{needle}」를 갖고 있다", needle in text, why)

    # ⚠️ 가장 중요한 잠금 — 완화가 **판정 기준**까지 흘러내리면 이 앱은 요약기가 된다.
    #    말하는 순서만 완화했고 승급 기준은 그대로라는 것이 이 두 문장에 걸려 있다.
    check(f"{mode_name}가 정리에 예산을 준다(5~8줄)", "5~8줄" in text,
          "예산이 없으면 러너가 오늘 범위를 통째로 설명하고 원문 읽기를 대신한다")
    check(f"{mode_name}가 「정리를 읽은 것은 통과가 아니다」를 못박는다",
          "통과가 아니다" in text,
          "이 줄이 빠지면 강의를 들은 것만으로 「설명가능」 승급이 일어난다")
    check(f"{mode_name}가 근거 없는 칸을 지어내지 말라고 한다",
          "지어내지 말고" in text,
          "첫 세션에는 지난 자리가 없다 — 지어내면 그것이 곧 거짓 기록이다")

# 자료의 파킹랏 — 앱의 읽기 화면이 렉처노트·교재에 남긴 「막혔다」.
#
# 2026-08-14: 파일은 정확히 만들어지는데 **러너가 경로를 알 길이 없어 써 놓고도 못 봤다.**
# `MaterialRef`에 경로를 실어 고쳤지만(Topdown 쪽), 경로만 주면 안 읽는다 — 세션을 열 때
# 읽으라고 대본이 시켜야 한다.
for needle, why in [
    ("materials[].parkingLot", "저장소 전체 큐와 자료별 파킹랏을 구분하지 않으면 러너가 섞는다"),
    ("직접 「막혔다」로 그은 것", "이게 요약이 아니라 학습자 본인의 표시라는 것이 근거의 힘이다"),
]:
    check(f"과목 모드가 「{needle}」를 갖고 있다", needle in subject_mode, why)

check("과목 모드가 자료 파킹랏을 세션 열 때 읽으라고 한다",
      "`parkingLot`이 있으면 읽는다" in subject_mode,
      "경로를 줘도 읽으라고 안 하면 러너는 안 읽는다 — 그게 이 라운드에서 고친 것이다")

# 원문 근거 계약 — 이게 빠지면 러너가 요약으로 시험을 내고, 요약에서 빠진 것은
# 학습자가 자기가 모르는 줄도 모르게 된다. 계약의 손잡이 이름들을 못박는다.
for needle, why in [
    ("원문에 근거해 진행한다", "계약 절이 사라지면 러너가 증류본만 읽는다"),
    ("materialStatus", "오늘 어디부터인지를 짐작하게 되면 이미 한 절을 또 한다"),
    ("## 원문 목차", "절을 고를 지도가 없으면 원문을 통째로 받게 된다"),
    ("sourceAnchors", "앵커가 없으면 원문을 읽었는지 확인할 길이 없다"),
    ("## 자료 진도 갱신", "진도를 안 남기면 다음 세션이 짐작한다"),
    # 설계도 → 파킹랏 → 과목. 이 순서가 곧 우선순위다(`PARKING-LOT.md`가 정한 것).
    ("learningSpec", "설계도를 안 보면 순서를 세션마다 다시 지어낸다"),
    ("## 학습 설계도", "통과한 단계를 되돌려 보낼 절이 없으면 같은 단계를 또 집는다"),
    ("courses", "내 과목 노트를 안 보면 표준 커리큘럼을 지어낸다"),
    ("parkingLot", "막힌 것을 안 집으면 큐가 쌓인 채로 남는다"),
]:
    check(f"과목 모드에 `{needle}`가 있다", needle in subject_mode, why)

# 논문도 같은 계약을 따른다 — 문구가 갈리면 종류마다 다르게 행동한다.
paper_mode_text = (ROOT / "runner" / "paper-mode.md").read_text(encoding="utf-8")
check("논문 모드가 원문 근거 계약을 가리킨다",
      "원문에 근거해 진행한다" in paper_mode_text and "subject-mode.md" in paper_mode_text,
      "논문만 계약 밖이면 정제본(=학습자가 이미 아는 것)만 보고 시험을 내게 된다")

# 연구 모드는 새 Issue 종류를 만들지 않는다 — 기존 `[학습]` + `artifact:`를 쓴다.
# 여기서 새 접두어를 지어내면 CI 게이트가 모르는 Issue가 되어 조용히 사라진다.
research_mode = (ROOT / "runner" / "research-mode.md").read_text(encoding="utf-8")
check("연구 모드가 기존 쓰기 계약을 쓴다",
      "artifact:" in research_mode and "[학습]" in research_mode,
      "새 Issue 접두어를 만들면 CI가 못 받는다")
check("연구 모드가 반증 조건을 요구한다", "반증 조건" in research_mode,
      "반증 조건이 없으면 무엇이 나와도 '맞았다'가 된다")

# 2026-08-05: 개념 지도는 **학습 로그가 아니라 커리큘럼**이 됐다(유지훈).
# 조각으로 자라면 "이 개념이 대체 어디에 있는 거지"에 답할 수 없다.
concept_map = (ROOT / "runner" / "concept-map.md").read_text(encoding="utf-8")
check("개념 지도가 커리큘럼임을 밝힌다", "커리큘럼" in concept_map,
      "지도가 다시 학습 로그로 자란다")
check("아직 안 배운 개념도 넣으라고 한다", "안 배운 개념도" in concept_map,
      "미래 길목이 그래프에 안 서면 로드맵이 안 된다")
# 지침 본문에서 뺐으므로 대본이 그 규칙을 갖고 있어야 한다.
for rule in ("개념의 단위", "간선", "분야"):
    check(f"대본이 `{rule}` 규칙을 갖고 있다", rule in concept_map,
          "지침에서 뺀 규칙이 어디에도 없다")
# `[설정]`이 아는 절은 트랙·분야·주제뿐이다 — 개념 지도를 거기 보내면 수집이 실패한다.
check("개념 지도를 `[설정]`로 보내지 말라고 한다", "`[설정]` Issue로 보내지 마라" in concept_map,
      "러너가 없는 설정 종류를 지어낸다")

# 러너가 스스로 "내 지침이 낡았다"를 알아채는 경로. 지침 재붙여넣기는 자동화가 불가능한
# 유일한 수동 작업이라, 아무도 안 알려 주면 옛 지침으로 몇 주씩 돈다.
check("세션 시작에 CHANGELOG를 읽는다", "CHANGELOG.md" in base,
      "낡은 지침을 아무도 알려 주지 않는다")
check("갱신일과 비교한다", "지침 갱신일" in base,
      "비교 기준이 없으면 매 세션 잔소리가 된다")
# 러너가 내용을 다 만들어 놓고 "권한이 없다"며 출력만 하고 끝낸 사고(2026-08-05).
# 파일 API가 없는 것이지 Issue는 늘 쓸 수 있다.
check("못 쓴다고 답하지 말라고 못박는다", '"못 쓴다"고 답하지 마라' in base,
      "러너가 기록을 포기하고 사용자에게 손으로 옮기라고 한다")
# 러너가 액션을 파이썬으로 import하려다 실패하고 웹 검색으로 갈아탄 사고(2026-08-05).
# 검색 결과는 이 학습자의 기록이 아니라, 그렇게 진행하면 남의 내용으로 세션이 돈다.
check("도구를 코드로 부르지 말라고 못박는다", "코드 인터프리터" in base,
      "러너가 도구를 파이썬에서 import하려 한다")
# 2026-08-05: 없는 파일이 404로 보이면 러너가 도구를 포기하고 웹으로 샜다.
# 이제 `missing`으로 오므로, 지침이 그 구분을 말해야 한다.
check("없음과 실패를 구분하라고 말한다", "missing" in base,
      "러너가 빈 저장소를 '읽기 실패'로 보고 웹 검색으로 간다")
check("상태를 붙여넣어 달라고 하지 말라고 못박는다", "붙여넣어 달라고 요청하지 마라" in base,
      "러너가 사용자에게 STATUS를 손으로 넣게 시킨다")
check("실패해도 웹 검색으로 갈아타지 말라고 한다", "웹 검색으로 갈아타지" in base,
      "검색 결과가 학습자의 기록 행세를 한다")

check("개념 지도의 목적지를 밝힌다", "STATUS.md가 아니라" in base,
      "사용자가 STATUS라고 말하면 러너가 목적지를 헷갈린다")

check("낡아도 세션을 막지 않는다", "세션은 그대로 진행한다" in base,
      "알림이 공부를 막으면 사람은 알림을 끈다")
check("CHANGELOG가 루트 읽기 목록에 있다",
      "CHANGELOG.md" in (ROOT / "runner" / "action-schema.yaml").read_text(encoding="utf-8"),
      "스키마가 안내하지 않으면 모델이 그 파일을 안 읽는다")

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

    check("옛 스키마에 폐기 표시가 있다", "폐기 예정" in schema_text,
          "새 사용자가 폐기된 경로를 따라간다")

# 지침·대본이 부르는 도구 이름이 실제 MCP 도구여야 한다. 없는 이름을 부르면 러너는
# 도구가 고장난 줄 알고 웹 검색으로 간다 — 옛 404 사고와 같은 결말이다.
MCP_TOOLS = {"get_state", "read_doc", "get_paper", "save_session"}
referenced = set()
for rel in ("runner/instructions.md", *MODES):
    text = (ROOT / rel).read_text(encoding="utf-8")
    referenced |= {m for m in re.findall(r"`(get_state|read_doc|get_paper|save_session|readFile|readRunnerFile|readPapersFile|readPaperFile|readDailyFile|readTrackDaily|readMaterialFile|listPapers|createNote|appendNote|closeNote)`", text)}
unknown = sorted(referenced - MCP_TOOLS)
check("지침이 부르는 도구가 전부 실재한다", not unknown, f"없는 도구: {unknown}")

if ADDENDUM.exists():
    text = ADDENDUM.read_text(encoding="utf-8")
    check("toeic addendum은 붙여넣기가 아니라 모드 파일을 가리킨다",
          "runner/exam-mode.md" in text, "옛 '이어서 붙여넣기' 안내가 남아 있다")

print()
if failures:
    sys.exit(f"실패 {len(failures)}건")
print("전부 통과")
