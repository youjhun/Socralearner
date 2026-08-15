#!/usr/bin/env python3
"""학습 노트 수집기 — GitHub Issue(본문 + 코멘트) → `daily/` 세션 로그.

왜 이 경로인가:
러너(특히 ChatGPT Custom GPT)의 기존 쓰기 경로는 GitHub Contents API였다. 그 API는
파일 생성·수정 시 **본문 전체를 base64 한 덩어리로** 요구한다(부분 패치 없음). 즉 노트
본문이 모델의 출력 토큰을 두 번(마크다운 → base64) 통과해야 하고, 길어질수록
① 인코딩이 어긋나거나 ② 인자 문자열이 잘려 JSON이 깨지고 ③ 수정은 blob sha까지
읽어와야 해서 실패한다. 그 결과 긴 세션일수록 커밋이 안 되고, 러너는 살아남는 길이인
"3줄 요약"으로 스스로 줄였다(2026-07-25 status-delta 파일이 그 흔적).
`consolidate_mastery.py`가 mastery.md에 대해 이미 같은 문제를 조각+CI로 풀었고,
이 스크립트는 그 패턴을 **세션 로그 생성 경로 전체**로 확장한다.

새 계약: 러너는 Issue에 **평문**을 쓴다(base64 없음, sha 없음, 읽기-수정-쓰기 없음).
길면 코멘트로 이어 쓴다 — 요청 하나하나가 짧아 길이가 실패 원인이 되지 않는다.
파일을 만드는 것은 모델이 아니라 이 결정론적 스크립트다(LLM 토큰 0).

실행: CI(.github/workflows/learning-note-ingest.yml)가 Issue 종료 또는 `/기록` 코멘트에 실행.
로컬: `python3 scripts/ingest_learning_note.py --payload payload.json --today 2026-08-01`

payload.json 형식:
    {"number": 12, "title": "[학습] 2026-08-01 lda-scatter", "body": "...", "html_url": "...",
     "comments": [{"author": "youjhun", "body": "..."}]}
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

DAILY_DIR = "daily"
MATERIALS_DIR = "materials"
PAPERS_DIR = "papers"
STATUS_PATH = "STATUS.md"
LEARNING_ROOT = "."

# 대시보드(dashboard/lib/data/learning.ts)와 음성 로더가 키로 삼는 정규 헤딩.
# 없으면 "기록됐는데 안 읽히는" 조용한 실패가 되므로, 막지 않고 채워 넣고 경고한다.
# 2026-08-04: `현재 이해 수준`·`미해결 질문`을 추가했다. 유지훈 개인 러너는 이미 둘을
# 정규 헤딩으로 요구하는데 템플릿만 빠져 있어, 배포판 사용자의 노트에는 "지금 어디까지
# 이해했나"와 "다음 세션의 시작점"이 남지 않았다. 둘은 다음 세션이 이어붙는 자리라
# 빠지면 매 세션이 처음부터 시작된다.
REQUIRED_HEADINGS = [
    "오늘 직접 학습한 지식",
    "취약 영역",
    "다음 복습 질문",
    "현재 이해 수준",
    "미해결 질문",
]

STATUS_SECTION = "STATUS 갱신"
MASTERY_SECTION = "이해도 승급"

# ─────────────────────── STATUS 승격 (노트 → STATUS.md) ───────────────────────
#
# 2026-08-04: STATUS.md의 쓰기 계약은 러너에게 넷을 요구하는데(오늘 목표·약점 top5·
# 복습 top5·최근 궤적), `runner/instructions.md`의 노트 서식에는 `### 오늘 할 것`
# 하나뿐이었다. 나머지 셋은 러너가 쓰지 않으니 패치할 내용이 없었고, STATUS.md는
# 템플릿 자리표시자 그대로 남았다 — 앱에서 "지금 약한 것: 아직 없습니다"가 계속 뜬
# 원인이다(유지훈 2026-08-04 보고).
#
# 고치는 방향은 서식에 절을 더 요구하는 것이 **아니다**. 약점과 복습 질문은 이미
# `## 취약 영역` · `## 다음 복습 질문`으로 노트에 들어오고 CI가 필수 헤딩으로 검사까지
# 한다. 같은 내용을 한 노트에 두 번 쓰게 하면 두 곳이 어긋나고, 한 곳을 빠뜨리면 이
# 버그가 그대로 재발한다.
#
# 그래서 이 repo가 이미 택한 원칙을 따른다 — **큰 쓰기는 모델이 아니라 CI가
# 결정론적으로**(learning-note-ingest.yml 헤더의 설계 근거). 러너는 자기만 아는 것
# (`오늘 할 것`)만 쓰고, 나머지는 여기서 노트로부터 유도한다.
#
# 러너가 직접 쓴 절이 있으면 **그쪽이 이긴다** — 유도는 빈 자리를 메우는 것이지
# 사람이 쓴 것을 덮는 것이 아니다.
STATUS_DERIVED = [
    # (노트 본문의 절, STATUS.md의 절, 최대 줄 수)
    ("취약 영역", "지금 약한 것", 5),
    ("다음 복습 질문", "다음 복습 질문", 5),
]

# 2026-08-05: `지금 약한 것`은 **교체가 아니라 누적**이다.
#
# 그 전에는 `apply_section_patch`가 절 본문을 통째로 갈아 끼웠다. 그래서 이번 세션에서
# 다루지 않은 약점은 조용히 사라졌고, 러너는 다음 세션에 그것을 다시 만나지 못했다 —
# STATUS.md는 러너가 세션 시작에 읽는 유일한 파일이라, 여기서 지워지면 영영 안 돌아온다.
# (파일럿 저장소에서 KCL·KVL이 `암기`로 남은 채 테브난만 두 세션 연속으로 돌았다.)
#
# 약점은 "이번 세션에서 나온 것"이 아니라 **"아직 안 풀린 것"**이다. 새 것을 앞에 놓고
# 이어 붙이되 상한을 둔다 — 무한정 쌓이면 이 파일이 커져 러너가 매 세션 통째로 읽는
# 비용이 오른다(작게 유지하는 것이 이 파일의 존재 이유다). 상한 밖으로 밀려난 것은
# `mastery.md`에 남아 있으므로 사라지는 것이 아니다.
STATUS_ACCUMULATED = {"지금 약한 것": 5}

TRAJECTORY_SECTION = "최근 궤적"
# 최근 궤적은 교체가 아니라 누적이다. 무한정 쌓으면 STATUS.md가 커져 러너가 매 세션
# 통째로 읽는 비용이 오르므로(이 파일의 존재 이유가 "작게 유지"다) 최근 것만 남긴다.
TRAJECTORY_KEEP = 7

# `## 드릴 항목` — 회상 대상(단어 뜻·연호·값)은 개념 지도가 아니라 여기로 온다.
# 2026-08-03: 토익 트랙에서 지식 그래프가 단어 단위로 생성된 것을 고치며 생긴 경로다.
# 개념의 단위 정의는 runner/instructions.md의 "개념의 단위"에 있다. 여기는 그 저장 경로일 뿐이다.
DRILLS_SECTION = "드릴 항목"
DRILLS_PATH = "drills.md"

# `## 개념 지도` — `build_concepts.py`가 선수관계를 읽어 가는 절(그쪽 `SECTION`과 같은 값).
# 여기서는 `[자료]` 본문이 실제로 증류됐는지 가리는 데 쓴다(`is_distilled`).
CONCEPT_MAP_SECTION = "개념 지도"

# `## 원문` — 증류와 원문의 경계. 앱이 초안을 이 모양으로 만든다(issueDraft.ts).
SOURCE_SECTION = "원문"
DRILLS_HEADER = [
    "---",
    'title: "드릴 항목 (회상 대상)"',
    "kind: drills",
    "---",
    "",
    "# 드릴 항목 — 그래프에 넣지 않는 것",
    "",
    "> 단어 뜻·연호·공식의 값처럼 **답이 하나로 끝나고 위계에 참여하지 않는 것**을 모은다.",
    "> 개념 그래프는 *설명 대상*만 담는다 — 여기 있는 것은 복습에는 쓰되 노드가 되지 않는다.",
    "> 판정 기준은 `runner/instructions.md`의 「개념의 단위」를 본다.",
    "",
]
# ─────────────────────────── 논문 세션 (`[논문]`) ───────────────────────────
#
# 2026-08-04: 템플릿 CI의 게이트가 `[학습]`·`[자료]`만 통과시켜, 논문 러너가 만든
# `[논문]` Issue는 **워크플로가 아예 돌지 않고 조용히 사라졌다.** 유지훈 본인은 Hudson에
# 별도 경로가 있어 문제를 못 겪지만, 이 템플릿만 쓰는 사용자에게는 논문 트랙 전체가
# 기록되지 않는 상태였다. 배포판이 곧 제품이므로 여기서 받는다.
#
# 논문은 세션이 여러 번에 걸쳐 한 편을 관통한다(Methods → Results → …). 그래서 학습
# 노트처럼 날짜 하나에 접지 않고 **논문별 폴더**에 세션을 쌓는다.
#
#   papers/<slug>/sessions/YYYY-MM-DD-<섹션>.md   세션 원문 — 실패하지 않는 경로
#   papers/<slug>/paper.md                        정제본 — 검증된 이해만, 절 단위 교체
#   papers/<slug>/annotations.md                  인용 + 코멘트, 쌓인다
#   papers/READING_STATUS.md                      지금 읽는 논문·어디까지·다음 세션
#   papers/<slug>/parking-lot.md                  미뤄 둔 선수지식 — 항목 단위로 병합
#   papers/<slug>/meta.yaml                       서지 정보 + 현재 이해 단계
#   papers/<slug>/artifacts/                      시각 아티팩트 — 제목마다 파일 하나
#
# 2026-08-04(2): Parking Lot·아티팩트·meta는 `runner/paper-mode.md`의 루프가 실제로
# 만들어 내는 산출물인데 받는 곳이 없어 세션 원문에만 묻혀 있었다. 묻히면 다음 세션의
# 러너가 못 찾고, 못 찾으면 같은 선수지식을 매번 다시 미룬다.
#
# 2026-08-14: `root: materials` 지시행을 주면 위 경로가 통째로 `materials/<slug>/`로 간다
# (`parse_root`). 앱 읽기 화면이 렉처노트·교재에 남긴 파킹랏·주석을 올리기 시작해서다 —
# 그전에는 파킹랏을 받는 곳이 `papers/`뿐이라 자료에 남긴 표시를 러너가 볼 수 없었다.
# `READING_STATUS 갱신`만은 예외로 `papers/READING_STATUS.md`에 남는다(자료 진도는
# `## 자료 진도 갱신`이라는 다른 기계가 담당한다).
PAPER_SECTIONS = {
    "정제본 갱신": "paper.md",
    "주석": "annotations.md",
}
PARKING_SECTION = "Parking Lot"
ARTIFACT_SECTION = "아티팩트"
META_SECTION = "메타"
# meta.yaml에 받는 키. 모르는 키는 버린다 — 러너가 지어낸 필드로 파일이 자라지 않게.
META_KEYS = ("title", "authors", "year", "venue", "link", "understanding", "flow", "next_section")
UNDERSTANDING = ("미이해", "부분 이해", "기능적 이해", "비판적 이해")

# 논문 흐름 5단계 — **사용자가 자기 말로 설명해 통과한 단계만** 여기 쌓인다.
#
# 왜 단계 이름의 나열인가 (2026-08-15): 파일럿 논문 트랙의 완료 조건이 "논문의 흐름을
# 실제로 이해했는가"인데, `understanding`의 4단계는 그것을 통째로 뭉갠다 — 방법만 알고
# 실험 설계를 못 읽는 사람과 그 반대인 사람이 같은 「부분 이해」로 접힌다. 다섯 칸으로
# 나눠 두면 **어디서 막히는지가 사람마다 다르게 보이고**, 그것이 다음 개선의 재료다.
#
# 점수를 매기지 않는 이유는 이 저장소의 다른 판정과 같다 — 숫자는 정확해 보이지만
# 설명하지 못한다. 통과한 단계를 적고, 안 적힌 것은 아직 아닌 것이다.
FLOW_STEPS = ("문제", "한계", "방법", "실험", "결과")
READING_STATUS_SECTION = "READING_STATUS 갱신"
READING_STATUS_PATH = os.path.join(PAPERS_DIR, "READING_STATUS.md")

# 자료(렉노·교재)의 진도. 논문이 `papers/READING_STATUS.md`로 하던 것과 **같은 기계**다 —
# 세션 노트에 절을 하나 남기면 CI가 파일에 옮겨 적는다.
#
# 왜 필요한가: 원문을 절 단위로 읽게 되면서 "오늘 어느 절부터인가"가 세션의 첫 물음이 됐다.
# 기록이 없으면 러너가 daily 노트에서 짐작해야 하고, 짐작이 틀리면 이미 한 절을 또 한다.
MATERIAL_STATUS_SECTION = "자료 진도 갱신"
MATERIAL_STATUS_PATH = os.path.join(MATERIALS_DIR, "READING_STATUS.md")

# 학습 설계도 — **순서의 SSOT.** `mode: topdown`이 목표 한 줄에서 큰 그림→개념 분해→순서
# →검증기준으로 경로를 만든다. 논문도 자료도 파킹랏도 없는 사람의 시작점이 이 파일이다.
#
# 우선순위는 `PARKING-LOT.md`가 이미 정해 두었다 — *"학습 설계도의 순서는 근거를 가진
# 가설이고, 큐는 그것을 보조한다."* 설계도=주 · 파킹랏=보조 · `courses/`=재료.
#
# 왜 여기 오는가(2026-08-10): 이 파일이 `git add` 범위에 없어서 **손으로만 갱신됐다.**
# 그래서 `[다음]`·`[완료]` 표시가 세션이 진행돼도 움직이지 않았다. 자료 진도(위)와 같은
# 기계를 그대로 쓴다 — 절을 하나 남기면 CI가 파일에 옮겨 적는다.
LEARNING_SPEC_SECTION = "학습 설계도"
LEARNING_SPEC_PATH = "learning-spec.md"

# ─────────────────────────── 설정 (`[설정]`) ───────────────────────────
#
# 2026-08-04: `topics.yaml`을 사람이 손으로 쓰게 하는 것이 병목이었다. YAML 문법이
# 깨지고, 영어 검색어를 짓기 번거롭고, 무엇보다 **분야 고정**을 사람이 할 리 없다.
# 러너(이미 LLM이다)가 만들어 평문 Issue로 넘기고, 파일은 여기서 결정론적으로 쓴다.
# 학습 노트와 같은 계열 — 모델은 평문만, 파일은 CI.
TOPICS_PATH = "topics.yaml"
TOPICS_SECTION = "주제"
TOPIC_FIELDS = ("query", "seed", "topics", "field", "exclude")

# ─────────────────────────── 학습 트랙 ───────────────────────────
#
# 2026-08-04: 전자공학과 영어가 `daily/` 한 폴더에 섞여 쌓였다. 세션 노트가 뒤엉키면
# 러너가 세션 시작에 읽는 맥락도 뒤엉키고("지금 뭘 공부하는 중이지?"), 개념 지도도
# 한 그래프에 서로 무관한 두 주제가 들어간다. 사람에게도 기계에게도 읽히지 않는다.
#
# 트랙은 **학습자가 정하는 서랍**이다. 앱이나 러너가 임의로 만들지 않는다 —
# `tracks.yaml`에 있는 것만 폴더가 되고, 세션은 `track:` 지시행으로 자기 서랍을 고른다.
TRACKS_PATH = "tracks.yaml"
TRACKS_SECTION = "트랙"
TRACK_FIELDS = ("label", "mode", "goal")

# 2026-08-05: `subjects.yaml` — 그래프의 **색**이 되는 분야.
#
# 러너가 `## 개념 지도`의 `###` 소제목을 매번 새로 지어서 같은 것이 여러 조각으로
# 갈라졌다(파일럿에서 실제로 "회로 등가화 6 · 전자회로 5 · 전자회로 기초 4 · 미분류 22"가
# 나왔다 — 앞의 셋은 다 같은 전자회로다). 합치는 표는 이미 `build_concepts`가 읽는데,
# **그 표를 채울 쓰기 경로가 없었다.** 여기가 그 경로다.
#
# 형식이 트랙·주제와 다른 이유: 이건 id를 정하는 일이 아니라 **묶는 일**이다.
# 대표 이름 아래에 "이렇게 적혀도 같은 것"을 나열한다.
#
#     ## 분야
#     ### 전자회로
#     - 회로 등가화
#     - 전자회로 기초
#
# 대주제 묶음은 **사람이 한다**(유지훈 2026-08-05) — 러너가 마음대로 합치면 학습자가
# 일부러 나눠 둔 것까지 뭉갠다.
SUBJECTS_PATH = "subjects.yaml"

# 2026-08-07: 지식 그래프에서 노드를 감추거나 이름을 합치는 곳. 노드는 daily 노트에서
# 매번 다시 만들어지므로 "삭제"는 노트를 고치는 일이 되는데, 그건 기록을 거짓으로 만든다.
# 그래서 지도 위에 얇게 덮는다 — 되돌리려면 이 파일에서 한 줄 지우면 된다.
OVERRIDES_PATH = "concepts-overrides.yaml"
OVERRIDES_SECTION = "지도"
SUBJECTS_SECTION = "분야"

BOT_SUFFIX = "[bot]"
COMMAND_PREFIX = ("/기록", "/ingest", "/skip", "<!-- ingest")


# --------------------------------------------------------------------------- 유틸


def kst_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date().isoformat()


def split_frontmatter(text):
    """(frontmatter dict, 본문) — frontmatter가 없으면 ({}, 원문)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 2)
    if len(parts) < 2:
        return {}, text
    head = parts[0][3:]
    rest = parts[1].lstrip("-").lstrip("\n") if len(parts) == 2 else parts[2].lstrip("\n")
    fm = {}
    for line in head.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line.strip())
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm, rest


