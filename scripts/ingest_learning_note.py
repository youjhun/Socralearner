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

TRAJECTORY_SECTION = "최근 궤적"
# 최근 궤적은 교체가 아니라 누적이다. 무한정 쌓으면 STATUS.md가 커져 러너가 매 세션
# 통째로 읽는 비용이 오르므로(이 파일의 존재 이유가 "작게 유지"다) 최근 것만 남긴다.
TRAJECTORY_KEEP = 7

# `## 드릴 항목` — 회상 대상(단어 뜻·연호·값)은 개념 지도가 아니라 여기로 온다.
# 2026-08-03: 토익 트랙에서 지식 그래프가 단어 단위로 생성된 것을 고치며 생긴 경로다.
# 개념의 단위 정의는 runner/instructions.md의 "개념의 단위"에 있다. 여기는 그 저장 경로일 뿐이다.
DRILLS_SECTION = "드릴 항목"
DRILLS_PATH = "drills.md"
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
PAPER_SECTIONS = {
    "정제본 갱신": "paper.md",
    "주석": "annotations.md",
}
READING_STATUS_SECTION = "READING_STATUS 갱신"
READING_STATUS_PATH = os.path.join(PAPERS_DIR, "READING_STATUS.md")

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


def build_material(payload, today):
    """`[자료]` Issue → materials/<slug>.md — 강의자료(PDF)를 **1회 증류**한 파생 학습자료.

    왜 이 경로인가: Custom GPT Action 응답은 텍스트라 repo의 PDF를 세션에서 읽을 수
    없다. 그래서 PDF는 대화에 한 번 올리고, 요약(지도)·개념 지도·빈칸 문제 은행을
    텍스트로 남긴다 — 이후 세션은 readFile로 끌어온다. 원문 PDF는 저장하지 않는다
    (저작권·용량). 정규 헤딩 강제·STATUS/mastery 처리도 하지 않는다(세션 로그가 아니다).
    """
    raw = assemble(payload)
    user_fm, body = split_frontmatter(raw)
    title = payload.get("title") or ""
    head, _, tail = title.partition("—")
    if not tail:
        head, _, tail = title.partition(" - ")
    slug = user_fm.get("slug") or slugify(head) or f"material-{payload.get('number', '0')}"
    display = (tail or head).strip()
    display = re.sub(r"^\s*\[[^\]]*\]\s*", "", display).strip()
    display = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", display).strip() or slug
    fm = [
        "---",
        f'title: "{display}"',
        f"created: {today}",
        f"updated: {today}",
        "tags: [material, distilled]",
        f'source: "자료 증류 → Issue #{payload.get("number")} (원문 PDF는 저장하지 않음)"',
        "kind: material",
        f"source_issue: {payload.get('number')}",
        "---",
    ]
    if not re.match(r"^#\s", body):
        body = f"# {display}\n\n" + body
    return {"slug": slug, "content": "\n".join(fm) + "\n\n" + body.rstrip() + "\n"}


def build_note(payload, today):
    raw = assemble(payload)
    user_fm, body = split_frontmatter(raw)

    # 본문 맨 앞의 지시행(slug:, runner:)도 frontmatter처럼 취급하고 제거한다.
    directives = {}
    lines = body.splitlines()
    while lines and re.match(r"^(slug|runner|course|week|exam_target|tags|track|artifact)\s*:\s*\S", lines[0].strip()):
        key, value = lines[0].split(":", 1)
        directives[key.strip()] = value.strip()
        lines.pop(0)
    body = "\n".join(lines).strip()
    user_fm = {**directives, **user_fm}

    body, status_patch = extract_status_patch(body)
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
    for key in ("course", "week", "exam_target", "artifact"):
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
        "mastery": mastery,
        "drills": drills,
        "track": user_fm.get("track", ""),
        "display": display,
        "missing": missing,
    }


# --------------------------------------------------------------------------- 쓰기