def slugify(text):
    """ASCII 슬러그. 한글만 있으면 빈 문자열(호출부가 대체값을 쓴다)."""
    text = re.sub(r"\[[^\]]*\]", " ", text)          # [학습] 같은 말머리 제거
    text = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)   # 날짜 제거
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return "-".join(tokens)[:60].strip("-")


def normalize_heading(text):
    """헤딩 비교용 정규화 — 이모지·괄호주석·공백·마크다운 강조 제거."""
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^\w가-힣]", "", text)
    return text


# --------------------------------------------------------------------------- 조립


def assemble(payload):
    """Issue 본문 + 코멘트를 순서대로 이어 붙인다(청크 프로토콜)."""
    chunks = [payload.get("body") or ""]
    for c in payload.get("comments") or []:
        author = (c.get("author") or "")
        body = (c.get("body") or "").strip()
        if not body or author.endswith(BOT_SUFFIX):
            continue
        if body.startswith(COMMAND_PREFIX):
            continue
        chunks.append(body)
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def pop_section(body, name):
    """`## <name>` 절을 본문에서 떼어내 (남은 본문, 절 내용)으로 돌려준다."""
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and name in line:
            start = i
            break
    if start is None:
        return body, ""

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    section = "\n".join(lines[start + 1:end]).strip()
    return "\n".join(lines[:start] + lines[end:]).strip(), section


def extract_status_patch(body, name=None):
    """`## STATUS 갱신`(또는 지정한 절)을 본문에서 떼어내 {섹션: 내용} 으로 돌려준다."""
    body, section = pop_section(body, name or STATUS_SECTION)
    if not section:
        return body, {}

    patch, current = {}, None
    for line in section.splitlines():
        if line.startswith("### "):
            current = line[4:].strip()
            patch[current] = []
        elif current is not None:
            patch[current].append(line)
    patch = {k: "\n".join(v).strip() for k, v in patch.items() if "\n".join(v).strip()}
    return body, patch


def read_section(body, name):
    """`## <name>` 절의 내용을 **떼어내지 않고** 읽는다(pop_section의 읽기 전용판)."""
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and name in line:
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start + 1:end]).strip()


def _is_empty_marker(text):
    """수집기가 자동 보정한 자리표시자는 내용이 아니다 — 승격하면 거짓이 쌓인다."""
    stripped = text.strip().lstrip("-*0123456789. ").strip()
    return not stripped or stripped in {"(이번 세션 기록 없음)", "(없음)", "없음"}


def derive_status_patch(body, patch):
    """러너가 안 쓴 STATUS 절을 노트 본문에서 유도한다(러너가 쓴 것이 우선)."""
    patch = dict(patch)
    for source, target, limit in STATUS_DERIVED:
        if any(normalize_heading(target) in normalize_heading(k) for k in patch):
            continue  # 러너가 직접 썼다 — 건드리지 않는다
        section = read_section(body, source)
        if not section:
            continue
        items = [ln.strip() for ln in section.splitlines() if ln.strip()]
        items = [ln for ln in items if not ln.lstrip().startswith(">")]
        items = [ln for ln in items if not _is_empty_marker(ln)]
        if not items:
            continue
        numbered = []
        for i, item in enumerate(items[:limit], 1):
            numbered.append(f"{i}. {item.lstrip('-*0123456789. ').strip()}")
        patch[target] = "\n".join(numbered)
    return patch


def append_trajectory(display, date, path, today):
    """`## 최근 궤적`에 세션 한 줄을 누적한다 — 교체가 아니라 append."""
    if not os.path.exists(STATUS_PATH):
        return False
    with open(STATUS_PATH, encoding="utf-8") as f:
        lines = f.read().splitlines()

    idx = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and normalize_heading(TRAJECTORY_SECTION) in normalize_heading(line[3:]):
            idx = i
            break
    if idx is None:
        return False

    end = len(lines)
    for i in range(idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    keep, entries = [], []
    for line in lines[idx + 1:end]:
        if line.lstrip().startswith(">"):
            keep.append(line)
        elif line.strip().startswith("-"):
            entries.append(line.strip())

    # 첫 세션 전의 자리표시자는 실제 기록이 들어오면 사라져야 한다.
    entries = [e for e in entries if "아직 없음" not in e]
    entry = f"- {date} · {display} → [{path}]({path})"
    entries = [e for e in entries if not e.startswith(f"- {date} · {display} ")]
    entries.append(entry)
    entries = entries[-TRAJECTORY_KEEP:]

    lines[idx + 1:end] = keep + [""] + entries + [""]
    for i, line in enumerate(lines[:20]):
        if line.startswith("updated:"):
            lines[i] = f"updated: {today}"
            break
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return True


def ensure_headings(body):
    """정규 헤딩이 없으면 자리만 만들어 둔다 — 기록을 막는 대신 경고한다."""
    present = {normalize_heading(m) for m in re.findall(r"^#{1,6}\s*(.+)$", body, re.M)}
    missing = []
    for heading in REQUIRED_HEADINGS:
        key = normalize_heading(heading)
        if not any(key in p for p in present):
            missing.append(heading)
    if missing:
        extra = ["", "> ⚠️ 아래 헤딩은 수집기가 자동 보정했다 — 세션에 실제 기록이 없었다는 뜻이다."]
        for heading in missing:
            extra += ["", f"## {heading}", "- (이번 세션 기록 없음)"]
        body = body.rstrip() + "\n" + "\n".join(extra) + "\n"
    return body, missing


def pop_directives(body, allowed):
    """본문 맨 앞의 `key: value` 지시행을 떼어낸다 → (지시 dict, 남은 본문).

    앱이 만든 초안은 frontmatter 울타리(`---`) 없이 `slug: …`처럼 맨 윗줄에 적는다.
    세션 노트(`build_note`)가 쓰던 관례와 같은 것이라 여기 모아 둘이 함께 쓴다.
    """
    out, lines = {}, (body or "").splitlines()
    pattern = r"^(%s)\s*:\s*\S" % "|".join(allowed)
    while lines and re.match(pattern, lines[0].strip()):
        key, value = lines[0].split(":", 1)
        out[key.strip()] = value.strip()
        lines.pop(0)
    return out, "\n".join(lines).strip()


def source_toc(source_body):
    """원문의 `### ` 제목 목록. 증류본에 실어 **어느 절을 열지 고르는 지도**로 쓴다.

    `get_state`에 담지 않는 이유: 그러면 자료 수만큼 원문을 통째로 받아야 해서 세션
    시작이 느려진다. CI는 자료를 가를 때 이미 원문을 손에 들고 있으므로 여기서는 공짜다.
    """
    return [m.group(1).strip() for m in re.finditer(r"^###\s+(\S.*)$", source_body or "", re.M)]


def existing_material_slug(number):
    """이 Issue로 이미 만든 자료의 slug. 없으면 None.

    같은 Issue를 고쳐 다시 보내도 새 파일이 생기지 않게 한다(제목을 고치면 slug가 바뀐다).
    단일 파일형(`materials/<slug>.md`)과 폴더형(`materials/<slug>/distilled.md`)을 함께 본다.
    """
    marker = f"source_issue: {number}"
    if not os.path.isdir(MATERIALS_DIR):
        return None
    for entry in sorted(os.listdir(MATERIALS_DIR)):
        full = os.path.join(MATERIALS_DIR, entry)
        if os.path.isfile(full) and entry.endswith(".md"):
            with open(full, encoding="utf-8") as f:
                if marker in f.read(2000):
                    return entry[: -len(".md")]
        elif os.path.isdir(full):
            for name in ("distilled.md", "source.md"):
                cand = os.path.join(full, name)
                if os.path.isfile(cand):
                    with open(cand, encoding="utf-8") as f:
                        if marker in f.read(2000):
                            return entry
    return None


def split_source(body):
    """`## 원문` 경계로 (증류 부분, 원문 부분). 경계가 없으면 (body, None).

    앱이 자료를 올릴 때 증류를 원문 **앞에** 놓고 이 제목을 경계로 둔다
    (Topdown `lib/sources/issueDraft.ts`). 두 조각은 성격이 다르다 —
    증류는 파생 학습자료이고 원문은 인용 근거다. 그래서 파일을 나눈다.
    """
    m = re.search(r"^##\s*%s\s*$" % re.escape(SOURCE_SECTION), body or "", re.M)
    if not m:
        return body, None
    return body[:m.start()].rstrip(), body[m.end():].lstrip("\n")


def is_distilled(body):
    """이 본문이 **실제로 증류된 것인가** — `## 개념 지도`가 있는가.

    셋 중 이것을 기준으로 삼는 이유: 요약·빈칸 문제는 사람이 읽는 것이지만 `## 개념 지도`는
    **파이프라인이 실제로 먹는 것**이다(`build_concepts.py`가 materials/에서 선수관계를
    읽어 간다). 이게 없으면 그래프에 아무것도 안 들어가므로, 증류의 값이 없는 것과 같다.
    """
    return bool(re.search(r"^##\s*.*%s" % re.escape(CONCEPT_MAP_SECTION), body or "", re.M))


def build_material(payload, today):
    """`[자료]` Issue → materials/<slug>.md — 강의자료를 증류한(또는 못 한) 파생 학습자료.

    왜 이 경로인가: Custom GPT Action 응답은 텍스트라 repo의 PDF를 세션에서 읽을 수
    없다. 그래서 PDF는 대화에 한 번 올리고, 요약(지도)·개념 지도·빈칸 문제 은행을
    텍스트로 남긴다 — 이후 세션은 readFile로 끌어온다.
    정규 헤딩 강제·STATUS/mastery 처리는 하지 않는다(세션 로그가 아니다).

    **라벨은 사실을 말한다.** 2026-08-09: 앱에서 PDF를 파싱해 초안만 만들고 세션 없이
    닫으면 본문 전체가 원문인데도 frontmatter가 조건 없이 `distilled`를 적고 있었다
    (실측: 102KB 전부 원문, `## ` 헤딩은 `러너에게`·`원문` 둘뿐). 조용한 거짓말이라
    "이 파일은 증류본이니 원문이 아니다"라는 저작권 판단까지 오도한다. 그래서 본문을
    보고 정한다 — 증류가 있으면 `distilled`, 없으면 `raw`.
    """
    raw = assemble(payload)
    user_fm, body = split_frontmatter(raw)
    directives, body = pop_directives(body, ("slug", "paper"))
    user_fm = {**directives, **user_fm}
    title = payload.get("title") or ""
    head, _, tail = title.partition("—")
    if not tail:
        head, _, tail = title.partition(" - ")
    # `paper:`가 있으면 논문 한 편의 저장소로 간다 — 그 논문의 것은 그 논문 폴더에.
    paper_slug = (user_fm.get("paper") or "").strip()
    root = PAPERS_DIR if paper_slug else MATERIALS_DIR
    slug = paper_slug or user_fm.get("slug") or slugify(head) or f"material-{payload.get('number', '0')}"
    display = (tail or head).strip()
    display = re.sub(r"^\s*\[[^\]]*\]\s*", "", display).strip()
    display = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", display).strip() or slug
    head, source_body = split_source(body)
    distilled = is_distilled(head if source_body is not None else body)

    def frontmatter(tag, source_line):
        return "\n".join([
            "---",
            f'title: "{display}"',
            f"created: {today}",
            f"updated: {today}",
            f"tags: [material, {tag}]",
            f'source: "{source_line} → Issue #{payload.get("number")}"',
            "kind: material",
            f"source_issue: {payload.get('number')}",
            "---",
        ])

    def page(text, tag, source_line):
        if not re.match(r"^#\s", text):
            text = f"# {display}\n\n" + text
        return frontmatter(tag, source_line) + "\n\n" + text.rstrip() + "\n"

    # 폴더형으로 가르는 때: **원문 경계가 있으면 언제나.** 논문은 `papers/<slug>/`가 이미
    # 폴더 규약이라 경계가 없어도 폴더다.
    #
    # 증류 성공 여부로 가르지 않는다(유지훈 2026-08-10: *"원본도 내가 분명히 그냥 저장하자고
    # 했었는데 — GPT가 효율적으로 읽고 토큰 절감시킨다고 증류가 목적이지"*). 증류는 러너의
    # 토큰을 아끼는 **길잡이**이고 원문은 인용 근거다. 길잡이를 못 만들었다고 원문이 있을
    # 자리가 바뀌면, 앱이 약속한 `<root>/<slug>/source.md`가 거짓이 되고
    # `read_doc`이 404를 돌려준다 — 러너가 도구를 버리게 만드는 바로 그 실패다.
    #
    # 그래도 빈 `distilled.md`는 만들지 않는다(아래) — 그 빈 껍데기에 `distilled` 딱지가
    # 붙는 것이 이 경로가 고쳐 온 거짓말이다. 없는 파일은 `listMaterials`가 이미 견딘다.
    folder = bool(paper_slug) or source_body is not None
    if not folder:
        return {
            "slug": slug, "root": root, "distilled": distilled, "files": None,
            "flat": page(
                body,
                "distilled" if distilled else "raw",
                "자료 증류" if distilled else "원문 텍스트 (증류 없음)",
            ),
        }

    files = {}
    if source_body is not None:
        if distilled:
            files["source.md"] = page(source_body, "source", "원문 텍스트 (그대로 보존)")
            # 목차를 증류본에 실어 준다 — 러너는 어차피 증류본을 길잡이로 읽는다.
            toc = source_toc(source_body)
            body_with_toc = head if not toc else head.rstrip() + "\n\n" + "\n".join(
                ["## 원문 목차", "",
                 "> `read_doc`에 `section`으로 이 이름을 그대로 넘기면 그 절의 원문만 받는다.",
                 ""] + [f"- {t}" for t in toc]
            )
            files["distilled.md"] = page(body_with_toc, "distilled", "자료 증류")
        else:
            # 증류가 없으면 `distilled.md`를 만들지 않는다. 그러면 머리말(메타 + 러너에게
            # 남길 일)이 갈 곳이 없으므로 원문 앞에 둔다 — 버리면 "무엇을 왜 올렸나"가
            # 사라지고, 경계가 아예 없는 경우(아래 else)와도 모양이 어긋난다.
            files["source.md"] = page(
                f"{head.rstrip()}\n\n{source_body}" if head.strip() else source_body,
                "source",
                "원문 텍스트 (증류 없음)",
            )
    else:
        # 경계가 없다 = 통째로 증류본이거나 통째로 원문이다.
        files["distilled.md" if distilled else "source.md"] = page(
            body,
            "distilled" if distilled else "source",
            "자료 증류" if distilled else "원문 텍스트 (증류 없음)",
        )
    return {"slug": slug, "root": root, "distilled": distilled, "files": files, "flat": None}


def build_note(payload, today):
    raw = assemble(payload)
    user_fm, body = split_frontmatter(raw)

    # 본문 맨 앞의 지시행(slug:, runner:)도 frontmatter처럼 취급하고 제거한다.
    directives = {}
    lines = body.splitlines()
    while lines and re.match(r"^(slug|runner|course|week|exam_target|tags|track|artifact|turns)\s*:\s*\S", lines[0].strip()):
        key, value = lines[0].split(":", 1)
        directives[key.strip()] = value.strip()
        lines.pop(0)
    body = "\n".join(lines).strip()
    user_fm = {**directives, **user_fm}

    body, status_patch = extract_status_patch(body)
    body, material_patch = extract_status_patch(body, MATERIAL_STATUS_SECTION)
    # 세션이 한 단계를 통과했으면 `[다음]` → `[완료]`가 여기로 온다.
    body, spec_patch = extract_status_patch(body, LEARNING_SPEC_SECTION)
    body, mastery = pop_section(body, MASTERY_SECTION)
    body, drills = pop_section(body, DRILLS_SECTION)
    body, missing = ensure_headings(body)
    # 러너가 안 쓴 STATUS 절은 노트 본문에서 유도한다(모델에게 같은 말을 두 번 시키지 않는다).
    status_patch = derive_status_patch(body, status_patch)

    # 제목 규약: `[학습] YYYY-MM-DD <slug> — <한 줄 제목>` (뒷부분은 선택)
    title = payload.get("title") or ""
    date = (re.search(r"\d{4}-\d{2}-\d{2}", title) or re.search(r"\d{4}-\d{2}-\d{2}", user_fm.get("created", "")))
    date = date.group(0) if date else today

    head, _, tail = title.partition("—")
    if not tail:
        head, _, tail = title.partition(" - ")
    slug = user_fm.get("slug") or slugify(head) or slugify(title) or f"session-{payload.get('number', '0')}"

    display = (tail or head).strip()
    display = re.sub(r"^\s*\[[^\]]*\]\s*", "", display).strip()
    display = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", display).strip() or slug

    tags = user_fm.get("tags") or "[learning]"
    if not tags.startswith("["):
        tags = "[" + tags + "]"

    fm = [
        "---",
        f'title: "{user_fm.get("title", display)}"',
        f"created: {date}",
        f"updated: {today}",
        f"tags: {tags}",
        f'source: "학습 세션 → Issue #{payload.get("number")} (수집기: ingest_learning_note.py)"',
        "status: active",
        "kind: mixed",
        f'runner: {user_fm.get("runner", "gpt")}',
        f"source_issue: {payload.get('number')}",
    ]
    # `artifact` — 세션 밖에 남은 산출물(코드·발표자료·재현 노트북)의 링크.
    # 파일럿 지표 `time_to_first_artifact`의 유일한 원자료라, 본문에 묻히지 않게
    # frontmatter로 올린다(`pilot_rollup.py`가 여기서 센다).
    # `turns` — 이번 세션의 대화 왕복 수(2026-08-15). 학습자 1명 월 LLM 원가 추정의
    # **최대 불확실성**이고(입력 토큰이 턴 수의 제곱으로 자란다), 여기 없으면 영원히
    # 가정으로 남는다. 안 적혔으면 줄을 만들지 않는다 — 0과 미기록은 다르다.
    for key in ("course", "week", "exam_target", "artifact", "turns"):
        if user_fm.get(key):
            fm.append(f"{key}: {user_fm[key]}")
    fm.append("---")

    heading = f"# {user_fm.get('title', display)}"
    if not re.match(r"^#\s", body):
        body = heading + "\n\n" + body

    return {
        "date": date,
        "slug": slug,
        "content": "\n".join(fm) + "\n\n" + body.rstrip() + "\n",
        "status_patch": status_patch,
        "material_patch": material_patch,
        "spec_patch": spec_patch,
        "mastery": mastery,
        "drills": drills,
        "track": user_fm.get("track", ""),
        "display": display,
        "missing": missing,
    }


# --------------------------------------------------------------------------- 쓰기


def load_tracks(path=TRACKS_PATH):
    """`tracks.yaml` → [{id, label, mode, goal}]. 없으면 빈 목록(= 트랙 없이 쓰던 대로)."""
    if not os.path.exists(path):
        return []
    tracks, cur = [], None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = re.match(r"^\s*-\s*(\w+):\s*(.*)$", line)
            if m:
                cur = {m.group(1): m.group(2).strip().strip("\"'")}
                tracks.append(cur)
                continue
            m = re.match(r"^\s+(\w+):\s*(.*)$", line)
            if m and cur is not None:
                cur[m.group(1)] = m.group(2).strip().strip("\"'")
    return [t for t in tracks if t.get("id")]


def resolve_track(name, tracks):
    """러너가 쓴 `track:` 값을 실제 트랙 id로 맞춘다 (id·라벨·대소문자 흔들림 흡수).

    **없는 트랙은 만들지 않는다.** 트랙은 학습자가 정하는 서랍이고, 러너가 오타를 내면
    `daily/electornics/`처럼 유령 폴더가 생겨 다음 세션부터 기록이 갈라진다.
    못 찾으면 None을 돌려주고, 호출부는 루트에 쓰면서 그 사실을 회신에 적는다.
    """
    if not name:
        return None
    want = name.strip().strip("`").lower()
    for t in tracks:
        if want in (t["id"].lower(), (t.get("label") or "").lower()):
            return t["id"]
    return None


def target_path(date, slug, issue_number, track=None):
    """같은 Issue를 다시 수집하면 같은 파일을 덮어쓴다(재실행 안전).

    트랙이 있으면 `daily/<track>/`에 쓴다. 없던 시절의 노트는 `daily/` 바로 아래에
    있으므로, 재수집 탐색은 **하위 폴더까지** 훑는다 — 그래야 트랙을 도입한 뒤에도
    옛 Issue를 다시 수집했을 때 파일이 둘로 갈라지지 않는다.
    """
    marker = f"source_issue: {issue_number}"
    if os.path.isdir(DAILY_DIR):
        for root, dirs, files in os.walk(DAILY_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    if marker in f.read(2000):
                        return path

    folder = os.path.join(DAILY_DIR, track) if track else DAILY_DIR
    base = os.path.join(folder, f"{date}-{slug}.md")
    if not os.path.exists(base):
        return base
    for n in range(2, 20):
        candidate = os.path.join(folder, f"{date}-{slug}-{n}.md")
        if not os.path.exists(candidate):
            return candidate
    raise SystemExit(f"경로 충돌: {base}")


def append_drills(section, date, path=DRILLS_PATH):
    """`## 드릴 항목` → `drills.md`에 누적. 이미 있는 항목은 다시 적지 않는다.

    mastery.md와 달리 조각+CI 통합을 쓰지 않는다 — 항목은 상태가 바뀌지 않는 목록이라
    덧붙이기만 하면 되고, 러너가 아니라 이 스크립트만 이 파일을 만진다(충돌 없음).
    """
    items = []
    for line in section.splitlines():
        m = re.match(r"^\s*(?:[-*+]|\d+[.)])\s*(.+?)\s*$", line)
        if not m:
            continue
        name = m.group(1).strip().strip("`")
        if name and "<" not in name and name not in items:
            items.append(name)
    if not items:
        return None

    existing, lines = set(), []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().rstrip().splitlines()
        for line in lines:
            m = re.match(r"^\s*[-*+]\s*(.+?)\s*$", line)
            if m:
                existing.add(m.group(1).split("  <!--")[0].strip())
    else:
        lines = list(DRILLS_HEADER)

    fresh = [i for i in items if i not in existing]
    if not fresh:
        return None

    lines += ["", f"## {date}"] + [f"- {i}" for i in fresh]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return len(fresh)


def write_mastery_fragment(section, track, date, slug, note_path):
    """`## 이해도 승급` 표를 create-only 조각으로 떨군다 → consolidate_mastery.py가 접는다.

    러너는 여기서도 큰 mastery.md를 건드리지 않는다. 판단(승급 여부)은 세션의 몫이고
    이 함수는 옮겨 적기만 한다.
    """
    if not section.strip():
        return None

    lines = section.splitlines()
    if lines and lines[0].strip().startswith("track:"):
        track = track or lines[0].split(":", 1)[1].strip()
        lines = lines[1:]
    section = "\n".join(lines).strip()
    if not section:
        return None

    if not track:
        ledgers = []
        for root, dirs, files in os.walk(LEARNING_ROOT):
            # `presets/`는 복사해 쓰라고 둔 견본이지 활성 트랙이 아니다. 숨김 디렉터리도 후보가 아니다.
            dirs[:] = [d for d in dirs if d != "presets" and not d.startswith(".")]
            if "mastery.md" in files:
                ledgers.append(os.path.relpath(root, LEARNING_ROOT))
        # 루트 원장이 있으면 그것이 기본 트랙이다 — 모호할 때 루트가 이긴다.
        if "." in ledgers:
            ledgers = ["."]
        if len(ledgers) != 1:
            return f"⚠️ 이해도 승급을 건너뛰었다 — `track:`이 없고 원장 후보가 {len(ledgers)}개다."
        track = ledgers[0]

    mdir = os.path.normpath(os.path.join(LEARNING_ROOT, track, "mastery"))
    if not os.path.isdir(os.path.join(LEARNING_ROOT, track)):
        return f"⚠️ 이해도 승급을 건너뛰었다 — 트랙 경로 없음: `{track}`"
    os.makedirs(mdir, exist_ok=True)

    path = os.path.join(mdir, f"{date}-{slug}.md")
    header = [
        "---",
        f'title: "{date} 이해도 승급 — {slug}"',
        f"created: {date}",
        "tags: [learning, mastery, promotion]",
        f'source: "{note_path}"',
        "kind: fact",
        "---",
        "",
        f"> 세션 근거: [[{note_path[:-3]}]]",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header) + "\n" + section.strip() + "\n")
    return path


def _entry_text(line):
    """`1. 항목` · `- 항목` → `항목`. 번호는 자리일 뿐이라 같은 항목의 판단에서 뺀다."""
    return re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", line).strip()


def merge_entries(old_lines, content, cap):
    """새 항목을 앞에, 아직 남은 옛 항목을 뒤에 — 중복 없이 `cap`개까지.

    자리표시자(`(첫 세션의 스캔에서 채워진다)` 같은 괄호 한 줄)는 실제 항목이 들어오면
    사라져야 한다. 안내용 인용(`>`)은 호출부가 이미 따로 보존한다.
    """
    fresh, seen = [], set()
    for line in content.splitlines():
        text = _entry_text(line)
        if text and text not in seen:
            seen.add(text)
            fresh.append(text)

    for line in old_lines:
        if line.lstrip().startswith(">") or not line.strip():
            continue
        text = _entry_text(line)
        if not text or text in seen:
            continue
        if text.startswith("(") and text.endswith(")"):
            continue
        seen.add(text)
        fresh.append(text)

    return "\n".join(f"{i}. {t}" for i, t in enumerate(fresh[:cap], 1))


def apply_section_patch(patch, today, path=STATUS_PATH):
    """`## ` 절 본문을 통째로 교체한다 — 안내용 인용(>)줄은 보존.

    STATUS.md 전용이었으나 논문 정제본·READING_STATUS도 동작이 같아 경로를 받는다.
    """
    if not patch or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    applied = []
    for section, content in patch.items():
        key = normalize_heading(section)
        idx = None
        for i, line in enumerate(lines):
            if line.startswith("## ") and key and key in normalize_heading(line[3:]):
                idx = i
                break
        if idx is None:
            continue

        end = len(lines)
        for i in range(idx + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break

        keep = []
        for line in lines[idx + 1:end]:
            if line.strip() == "" or line.lstrip().startswith(">"):
                keep.append(line)
            else:
                break
        while keep and keep[-1].strip() == "":
            keep.pop()

        cap = STATUS_ACCUMULATED.get(section)
        body = merge_entries(lines[idx + 1:end], content, cap) if cap else content

        lines[idx + 1:end] = (keep or [""]) + [body, ""]
        applied.append(section)

    if applied:
        for i, line in enumerate(lines[:20]):
            if line.startswith("updated:"):
                lines[i] = f"updated: {today}"
                break
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n")
    return applied


# 이름을 바꾸기 전 호출부와의 호환 — STATUS 경로 기본값 그대로.
apply_status_patch = apply_section_patch


def build_paper_session(payload, today):
    """`[논문]` Issue → 논문 폴더에 쌓이는 세션 + 정제본/주석/READING_STATUS 패치.

    제목 규약: `[논문] <paper-slug> — <섹션>`
    slug는 `papers/` 아래 폴더 이름이 된다. 학습 노트와 달리 **날짜가 아니라 논문**이
    묶는 단위다 — 한 편을 여러 세션에 걸쳐 관통하기 때문이다.
    """
    raw = assemble(payload)
    user_fm, body = split_frontmatter(raw)

    directives = {}
    lines = body.splitlines()
    while lines and re.match(r"^(slug|root|runner|tags)\s*:\s*\S", lines[0].strip()):
        key, value = lines[0].split(":", 1)
        directives[key.strip()] = value.strip()
        lines.pop(0)
    body = "\n".join(lines).strip()
    user_fm = {**directives, **user_fm}

    body, reading_patch = extract_status_patch(body, READING_STATUS_SECTION)
    section_patches = {}
    for name, filename in PAPER_SECTIONS.items():
        body, section = pop_section(body, name)
        if section:
            section_patches[filename] = section

    # Parking Lot·아티팩트·메타는 정제본과 저장 규칙이 달라 따로 뗀다.
    # (정제본은 절 단위 교체, 이쪽은 각각 병합·파일 분리·키 병합)
    body, parking = pop_section(body, PARKING_SECTION)
    body, artifacts = pop_section(body, ARTIFACT_SECTION)
    body, meta = pop_section(body, META_SECTION)

    title = re.sub(r"^\s*\[논문\]\s*", "", payload.get("title") or "").strip()
    head, _, tail = title.partition("—")
    if not tail:
        head, _, tail = title.partition(" - ")
    slug = user_fm.get("slug") or slugify(head) or slugify(title)
    if not slug:
        raise SystemExit(
            "제목에서 논문 slug를 못 찾았다 — `[논문] <paper-slug> — <섹션>` 형식이어야 한다."
        )
    section_name = (tail or "session").strip() or "session"

    return {
        "slug": slug,
        "root": parse_root(user_fm.get("root")),
        "section": section_name,
        "body": body,
        "reading_patch": reading_patch,
        "section_patches": section_patches,
        "parking": parking,
        "artifacts": artifacts,
        "meta": parse_meta(meta),
        "runner": user_fm.get("runner", "paper-gpt"),
    }


# `[논문]` 세션이 앉을 수 있는 뿌리. **이 둘뿐이다.**
#
# 2026-08-14: 앱의 읽기 화면이 파킹랏·주석을 저장소로 올리게 되면서 열었다(유지훈:
# *"파킹랏이나 주석이 … 항상 gpt가 읽을 수 있는 온라인으로 올려야한다"*). 렉처노트·교재는
# `materials/`에 사는데 파킹랏을 받는 곳이 `papers/`밖에 없어서, 자료에 남긴 표시는
# 러너가 볼 수 없었다.
#
# 화이트리스트로 잠근 이유: 이 값이 `os.path.join`의 첫 칸이 되고 이 스크립트는 repo
# 루트에서 돈다. 자유 문자열이면 `..`이나 `.github`가 들어올 수 있다 — `## 삭제`의
# `DELETABLE_ROOTS`와 같은 판단이다.
PAPER_ROOTS = (PAPERS_DIR, MATERIALS_DIR)


def parse_root(value):
    """`root:` 지시행 → 뿌리 이름. 모르는 값은 **기본값으로 떨어뜨린다.**

    거부하지 않고 떨어뜨리는 이유: 이 절이 없던 시절의 러너 Issue가 계속 들어오고, 그것들은
    전부 논문이다. 모르는 값에 실패로 답하면 러너가 오타 하나로 세션 기록을 잃는다 —
    잘못된 뿌리에 쓰는 것보다 낫고, 안 쓰는 것보다도 낫다.
    """
    root = (value or "").strip().strip("/")
    return root if root in PAPER_ROOTS else PAPERS_DIR


def parse_meta(section):
    """`## 메타`의 `key: value` 줄을 딕셔너리로. 모르는 키는 버린다."""
    meta = {}
    for line in section.splitlines():
        line = line.strip().lstrip("-").strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().strip("`"), value.strip()
        if key in META_KEYS and value and not value.startswith("<"):
            meta[key] = value
    return meta


def merge_flow(old, new):
    """`flow:`만 **합집합**으로 병합한다 — 다른 키와 달리 덮어쓰지 않는다.

    한 논문의 다섯 단계는 여러 세션에 걸쳐 통과한다. 1주차에 문제·한계를 설명했고
    2주차에 방법을 설명했다면, 2주차 노트에는 `flow: 방법`만 적히는 것이 정상이다
    (러너는 **이번 세션에 통과한 것**을 적는다). 다른 키처럼 덮어쓰면 앞선 두 단계가
    조용히 사라지고, 완료 판정은 영원히 안 난다.

    누적을 러너에게 맡기지 않는 이유: 이 파일의 다른 키와 같은 이유다 — 매 세션 전부
    다시 적으라고 하면 지어낸다. 기억은 기계가 한다.

    합집합이라 **빼는 방향은 없다.** 잘못 올라간 단계는 `meta.yaml`을 직접 고친다
    (판정이 올라가기만 하는 성질은 `understanding`도 같고, 되돌리는 일은 드물다).
    """
    seen = set()
    for text in (old or "", new or ""):
        for word in re.split(r"[,·/]|\s+", text):
            word = word.strip()
            if word in FLOW_STEPS:
                seen.add(word)
    # 원문 순서(문제→한계→방법→실험→결과)로 되돌려 적는다 — 러너가 적은 순서가 아니라
    # 논문이 흐르는 순서여야 사람이 읽고 "어디서 끊겼나"를 본다.
    return ", ".join(step for step in FLOW_STEPS if step in seen)


def merge_meta(path, meta, slug, today):
    """meta.yaml을 **키 단위로** 병합한다 — 안 온 키는 지우지 않는다.

    러너가 매 세션 서지 정보를 다시 적을 필요가 없어야 한다(적으라고 하면 지어낸다).
    YAML 라이브러리는 쓰지 않는다 — 이 파일은 평평한 `key: value`뿐이고, CI에
    의존성을 늘리지 않는 것이 이 저장소의 규칙이다.
    """
    existing = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if ":" in line and not line.lstrip().startswith("#"):
                    key, _, value = line.partition(":")
                    existing[key.strip()] = value.strip()
    # `flow`만 합집합(위 merge_flow) — 나머지는 이번 세션 값으로 덮어쓴다.
    flow = merge_flow(existing.get("flow"), meta.get("flow"))
    existing.update(meta)
    if flow:
        existing["flow"] = flow
    else:
        existing.pop("flow", None)
    existing["slug"] = slug
    existing["updated"] = today

    order = ["slug", *META_KEYS, "updated"]
    lines = [
        "# 논문 서지 + 현재 이해 단계 — 러너가 세션 시작에 읽는다.",
        f"# understanding: {' / '.join(UNDERSTANDING)}",
        f"# flow: 사용자가 자기 말로 설명해 통과한 단계만 — {' / '.join(FLOW_STEPS)}",
    ]
    for key in order:
        if key in existing:
            lines.append(f"{key}: {existing[key]}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def merge_parking_lot(path, section, slug, today):
    """Parking Lot을 **항목 단위로** 병합한다(중복 제거 · `- [x]`는 해소 표시).

    같은 선수지식이 여러 세션에 걸쳐 다시 걸린다. 그냥 append하면 목록이 같은 항목으로
    부풀어 "무엇이 남았나"를 못 읽는다. 그래서 항목 이름을 키로 병합하고, 한 번 해소된
    것은 다시 미해결로 내려가지 않는다.
    """
    def key_of(text):
        text = text.split("—")[0].split(" - ")[0]
        return re.sub(r"\s+", " ", text).strip().lower()

    items, order = {}, []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^- \[([ x])\]\s*(.+)$", line.strip())
                if m:
                    key = key_of(m.group(2))
                    if key not in items:
                        order.append(key)
                    items[key] = (m.group(1) == "x", m.group(2).rstrip())

    added, resolved = 0, 0
    for line in section.splitlines():
        line = line.strip()
        m = re.match(r"^- (?:\[([ x])\]\s*)?(.+)$", line)
        if not m:
            continue
        done, text = m.group(1) == "x", m.group(2).rstrip()
        key = key_of(text)
        if not key:
            continue
        was = items.get(key)
        if was is None:
            order.append(key)
            added += 1
        elif done and not was[0]:
            resolved += 1
        # 해소는 되돌리지 않는다 — 한 번 배운 것을 다시 미해결로 적지 않는다.
        items[key] = (done or (was[0] if was else False), text if not was or not was[0] else was[1])

    header = [
        "---", f'title: "{slug} — Parking Lot"', f"updated: {today}", "kind: parking-lot", "---",
        "",
        "# Parking Lot — 지금은 미룬 선수지식",
        "",
        "> 논문 읽기가 수학 공부로 탈선하지 않게, 지금 필요한 최소 의미만 듣고 여기로 보낸 것들.",
        "> 별도 `[학습]` 세션의 재료가 된다. 해소되면 `- [x]`로 바뀐다.",
        "",
    ]
    body = [f"- [{'x' if items[k][0] else ' '}] {items[k][1]}" for k in order]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + body) + "\n")
    return added, resolved


def write_artifacts(folder, section, slug, today, issue_number):
    """`### <제목>` 마다 파일 하나 — `papers/<slug>/artifacts/`.

    아티팩트는 다음 세션의 복습 장치다. 세션 원문 안에 묻히면 다시 못 찾으므로
    제목을 파일 이름으로 꺼내 둔다. 같은 Issue가 다시 돌면 같은 파일을 덮어쓴다.
    """
    written = []
    current, buf = None, []

    def flush():
        if current is None:
            return
        content = "\n".join(buf).strip()
        if not content:
            return
        name = f"{today}-{slugify(current) or 'artifact'}.md"
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join([
                "---", f'title: "{current}"', f"paper: {slug}", f"created: {today}",
                "kind: artifact", f"source_issue: {issue_number}", "---", "",
                f"# {current}", "",
            ]) + content + "\n")
        written.append(path)

    for line in section.splitlines():
        if line.startswith("### "):
            flush()
            current, buf = line[4:].strip(), []
        elif current is not None:
            buf.append(line)
    flush()
    return written