def target_path(date, slug, issue_number):
    """같은 Issue를 다시 수집하면 같은 파일을 덮어쓴다(재실행 안전)."""
    marker = f"source_issue: {issue_number}"
    if os.path.isdir(DAILY_DIR):
        for name in sorted(os.listdir(DAILY_DIR)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(DAILY_DIR, name)
            with open(path, encoding="utf-8") as f:
                if marker in f.read(2000):
                    return path

    base = os.path.join(DAILY_DIR, f"{date}-{slug}.md")
    if not os.path.exists(base):
        return base
    for n in range(2, 20):
        candidate = os.path.join(DAILY_DIR, f"{date}-{slug}-{n}.md")
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

        lines[idx + 1:end] = (keep or [""]) + [content, ""]
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
    while lines and re.match(r"^(slug|runner|tags)\s*:\s*\S", lines[0].strip()):
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
        "section": section_name,
        "body": body,
        "reading_patch": reading_patch,
        "section_patches": section_patches,
        "runner": user_fm.get("runner", "paper-gpt"),
    }


def write_paper_session(note, payload, today):
    """세션 원문을 논문 폴더에 쓰고, 정제본·주석·READING_STATUS를 갱신한다."""
    folder = os.path.join(PAPERS_DIR, note["slug"])
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

    # `papers/`는 sync_from_template의 NEVER 경로다 — 템플릿을 갱신해도 기존 학습자의
    # repo에는 이 파일이 오지 않는다. 그래서 첫 논문 세션에서 여기서 만든다.
    ensure_reading_status(today)
    applied = apply_section_patch(note["reading_patch"], today, path=READING_STATUS_PATH)
    return touched, applied


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
"""


def ensure_reading_status(today):
    """없으면 만든다 — 있으면 손대지 않는다(학습자의 기록이다)."""
    if os.path.exists(READING_STATUS_PATH):
        return False
    os.makedirs(PAPERS_DIR, exist_ok=True)
    with open(READING_STATUS_PATH, "w", encoding="utf-8") as f:
        f.write(READING_STATUS_TEMPLATE.format(today=today))
    return True


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
            print(f"[dry-run] papers/{note['slug']}/sessions/… ({note['section']})\n")
            print(note["body"])
            return
        touched, applied = write_paper_session(note, payload, args.today)
        report = [
            f"✅ 논문 세션 기록 완료 — `{touched[0]}`",
            "",
            f"- 논문: `{note['slug']}` · 섹션: {note['section']}",
        ]
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

    # `[자료]` — 세션 로그가 아니라 증류된 학습자료다. 별도 경로로 저장하고 끝낸다.
    if (payload.get("title") or "").startswith("[자료]"):
        note = build_material(payload, args.today)
        path = os.path.join(MATERIALS_DIR, f"{note['slug']}.md")
        marker = f"source_issue: {payload.get('number')}"
        if os.path.isdir(MATERIALS_DIR):
            for name in sorted(os.listdir(MATERIALS_DIR)):
                if name.endswith(".md"):
                    cand = os.path.join(MATERIALS_DIR, name)
                    with open(cand, encoding="utf-8") as f:
                        if marker in f.read(2000):
                            path = cand
                            break
        if args.dry_run:
            print(f"[dry-run] {path}\n")
            print(note["content"])
            return
        os.makedirs(MATERIALS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(note["content"])
        report = [
            f"✅ 자료 지도 저장 — `{path}` ({len(note['content'].splitlines())}줄)",
            "",
            "- 원문 PDF는 저장하지 않았다(저작권·용량) — 요약·개념 지도·빈칸 문제 은행만 남는다.",
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

    path = target_path(note["date"], note["slug"], payload.get("number"))
    if args.dry_run:
        print(f"[dry-run] {path}\n")
        print(note["content"])
        return

    os.makedirs(DAILY_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(note["content"])
    applied = apply_status_patch(note["status_patch"], args.today)
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
    if applied:
        report.append(f"- STATUS.md 갱신: {', '.join(applied)}")
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