def write_paper_session(note, payload, today):
    """세션 원문을 자료 폴더에 쓰고, 정제본·주석·READING_STATUS를 갱신한다.

    뿌리는 `note["root"]`가 정한다(`papers/` 기본, `materials/`도 가능 — `parse_root`).
    `READING_STATUS` 패치만은 여전히 `papers/READING_STATUS.md`로 간다: 자료의 진도는
    `## 자료 진도 갱신`이라는 **다른 기계**가 담당하고(`MATERIAL_STATUS_PATH`), 그 둘을
    섞으면 같은 파일을 두 경로가 쓰게 된다.
    """
    folder = os.path.join(note.get("root") or PAPERS_DIR, note["slug"])
    sessions = os.path.join(folder, "sessions")
    os.makedirs(sessions, exist_ok=True)

    marker = f"source_issue: {payload.get('number')}"
    path = None
    for name in sorted(os.listdir(sessions)):
        if not name.endswith(".md"):
            continue
        cand = os.path.join(sessions, name)
        with open(cand, encoding="utf-8") as f:
            if marker in f.read(2000):
                path = cand
                break
    if path is None:
        path = os.path.join(sessions, f"{today}-{slugify(note['section']) or 'session'}.md")

    fm = [
        "---",
        f'title: "{note["slug"]} — {note["section"]}"',
        f"created: {today}",
        f"updated: {today}",
        "kind: paper-session",
        f'runner: {note["runner"]}',
        f"source_issue: {payload.get('number')}",
        "---",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(fm) + "\n\n" + note["body"].rstrip() + "\n")

    touched = [path]
    # 정제본·주석 — 파일이 없으면 만들어 준다(첫 세션에 폴더가 비어 있다).
    for filename, content in note["section_patches"].items():
        target = os.path.join(folder, filename)
        if filename == "annotations.md":
            # 주석은 세션마다 **쌓이는** 파일이지만, CI는 코멘트가 붙을 때마다 다시 돈다.
            # 그냥 append하면 한 세션이 열 번 이어 써질 때 같은 인용이 열 번 쌓인다.
            # 그래서 Issue 번호로 블록을 표시하고, 같은 블록은 덮어쓴다(재실행 안전).
            marker = f"<!-- issue:{payload.get('number')} -->"
            block = (
                f"{marker}\n### {today} · {note['section']}\n{content.rstrip()}\n"
                f"<!-- /issue:{payload.get('number')} -->\n"
            )
            if os.path.exists(target):
                with open(target, encoding="utf-8") as f:
                    existing = f.read()
            else:
                existing = "\n".join([
                    "---", f'title: "{note["slug"]} — 주석"', "kind: annotations", "---",
                    "", "# 하이라이트", "",
                    "> 인용문과 내 코멘트가 세션마다 쌓인다(덮어쓰지 않는다).", "",
                ]) + "\n"
            start = existing.find(marker)
            if start != -1:
                end = existing.find(f"<!-- /issue:{payload.get('number')} -->", start)
                end = len(existing) if end == -1 else end + len(f"<!-- /issue:{payload.get('number')} -->") + 1
                existing = existing[:start] + block + existing[end:]
            else:
                existing = existing.rstrip() + "\n\n" + block
            with open(target, "w", encoding="utf-8") as f:
                f.write(existing)
            touched.append(target)
            continue

        if not os.path.exists(target):
            with open(target, "w", encoding="utf-8") as f:
                f.write(
                    "\n".join([
                        "---", f'title: "{note["slug"]} — 정제본"',
                        f"updated: {today}", "kind: paper", "---", "",
                        f"# {note['slug']}", "",
                        "> 검증된 이해만 담는다 — 설명하지 못한 것은 여기 오지 않는다(❓로 남긴다).",
                        "",
                    ]) + "\n"
                )
        # 정제본은 `### <절 이름>` 단위로 온다 — 없는 절은 뒤에 새로 붙인다.
        with open(target, encoding="utf-8") as f:
            existing = f.read()
        patch = {}
        current = None
        for line in content.splitlines():
            if line.startswith("### "):
                current = line[4:].strip()
                patch[current] = []
            elif current is not None:
                patch[current].append(line)
        patch = {k: "\n".join(v).strip() for k, v in patch.items() if "\n".join(v).strip()}
        missing = [k for k in patch if f"## {k}" not in existing]
        if missing:
            with open(target, "a", encoding="utf-8") as f:
                for k in missing:
                    f.write(f"\n## {k}\n\n")
        apply_section_patch(patch, today, path=target)
        touched.append(target)

    if note["meta"]:
        merge_meta(os.path.join(folder, "meta.yaml"), note["meta"], note["slug"], today)
        touched.append(os.path.join(folder, "meta.yaml"))

    parked = (0, 0)
    if note["parking"]:
        parked = merge_parking_lot(
            os.path.join(folder, "parking-lot.md"), note["parking"], note["slug"], today
        )
        touched.append(os.path.join(folder, "parking-lot.md"))

    artifacts = []
    if note["artifacts"]:
        artifacts_dir = os.path.join(folder, "artifacts")
        os.makedirs(artifacts_dir, exist_ok=True)
        artifacts = write_artifacts(
            artifacts_dir, note["artifacts"], note["slug"], today, payload.get("number")
        )
        touched += artifacts

    # `papers/`는 sync_from_template의 NEVER 경로다 — 템플릿을 갱신해도 기존 학습자의
    # repo에는 이 파일이 오지 않는다. 그래서 첫 논문 세션에서 여기서 만든다.
    ensure_reading_status(today)
    ensure_position_section()
    applied = apply_section_patch(note["reading_patch"], today, path=READING_STATUS_PATH)
    return touched, applied, {"parked": parked, "artifacts": artifacts}


READING_STATUS_TEMPLATE = """---
title: "논문 읽기 상태 — 논문 러너 진입점"
updated: {today}
kind: reading-status
---

# 논문 읽기 상태

> 논문 세션을 시작하면 러너가 가장 먼저 읽는 한 파일.
> 세션이 끝나면 Issue의 `## READING_STATUS 갱신` 절로 갱신된다.

## Progress

- (아직 없음)

## Current Understanding

- (아직 없음)

## Next Session

- (다음 세션의 시작점 한 줄)

## Position

- (아직 없음)
"""

MATERIAL_STATUS_TEMPLATE = """---
title: "자료 진도 — 어느 자료 어느 절까지"
updated: {today}
kind: reading-status
---

# 자료 진도

> 렉처노트·교재를 이어 읽을 때 러너가 먼저 읽는 파일.
> 세션이 끝나면 Issue의 `## 자료 진도 갱신` 절로 갱신된다.
> 절 이름은 그 자료 증류본의 `## 원문 목차`에 있는 것을 그대로 쓴다.

## Progress

- (아직 없음)

## Next Session

- (다음 세션에 열 자료와 절 한 줄)
"""

# 절 이름은 실제 설계도(`mode: topdown`)의 것과 같아야 한다 — `apply_section_patch`가
# 이 제목들을 찾아 본문을 통째로 교체하기 때문이다. 없는 절에 보낸 패치는 조용히 버려진다.
LEARNING_SPEC_TEMPLATE = """---
title: "학습 설계도"
updated: {today}
kind: learning-spec
mode: topdown
---

# 학습 설계도

> **순서의 SSOT.** 실라버스가 없어도 **목표 한 줄**에서 큰 그림 → 개념 분해 → 순서 →
> 검증 기준으로 경로를 만든다. 논문·자료·Parking Lot이 아직 없어도 여기서 시작한다.
>
> **철칙**: 아래 경로는 확정이 아니라 **검증 대상 가설**이다 — 배우면서 교정한다.
> 세션이 끝나면 Issue의 `## 학습 설계도` 절로 갱신된다(손으로 고치지 않는다).
>
> Parking Lot은 이 순서를 **보조**한다 — 논문을 읽다 막힌 개념을 여기 순서에 끼워 넣는다.

## 학습 목표 — 무엇을 할 줄 알게 되는가

- (이 학습이 끝나면 나는 ___를 스스로 설명/수행할 수 있다)

## 큰 그림 (why & 전체 지형)

- (아직 없음 — 목표 한 줄을 러너에게 주면 여기서부터 만든다)

## 학습 경로 (단계·마일스톤)

> `[완료]`는 실측 기록으로 확인된 단계, `[다음]`은 생성된 가설 경로.
> **왜 이 순서인지**(선수 개념)를 각 행에 남긴다.

| 단계 | 주제 | 왜 이 순서 (선수 개념) | 검증 기준 (무엇을 설명할 수 있으면 통과) |
|---|---|---|---|
| 1 `[다음]` | (첫 단계) | (진입점) | (무엇을 설명하면 통과인가) |

## 검증 / 도전

- (각 단계를 통과했다고 볼 근거 — 반박을 견딘 설명)

## 생성 근거 & 반증

- (이 경로를 왜 이렇게 짰나. 배우면서 틀린 것이 나오면 여기 적고 위 표를 고친다)
"""


def ensure_learning_spec(today):
    return ensure_status_file(LEARNING_SPEC_PATH, LEARNING_SPEC_TEMPLATE, today)


def apply_learning_spec(patch, today):
    """`## 학습 설계도` 절 → `learning-spec.md`. 없으면 견본을 먼저 만든다.

    자료 진도(`MATERIAL_STATUS_PATH`)와 **같은 기계**다 — `apply_section_patch`가 이미
    경로를 받으므로 새 코드가 아니라 호출 하나다.
    """
    if not patch:
        return []
    ensure_learning_spec(today)
    return apply_section_patch(patch, today, path=LEARNING_SPEC_PATH)


def build_topics(payload):
    """`[설정]` Issue의 `## 주제` 절 → [{id, label, query, seed, …}].

    형식(러너가 쓰는 것 — `runner/topics.md`와 같아야 한다):

        ## 주제
        ### hbm | HBM (고대역폭 메모리)
        query: high bandwidth memory stacked DRAM
        seed: 10.1109/ISSCC.2022.9731621
        exclude: breast milk | lactation

        ### remove | 지울 주제
        remove: true
    """
    body = assemble(payload)
    _, section = pop_section(body, TOPICS_SECTION)
    # 2026-08-05: 절이 셋(`트랙`·`분야`·`주제`)으로 늘면서 여기서 예외를 던지면 안 된다 —
    # 분배기가 세 파서를 차례로 시도하므로, "내 절이 아니다"는 빈 목록으로 답해야 한다.
    # 무엇도 못 읽었을 때의 오류는 분배기가 세 절을 모두 언급하며 낸다.
    if not section:
        return []

    topics, current = [], None
    for line in section.splitlines():
        line = line.rstrip()
        if line.startswith("### "):
            head = line[4:].strip()
            tid, _, label = head.partition("|")
            current = {"id": slugify(tid.strip()) or slugify(head), "label": label.strip() or tid.strip()}
            topics.append(current)
            continue
        m = re.match(r"^\s*-?\s*(\w+)\s*:\s*(.+)$", line)
        if m and current is not None:
            key, value = m.group(1).strip(), m.group(2).strip()
            if key == "remove":
                current["remove"] = value.lower() in ("true", "yes", "1", "예")
            elif key in TOPIC_FIELDS:
                current[key] = value
    return [t for t in topics if t.get("id") and (t.get("query") or t.get("remove"))]


def build_tracks(payload):
    """`[설정]` Issue의 `## 트랙` 절 → [{id, label, mode, goal}].

        ## 트랙
        ### electronics | 전자공학
        mode: 진도
        goal: 회로 해석을 스스로 설명하기

        ### english | 영어
        remove: true
    """
    body = assemble(payload)
    _, section = pop_section(body, TRACKS_SECTION)
    if not section:
        return []

    tracks, current = [], None
    for line in section.splitlines():
        if line.startswith("### "):
            head = line[4:].strip()
            tid, _, label = head.partition("|")
            # 폴더 이름이 되므로 id는 ASCII 슬러그다 — 한글 폴더는 경로·URL에서 깨진다.
            # 라벨(한글)은 사람이 보는 이름으로 따로 남는다.
            current = {"id": slugify(tid.strip()), "label": label.strip() or tid.strip()}
            if not current["id"]:
                # 한글만 준 경우: 라벨은 그대로 두고 id는 사용자에게 되묻게 만든다.
                current["id"] = ""
            tracks.append(current)
            continue
        m = re.match(r"^\s*-?\s*(\w+)\s*:\s*(.+)$", line)
        if m and current is not None:
            key, value = m.group(1).strip(), m.group(2).strip()
            if key == "remove":
                current["remove"] = value.lower() in ("true", "yes", "1", "예")
            elif key in TRACK_FIELDS:
                current[key] = value
    return [t for t in tracks if t.get("id")]


def build_subjects(payload):
    """`## 분야` → [{name, aliases[], remove?}].

    `### 대표 이름` 아래의 불릿이 별칭이다. 별칭이 없어도 유효하다 — 이름만 등록해 두면
    그 이름으로 적힌 것들이 한 분야로 모인다.
    """
    body = assemble(payload)
    _, section = pop_section(body, SUBJECTS_SECTION)
    if not section:
        return []

    subjects, current = [], None
    for line in section.splitlines():
        line = line.rstrip()
        head = re.match(r"^###\s+(.+?)\s*$", line)
        if head:
            current = {"name": head.group(1).strip().strip("`"), "aliases": []}
            subjects.append(current)
            continue
        if current is None:
            continue
        item = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if not item:
            continue
        value = item.group(1).strip().strip("`")
        if re.match(r"^remove\s*:", value, re.I):
            current["remove"] = value.split(":", 1)[1].strip().lower() in ("true", "yes", "1", "예")
        elif value:
            current["aliases"].append(value)
    return [s for s in subjects if s.get("name")]


def merge_subjects(new, path=SUBJECTS_PATH):
    """subjects.yaml을 대표 이름 단위로 병합한다 — 별칭은 **합집합**이다.

    별칭을 교체하지 않는 이유: 이 파일은 여러 세션에 걸쳐 자란다. 이번에 적지 않은 별칭을
    지우면 지난번에 합쳐 둔 것이 다시 갈라지고, 그래프의 색이 널뛴다.

    파일 위쪽 주석은 그대로 둔다 — 사람이 이 파일을 이해하는 유일한 문서다.
    """
    header, existing = [], []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        cut = next((i for i, l in enumerate(lines) if re.match(r"^subjects:", l)), len(lines))
        header = lines[:cut]
        cur = None
        for line in lines[cut:]:
            if line.lstrip().startswith("#"):
                continue
            m = re.match(r"^\s*-\s*name:\s*(.+)$", line)
            if m:
                cur = {"name": m.group(1).strip().strip("\"'"), "aliases": []}
                existing.append(cur)
                continue
            if cur is None:
                continue
            a = re.match(r"^\s+-\s+(.+)$", line)
            if a:
                cur["aliases"].append(a.group(1).strip().strip("\"'"))
    if not header:
        header = [
            "# 분야(subject) — 지식 그래프에서 개념을 묶어 보는 라벨.",
            "#",
            "# 대표 이름 아래 별칭을 적으면 노트에 그렇게 적혀도 한 분야로 합쳐진다.",
            "# 비어 있으면 정규화를 하지 않는다(안전 기본값).",
            "",
        ]

    by_name = {s["name"]: s for s in existing}
    order = [s["name"] for s in existing]
    added, updated, removed = [], [], []
    for s in new:
        name = s["name"]
        if s.get("remove"):
            if name in by_name:
                by_name.pop(name)
                order.remove(name)
                removed.append(name)
            continue
        if name in by_name:
            seen = set(by_name[name]["aliases"])
            fresh = [a for a in s["aliases"] if a not in seen]
            if fresh:
                by_name[name]["aliases"].extend(fresh)   # 합집합 — 지우지 않는다
                updated.append(name)
        else:
            by_name[name] = {"name": name, "aliases": list(s["aliases"])}
            order.append(name)
            added.append(name)

    out = list(header)
    if out and out[-1].strip():
        out.append("")
    out.append("subjects:" if order else "subjects: []")
    for name in order:
        out.append(f'  - name: "{name.replace(chr(34), chr(39))}"')
        aliases = by_name[name]["aliases"]
        if aliases:
            out.append("    aliases:")
            for a in aliases:
                out.append(f'      - "{a.replace(chr(34), chr(39))}"')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return added, updated, removed


def build_overrides(payload):
    """`## 지도` 절 → {"hidden": [...], "renamed": [{from,to}]}.

    형식은 사람이 Issue에 손으로 적어도 되게 단순하게 둔다:

        ## 지도
        ### 감추기
        - 오늘 한 것
        ### 이름 합치기
        - Fréchet 평균 → Fréchet mean

    화살표는 `→`·`->`·`=>`를 받는다. 개념 지도(`←`)와 방향이 **반대**인 것이 중요하다:
    저기서는 "무엇이 필요한가"이고 여기서는 "무엇으로 바뀌는가"다.
    """
    body = assemble(payload)
    _, section = pop_section(body, OVERRIDES_SECTION)
    if not section:
        return {}

    hidden, renamed, mode = [], [], ""
    for line in section.splitlines():
        head = re.match(r"^#{3,}\s*(.+?)\s*$", line.strip())
        if head:
            name = head.group(1).strip()
            mode = "hidden" if "감추" in name else "renamed" if "이름" in name or "합치" in name else ""
            continue
        item = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if not item:
            continue
        value = item.group(1).strip().strip("`")
        if mode == "hidden":
            if value:
                hidden.append(value)
        elif mode == "renamed":
            parts = re.split(r"→|->|=>", value, maxsplit=1)
            if len(parts) == 2:
                src, dst = parts[0].strip().strip("`"), parts[1].strip().strip("`")
                if src and dst:
                    renamed.append({"from": src, "to": dst})

    if not hidden and not renamed:
        return {}
    return {"hidden": hidden, "renamed": renamed}


def merge_overrides(new, path=OVERRIDES_PATH):
    """concepts-overrides.yaml 병합 — 지금 것에 **더한다**(지우지 않는다).

    덮어쓰지 않는 이유는 subjects.yaml과 같다: 이 파일은 여러 세션에 걸쳐 자란다.
    이번에 안 적은 항목을 지우면 지난번에 감춘 노드가 슬그머니 되살아난다.

    되돌리기는 사용자가 이 파일에서 한 줄을 지우는 것으로 한다 — 감추기를 취소하는
    Issue를 또 만들면, 무엇이 현재 상태인지가 Issue 이력에 흩어진다.
    """
    header, hidden, renamed = [], [], []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        cut = next((i for i, l in enumerate(lines) if re.match(r"^(hidden|renamed):", l)), len(lines))
        header = lines[:cut]
        mode, pending = "", None
        for line in lines[cut:]:
            if line.lstrip().startswith("#"):
                continue
            m = re.match(r"^(hidden|renamed):\s*(\[\])?\s*$", line)
            if m:
                mode, pending = m.group(1), None
                continue
            if mode == "hidden":
                item = re.match(r"^\s*-\s+(.+)$", line)
                if item:
                    hidden.append(item.group(1).strip().strip("\"'"))
            elif mode == "renamed":
                f_m = re.match(r"^\s*-\s*from:\s*(.+)$", line)
                t_m = re.match(r"^\s*to:\s*(.+)$", line)
                if f_m:
                    pending = {"from": f_m.group(1).strip().strip("\"'")}
                elif t_m and pending:
                    pending["to"] = t_m.group(1).strip().strip("\"'")
                    renamed.append(pending)
                    pending = None
    if not header:
        header = [
            "# 지식 그래프 손보기 — 지도만 고친다. 기록(daily 노트)은 그대로 둔다.",
            "#",
            "# hidden   그래프에서 뺀다 (한 줄 지우면 되돌아온다)",
            "# renamed  같은 것으로 합친다 (별칭이라 다음 세션에도 계속 합쳐진다)",
        ]

    added_hidden = [h for h in (new.get("hidden") or []) if h not in hidden]
    hidden.extend(added_hidden)

    known = {(r.get("from"), r.get("to")) for r in renamed}
    added_renamed = [
        r for r in (new.get("renamed") or [])
        # 자기 자신으로 바꾸기는 무한 루프의 씨앗이라 파일에 넣지 않는다.
        if r.get("from") and r.get("to") and r["from"] != r["to"]
        and (r["from"], r["to"]) not in known
    ]
    renamed.extend(added_renamed)

    def quote(v):
        return '"' + str(v).replace('"', "'") + '"'

    out = list(header)
    if out and out[-1].strip():
        out.append("")
    out.append("hidden:" if hidden else "hidden: []")
    out.extend(f"  - {quote(h)}" for h in hidden)
    out.append("")
    out.append("renamed:" if renamed else "renamed: []")
    for r in renamed:
        out.append(f"  - from: {quote(r['from'])}")
        out.append(f"    to: {quote(r['to'])}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return added_hidden, added_renamed


def merge_tracks(new, path=TRACKS_PATH):
    """tracks.yaml을 id 단위로 병합한다(topics와 같은 규칙).

    ⚠️ 트랙을 지워도 `daily/<id>/`의 기록은 지우지 않는다 — 서랍 목록에서 빠질 뿐,
    그동안 공부한 것은 학습자의 것이다.
    """
    header, existing = [], []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        cut = next((i for i, l in enumerate(lines) if re.match(r"^tracks:", l)), len(lines))
        header = lines[:cut]
        cur = None
        for line in lines[cut:]:
            m = re.match(r"^\s*-\s*(\w+):\s*(.*)$", line)
            if m:
                cur = {m.group(1): m.group(2).strip().strip("\"'")}
                existing.append(cur)
                continue
            m = re.match(r"^\s+(\w+):\s*(.*)$", line)
            if m and cur is not None:
                cur[m.group(1)] = m.group(2).strip().strip("\"'")
    if not header:
        header = [
            "# 학습 트랙 — 세션을 담는 서랍. 러너가 `[설정]` Issue로 갱신한다.",
            "#",
            "# 세션 노트는 `daily/<id>/`에 쌓인다. 트랙이 없으면 `daily/` 루트에 그대로 쌓인다",
            "# (지금까지 쓰던 방식 — 트랙은 선택이다).",
            "#",
            "# id는 폴더 이름이라 영문 소문자-하이픈, label은 사람이 보는 이름이다.",
            "",
        ]

    by_id = {t.get("id"): t for t in existing if t.get("id")}
    order = [t.get("id") for t in existing if t.get("id")]
    added, updated, removed = [], [], []
    for t in new:
        tid = t["id"]
        if t.get("remove"):
            if tid in by_id:
                by_id.pop(tid)
                order.remove(tid)
                removed.append(tid)
            continue
        if tid in by_id:
            by_id[tid].update({k: v for k, v in t.items() if k != "remove"})
            updated.append(tid)
        else:
            by_id[tid] = {k: v for k, v in t.items() if k != "remove"}
            order.append(tid)
            added.append(tid)

    out = list(header)
    if out and out[-1].strip():
        out.append("")
    out.append("tracks:" if order else "tracks: []")
    for tid in order:
        t = by_id[tid]
        out.append(f"  - id: {tid}")
        for key in TRACK_FIELDS:
            if t.get(key):
                out.append(f'    {key}: "{str(t[key]).replace(chr(34), chr(39))}"')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return added, updated, removed


def merge_topics(new, path=TOPICS_PATH):
    """topics.yaml을 id 단위로 병합한다 — 러너가 빠뜨린 주제를 지우지 않는다.

    파일 위쪽의 주석·설정(mailto·window_days…)은 그대로 두고 `topics:` 블록만 다시 쓴다.
    그 주석이 사람이 이 파일을 이해하는 유일한 문서라, 러너가 갱신했다고 사라지면 안 된다.
    """
    header, existing = [], []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        cut = next((i for i, l in enumerate(lines) if re.match(r"^topics:", l)), len(lines))
        header = lines[:cut]
        cur = None
        for line in lines[cut:]:
            m = re.match(r"^\s*-\s*(\w+):\s*(.*)$", line)
            if m:
                cur = {m.group(1): m.group(2).strip().strip("\"'")}
                existing.append(cur)
                continue
            m = re.match(r"^\s+(\w+):\s*(.*)$", line)
            if m and cur is not None and not line.lstrip().startswith("#"):
                cur[m.group(1)] = m.group(2).strip().strip("\"'")
    if not header:
        header = ["# 논문 스케줄링 — 러너가 `[설정]` Issue로 갱신한다.", ""]

    by_id = {t.get("id"): t for t in existing if t.get("id")}
    order = [t.get("id") for t in existing if t.get("id")]
    added, updated, removed = [], [], []
    for t in new:
        tid = t["id"]
        if t.get("remove"):
            if tid in by_id:
                by_id.pop(tid)
                order.remove(tid)
                removed.append(tid)
            continue
        if tid in by_id:
            by_id[tid].update({k: v for k, v in t.items() if k != "remove"})
            updated.append(tid)
        else:
            by_id[tid] = {k: v for k, v in t.items() if k != "remove"}
            order.append(tid)
            added.append(tid)

    out = list(header)
    if out and out[-1].strip():
        out.append("")
    out.append("topics:")
    if not order:
        out[-1] = "topics: []"
    for tid in order:
        t = by_id[tid]
        out.append(f"  - id: {tid}")
        for key in ("label", *TOPIC_FIELDS):
            if t.get(key):
                out.append(f'    {key}: "{str(t[key]).replace(chr(34), chr(39))}"')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return added, updated, removed


def ensure_status_file(path, template, today):
    """없으면 만든다 — 있으면 손대지 않는다(학습자의 기록이다)."""
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(template.format(today=today))
    return True


DELETE_SECTION = "삭제"

# 지울 수 있는 뿌리는 둘뿐이다. 다른 것을 여기 넣으면 이 스크립트가 repo 루트에서
# 도는 것을 잊은 셈이 된다 — `daily/`나 `.github/`가 이 목록에 들어오면 안 된다.
DELETABLE_ROOTS = (MATERIALS_DIR, PAPERS_DIR)

# 앱의 `SLUG_RE`(`lib/knowledge/materialPaths.ts`)와 **같은 모양**이어야 한다.
# `.`이 없으므로 `..`이 만들어질 수 없고, `/`가 없으므로 경로를 벗어날 수 없다.
DELETE_SLUG_RE = re.compile(r"^[\w가-힣-]{1,64}$")


def parse_delete_targets(body):
    """`## 삭제` 절의 `- <root>/<slug>` 줄을 (root, slug) 목록으로.

    **모양이 아닌 줄은 조용히 버리지 않고 돌려준다** — 왜 안 지워졌는지 보고해야 한다.
    이 값이 `shutil.rmtree`의 경로가 되므로 여기가 마지막 관문이다(앱도 자기 쪽에서 막지만
    Issue는 사람이 손으로도 만들 수 있다).
    """
    ok, bad = [], []
    for raw in (body or "").splitlines():
        line = re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", raw).strip().strip("`")
        if not line or line.startswith(">"):
            continue
        parts = line.split("/")
        if len(parts) != 2:
            bad.append(line)
            continue
        root, slug = parts[0].strip(), parts[1].strip()
        if root not in DELETABLE_ROOTS or not DELETE_SLUG_RE.match(slug):
            bad.append(line)
            continue
        if (root, slug) not in ok:
            ok.append((root, slug))
    return ok, bad


def strip_slug_from_status(path, slug):
    """진도 파일에서 그 자료를 말하는 불릿 줄을 뺀다.

    폴더만 지우면 `READING_STATUS.md`에 없는 자료의 진도가 남는다. 화면은 자료가 없으니
    그리지 않지만, **러너는 그 파일을 매 세션 읽는다** — 지운 논문을 계속 "다음에 읽을 것"으로
    본다. 절 구조(`## Progress` 등)는 건드리지 않고 줄만 뺀다.
    """
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    keep = [l for l in lines if not (l.lstrip().startswith(("-", "*", "1.")) and slug in l)]
    if len(keep) == len(lines):
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(keep).rstrip() + "\n")
    return True


def delete_materials(targets):
    """자료 폴더를 통째로 지우고 진도 파일에서도 그 slug를 뺀다.

    폴더형이 아닌 옛 단일 파일(`<root>/<slug>.md`)도 함께 지운다 — `build_material`이
    승격할 때 지우던 그 파일이고, 남겨 두면 목록에 그대로 뜬다.
    """
    removed, missing, touched = [], [], []
    for root, slug in targets:
        folder = os.path.join(root, slug)
        single = os.path.join(root, f"{slug}.md")
        hit = False
        if os.path.isdir(folder):
            shutil.rmtree(folder)
            hit = True
        if os.path.exists(single):
            os.remove(single)
            hit = True
        (removed if hit else missing).append(f"{root}/{slug}")

        for status in (READING_STATUS_PATH, MATERIAL_STATUS_PATH):
            if strip_slug_from_status(status, slug) and status not in touched:
                touched.append(status)
    return removed, missing, touched


def ensure_reading_status(today):
    return ensure_status_file(READING_STATUS_PATH, READING_STATUS_TEMPLATE, today)


def ensure_position_section(path=READING_STATUS_PATH):
    """기존 `READING_STATUS.md`에 `## Position` 절이 없으면 끝에 덧붙인다.

    `ensure_status_file`은 파일이 있으면 손대지 않는다(학습자의 기록이라 의도된 것) —
    그래서 템플릿에 절을 새로 넣어도 이미 세션을 한 번이라도 돌린 학습자의 파일에는
    오지 않는다. 이 함수는 그 계약을 건드리지 않고 **새로 추가된 절 하나**만 뒤늦게
    채워 넣는 좁은 통로다. 이미 있으면 아무 일도 하지 않는다(멱등).
    """
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if "## Position" in content:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.rstrip("\n") + "\n\n## Position\n\n- (아직 없음)\n")
    return True


def ensure_material_status(today):
    return ensure_status_file(MATERIAL_STATUS_PATH, MATERIAL_STATUS_TEMPLATE, today)


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Issue → daily 세션 로그 수집기")
    ap.add_argument("--payload", required=True, help="Issue payload JSON 경로")
    ap.add_argument("--today", default=kst_today(), help="KST 기준 오늘 (YYYY-MM-DD)")
    ap.add_argument("--report", help="사람이 읽을 결과 보고서를 쓸 경로(Issue 코멘트용)")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    args = ap.parse_args()

    with open(args.payload, encoding="utf-8") as f:
        payload = json.load(f)

    # `[논문]` — 논문 한 편을 여러 세션에 걸쳐 관통한다. 날짜가 아니라 논문이 묶는 단위다.
    if (payload.get("title") or "").startswith("[논문]"):
        note = build_paper_session(payload, args.today)
        if args.dry_run:
            print(f"[dry-run] {note['root']}/{note['slug']}/sessions/… ({note['section']})\n")
            print(note["body"])
            return
        touched, applied, extra = write_paper_session(note, payload, args.today)
        report = [
            f"✅ 논문 세션 기록 완료 — `{touched[0]}`",
            "",
            f"- 자료: `{note['root']}/{note['slug']}` · 섹션: {note['section']}",
        ]
        if note["meta"].get("understanding"):
            report.append(f"- 이해 단계: **{note['meta']['understanding']}**")
        added, resolved = extra["parked"]
        if added or resolved:
            report.append(
                f"- Parking Lot: 새 항목 {added}개"
                + (f" · 해소 {resolved}개" if resolved else "")
                + " → `{}/{}/parking-lot.md`".format(note["root"], note["slug"])
            )
        if extra["artifacts"]:
            report.append(f"- 아티팩트 {len(extra['artifacts'])}개 저장 (다음 세션 복습용)")
        if len(touched) > 1:
            report.append("- 갱신: " + ", ".join(f"`{t}`" for t in touched[1:]))
        if applied:
            report.append(f"- READING_STATUS 갱신: {', '.join(applied)}")
        else:
            report.append(
                "- ℹ️ READING_STATUS는 갱신하지 않았다 — `## READING_STATUS 갱신` 절이 없거나 "
                f"`{READING_STATUS_PATH}`가 아직 없다."
            )
        text = "\n".join(report)
        print(text)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        return

    # `[설정]` — 학습 기록이 아니라 설정 파일(topics.yaml)의 쓰기 경로다.
    if (payload.get("title") or "").startswith("[설정]"):
        """
        자료 삭제 — 앱의 「삭제」가 만든 Issue. **가장 먼저 본다**: 되돌리기 어려운 동작이므로
        다른 절 파싱에 섞여 들어가지 않게 한다.

        새 제목 prefix를 만들지 않은 이유: 워크플로의 `if:` 게이트와 아래 `PREFIXES` 배열이
        같은 목록을 두 벌 들고 있고(이 파일이 스스로 경고한다 — *"한쪽만 열면 잡이 돌다가
        실패한다"*), `[설정]`에 절을 더하면 그 두 곳을 안 건드린다.

        워크플로도 안 고쳤다 — 커밋 스텝의 `git add -A … materials papers …`가 **삭제도 그대로
        스테이징한다**(`os.remove(stale)`가 이미 이 경로로 동작 중인 증거).
        """
        _, delete_body = pop_section(assemble(payload), DELETE_SECTION)
        if delete_body:
            targets, bad = parse_delete_targets(delete_body)
            if args.dry_run:
                print(f"[dry-run] 삭제 대상 {len(targets)}건: {targets}")
                if bad:
                    print(f"[dry-run] 모양이 아니라 건너뜀: {bad}")
                return
            removed, missing, touched = delete_materials(targets)
            report = [f"✅ 자료 {len(removed)}건 삭제", ""]
            if removed:
                report.append("- 지움: " + ", ".join(f"`{p}`" for p in removed))
            if touched:
                report.append("- 진도 파일에서도 뺐다: " + ", ".join(f"`{t}`" for t in touched))
            if missing:
                # 이미 없는 것을 지우라고 한 경우 — 실패가 아니지만 말해 준다(두 번 눌렀거나
                # 앞선 삭제가 이미 처리했다).
                report.append("- ℹ️ 이미 없었다: " + ", ".join(f"`{p}`" for p in missing))
            if bad:
                report.append(
                    "- ⚠️ 모양이 아니라 **지우지 않았다**: "
                    + ", ".join(f"`{b}`" for b in bad)
                    + " (`materials/<slug>` 또는 `papers/<slug>` 꼴이어야 한다)"
                )
            report += [
                "",
                "> `concepts.json`은 다음 CI 실행에서 자동으로 다시 만들어진다 —"
                " 지운 자료의 개념 간선은 그때 빠진다.",
            ]
            text = "\n".join(report)
            print(text)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
            return

        # 학습 설계도 — **새 사용자의 첫 파일.** 목표 한 줄에서 러너가 경로를 만들어
        # 승인받은 뒤 이 절로 보낸다. 세션 기록이 아니므로 `[설정]`이 맞는 자리다.
        _, spec_patch = extract_status_patch(assemble(payload), LEARNING_SPEC_SECTION)
        if spec_patch:
            if args.dry_run:
                print(f"[dry-run] {LEARNING_SPEC_PATH}\n")
                print(json.dumps(spec_patch, ensure_ascii=False, indent=2))
                return
            created = not os.path.exists(LEARNING_SPEC_PATH)
            spec_applied = apply_learning_spec(spec_patch, args.today)
            report = [
                f"✅ 학습 설계도 {'생성' if created else '갱신'} — `{LEARNING_SPEC_PATH}`",
                "",
            ]
            if spec_applied:
                report.append(f"- 갱신된 절: {', '.join(spec_applied)}")
            skipped = [k for k in spec_patch if k not in spec_applied]
            if skipped:
                # 없는 절에 보낸 패치는 조용히 버려진다 — 그것을 말한다.
                report.append(
                    f"- ⚠️ 설계도에 없는 절이라 건너뜀: {', '.join(skipped)} "
                    "(견본의 절 이름을 그대로 쓴다)"
                )
            report += [
                "",
                "> 이 순서가 앞으로 모든 과목 세션의 시작점이다. Parking Lot은 이 순서를 **보조**한다.",
            ]
            text = "\n".join(report)
            print(text)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
            return

        # 트랙(학습 서랍)과 주제(논문 수집)는 같은 `[설정]` Issue로 온다 — 둘 다 설정이고,
        # 사용자에게 "이건 어느 Issue로 쓰지"를 고르게 하지 않는다.
        tracks = build_tracks(payload)
        if tracks:
            added, updated, removed = merge_tracks(tracks)
            report = [f"✅ 학습 트랙 갱신 — `{TRACKS_PATH}`", ""]
            if added:
                report.append(f"- 추가: {', '.join(f'`{t}`' for t in added)} → 세션은 `daily/<id>/`에 쌓인다")
            if updated:
                report.append(f"- 갱신: {', '.join(f'`{t}`' for t in updated)}")
            if removed:
                report.append(
                    f"- 목록에서 제거: {', '.join(f'`{t}`' for t in removed)} "
                    "(그동안의 기록은 지우지 않는다)"
                )
            report += ["", "> 다음 세션부터 러너가 \"오늘은 어느 트랙?\"을 묻고 그 폴더에 저장한다."]
            text = "\n".join(report)
            print(text)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
            if not build_topics(payload):
                return

        overrides = build_overrides(payload)
        if overrides:
            if args.dry_run:
                print(f"[dry-run] {OVERRIDES_PATH}\n")
                print(json.dumps(overrides, ensure_ascii=False, indent=2))
                return
            added_hidden, added_renamed = merge_overrides(overrides)
            report = [f"✅ 지식 그래프 손보기 — `{OVERRIDES_PATH}`", ""]
            if added_hidden:
                report.append(f"- 감춤: {', '.join(f'`{h}`' for h in added_hidden)}")
            if added_renamed:
                report.append(
                    "- 이름 합치기: "
                    + ", ".join(f"`{r['from']}` → `{r['to']}`" for r in added_renamed)
                )
            if not added_hidden and not added_renamed:
                report.append("- 바뀐 것 없음 (이미 적용돼 있다)")
            report += [
                "",
                "> **노트와 원장은 그대로다.** 그래프에서만 빠진다 — 되돌리려면 "
                f"`{OVERRIDES_PATH}`에서 그 줄을 지우면 다음 빌드에 돌아온다.",
            ]
            text = "\n".join(report)
            print(text)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
            return

        subjects = build_subjects(payload)
        if subjects:
            if args.dry_run:
                print(f"[dry-run] {SUBJECTS_PATH}\n")
                print(json.dumps(subjects, ensure_ascii=False, indent=2))
                return
            added, updated, removed = merge_subjects(subjects)
            report = [f"✅ 분야 갱신 — `{SUBJECTS_PATH}`", ""]
            if added:
                report.append(f"- 추가: {', '.join(f'`{t}`' for t in added)}")
            if updated:
                report.append(f"- 별칭 추가: {', '.join(f'`{t}`' for t in updated)}")
            if removed:
                report.append(f"- 삭제: {', '.join(f'`{t}`' for t in removed)}")
            report += [
                "",
                "> 다음 세션의 개념 지도부터 이 이름으로 합쳐집니다. 지난 노트는 고치지 "
                "않습니다 — 합치기는 그래프를 만들 때 일어납니다(`build_concepts`).",
            ]
            text = "\n".join(report)
            print(text)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
            return

        topics = build_topics(payload)
        if not topics:
            raise SystemExit(
                "`## 트랙`·`## 분야`·`## 주제` 중 어느 절도 못 읽었다 — "
                "`[설정]` Issue는 그중 한 절에 `### <이름>` 형식으로 적어야 한다."
            )
        if args.dry_run:
            print(f"[dry-run] {TOPICS_PATH}\n")
            print(json.dumps(topics, ensure_ascii=False, indent=2))
            return
        added, updated, removed = merge_topics(topics)
        unanchored = [
            t["id"] for t in topics
            if not t.get("remove") and not (t.get("seed") or t.get("topics") or t.get("field"))
        ]
        report = [f"✅ 연구 주제 갱신 — `{TOPICS_PATH}`", ""]
        if added:
            report.append(f"- 추가: {', '.join(f'`{t}`' for t in added)}")
        if updated:
            report.append(f"- 갱신: {', '.join(f'`{t}`' for t in updated)}")
        if removed:
            report.append(f"- 삭제: {', '.join(f'`{t}`' for t in removed)}")
        if unanchored:
            report += [
                "",
                f"⚠️ **분야가 고정되지 않은 주제**: {', '.join(f'`{t}`' for t in unanchored)}",
                "",
                "이 주제들은 단어로만 검색된다 — 약어가 겹치면 엉뚱한 분야가 섞인다"
                "(`HBM` → high bandwidth memory / human breast milk).",
                "러너에게 **씨앗 논문 DOI**를 하나 주면(`seed:`) 그 논문의 분야로 고정된다.",
            ]
        report += [
            "",
            "> 다음 `paper-scan`(매주 월요일 또는 Actions → Run workflow)부터 적용된다.",
        ]
        text = "\n".join(report)
        print(text)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        return

    # `[자료]` — 세션 로그가 아니라 증류된 학습자료다. 별도 경로로 저장하고 끝낸다.
    if (payload.get("title") or "").startswith("[자료]"):
        note = build_material(payload, args.today)
        root = note["root"]
        # 논문은 slug가 지시행으로 못박혀 있다(그 논문 폴더에 들어가야 한다).
        slug = note["slug"] if root == PAPERS_DIR else (
            existing_material_slug(payload.get("number")) or note["slug"]
        )

        if note["files"] is not None:
            # 폴더형 — 증류와 원문을 나눈다. 경로 계약은 Topdown `materialPaths.ts`의
            # `MATERIAL_RE`가 이미 허용한다(`materials/<slug>/(source|distilled).md`).
            folder = os.path.join(root, slug)
            writes = [(os.path.join(folder, name), c) for name, c in sorted(note["files"].items())]
            # 같은 자료가 전에 단일 파일로 저장돼 있었다면 지운다. 남겨 두면 같은 개념
            # 지도가 두 번 읽혀 그래프에 중복 간선이 생긴다(빌더는 materials/**를 다 본다).
            stale = os.path.join(root, f"{slug}.md")
        else:
            writes = [(os.path.join(root, f"{slug}.md"), note["flat"])]
            stale = None

        if args.dry_run:
            for path, content in writes:
                print(f"[dry-run] {path}\n")
                print(content)
            return
        for path, content in writes:
            os.makedirs(os.path.dirname(path) or MATERIALS_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        if stale and os.path.isfile(stale):
            os.remove(stale)

        path = writes[0][0]
        saved = " · ".join(f"`{p}` ({len(c.splitlines())}줄)" for p, c in writes)
        if note["files"] and len(writes) > 1:
            report = [
                f"✅ 자료 저장 — {saved}",
                "",
                "- 요약·개념 지도·빈칸 문제 은행이 증류본에 있다 — `## 개념 지도`는 그래프로 간다.",
                "- 증류본의 `## 원문 목차`에서 절을 고르고 "
                "`read_doc`의 `section`으로 그 절의 원문만 읽는다.",
                "- 원문은 그대로 보존됐다 — 인용 근거이고, 러너가 읽을 수 있다.",
            ]
        elif note["files"] and not note["distilled"]:
            report = [
                f"✅ 원문 저장 — {saved}",
                "",
                "- ⚠️ **증류는 없다** — `## 개념 지도`가 없어 그래프에 들어가는 것은 없다.",
                "- 원문은 그대로 보존됐다. 러너가 `read_doc`으로 절 단위로 읽을 수 있다.",
            ]
        elif note["distilled"]:
            lines = len(writes[0][1].splitlines())
            report = [
                f"✅ 자료 지도 저장 — `{path}` ({lines}줄)",
                "",
                "- 요약·개념 지도·빈칸 문제 은행이 들어 있다 — `## 개념 지도`는 그래프로 간다.",
                "- 다음 세션부터 러너가 이 파일을 readFile로 끌어와 쓴다.",
            ]
        else:
            # 증류를 대신 해 주지 않는다(이 CI는 LLM 토큰 0이 원칙이다). 대신 무엇이 저장됐고
            # 무엇이 없는지 정확히 말한다 — 라벨과 보고가 어긋나면 저작권 판단까지 오도한다.
            report = [
                f"✅ 자료 원문 저장 — `{path}` ({len(writes[0][1].splitlines())}줄)",
                "",
                "- ⚠️ **증류는 없다** — `## 개념 지도`가 없어 `tags: [material, raw]`로 적었다.",
                "  그래프에 들어가는 것은 없다(선수관계는 `## 개념 지도`에서만 읽는다).",
                "- 세션에서 이 자료를 증류하려면 러너에게 "
                "`이 자료 증류해줘 — 요약·개념 지도·빈칸 문제로.`라고 한다.",
                "- 다음 세션부터 러너가 이 파일을 readFile로 끌어와 쓴다.",
            ]
        text = "\n".join(report)
        print(text)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"path={path}\n")
        return

    note = build_note(payload, args.today)
    if len(note["content"].strip().splitlines()) < 4:
        raise SystemExit("본문이 비었다 — 수집할 내용이 없다.")

    # 트랙(과목 서랍) — 있으면 `daily/<track>/`으로 간다. 러너가 안 적었거나 없는 이름을
    # 적었으면 루트에 쓰고 **그 사실을 회신에 적는다**(조용히 섞이면 다음 세션이 헷갈린다).
    tracks = load_tracks()
    track = resolve_track(note["track"], tracks)
    track_note = ""
    if tracks and not track:
        names = ", ".join(f"`{t['id']}`" for t in tracks)
        why = "`track:`을 적지 않아" if not note["track"] else f"`{note['track']}`와 맞는 트랙이 없어"
        track_note = f"⚠️ {why} `daily/` 루트에 저장했다. 쓸 수 있는 트랙: {names}"

    path = target_path(note["date"], note["slug"], payload.get("number"), track)
    if args.dry_run:
        print(f"[dry-run] {path}\n")
        print(note["content"])
        return

    os.makedirs(os.path.dirname(path) or DAILY_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(note["content"])
    applied = apply_status_patch(note["status_patch"], args.today)
    # 자료 진도 — 논문의 READING_STATUS와 같은 기계다(절 교체). 절이 없으면 아무 일도 없다.
    # `applied`에 섞지 않는다 — 섞으면 보고가 "STATUS.md 갱신"이라고 거짓말한다.
    material_applied = []
    if note["material_patch"]:
        ensure_material_status(args.today)
        material_applied = apply_section_patch(
            note["material_patch"], args.today, path=MATERIAL_STATUS_PATH
        )
    spec_applied = apply_learning_spec(note["spec_patch"], args.today)
    if append_trajectory(note["display"], note["date"], path, args.today):
        applied.append(TRAJECTORY_SECTION)
    promoted = write_mastery_fragment(note["mastery"], note["track"], note["date"], note["slug"], path)
    drilled = append_drills(note["drills"], note["date"])

    lines_written = len(note["content"].splitlines())
    report = [
        f"✅ 학습 노트 기록 완료 — `{path}` ({lines_written}줄)",
        "",
        f"- 수집 조각: 본문 1 + 코멘트 {len(payload.get('comments') or [])}개",
    ]
    if track:
        report.append(f"- 트랙: `{track}` (같은 과목의 세션은 이 폴더에 모인다)")
    elif track_note:
        report.append(f"- {track_note}")
    if applied:
        report.append(f"- STATUS.md 갱신: {', '.join(applied)}")
    if material_applied:
        report.append(
            f"- 자료 진도 갱신: `{MATERIAL_STATUS_PATH}` — {', '.join(material_applied)}"
        )
    if spec_applied:
        report.append(
            f"- 학습 설계도 갱신: `{LEARNING_SPEC_PATH}` — {', '.join(spec_applied)}"
        )
    if promoted:
        report.append(f"- 이해도 승급 조각: `{promoted}`" if promoted.endswith(".md") else f"- {promoted}")
    if drilled:
        report.append(f"- 드릴 항목 {drilled}개 → `{DRILLS_PATH}` (그래프에는 넣지 않는다 — 회상 대상이다)")
    if note["missing"]:
        report.append(f"- ⚠️ 정규 헤딩 자동 보정: {', '.join(note['missing'])} — 다음 세션에서 실제로 채울 것")
    report += [
        "",
        "> 이 노트는 모델이 아니라 CI가 결정론적으로 썼다(base64·sha 경로 없음). "
        "길이 때문에 커밋이 실패하지 않는다.",
    ]
    text = "\n".join(report)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"path={path}\n")


if __name__ == "__main__":
    sys.exit(main())
