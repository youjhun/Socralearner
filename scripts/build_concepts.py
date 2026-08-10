#!/usr/bin/env python3
"""개념 지도 빌더 — `mastery.md` + `daily/**` → `concepts.json`.

왜 이 파일이 필요한가:
학습 기록(mastery.md)에는 **개념과 이해 상태**가 있지만 **선수관계(edges)** 가 없다.
그래서 "아직 설명 못 하는데 다른 개념을 막고 있는" **막힌 길목**을 계산할 수 없다.
러너가 세션마다 `## 개념 지도` 절에 `A ← B, C`(A의 선수 개념은 B와 C) 한두 줄만 남기면,
이 스크립트가 그것을 모아 그래프로 만든다.

이 빌더가 daily 노트에서 뽑는 것은 셋이다:

1. **선수관계** — `## 개념 지도`의 `A ← B, C`
2. **분야(domain)** — `## 개념 지도` 안의 `### 소제목`. 그 아래 줄들의 개념이 그 분야다.
   분야는 세션의 속성이 아니라 **개념의 속성**이라서 여기서 정한다.
3. **원문 근거** — 노트 본문의 불릿 한 줄을 **그대로**. 요약하지 않는다.
   "이 개념을 안다고 말할 근거가 내 노트 어느 줄에 있는가"가 이해도의 증거다.

산출물 `concepts.json`은 Topdown 앱이 그대로 읽는 형식이다(개념 그래프·막힌 길목·원문 인용).
**생성물이다** — 고칠 곳은 `mastery.md`와 daily 노트다.

## 재료를 어디서 얻는가 — 두 모드 (2026-08-09)

**② 노트 모드(기본)** — 위에 적은 그대로. `mastery.md` + daily의 `## 개념 지도`에서 재료를
모은다. 템플릿을 그대로 쓰는 사람에게는 아무것도 달라지지 않는다.

**① 레지스트리 모드** — `knowledge/concepts.yaml`이 있으면 **재료를 그 파일에서 얻는다.**
개념의 정체(도메인·선수관계·외부 문서)를 사람이 한 곳에 적고, 원문은 앵커(`sources[].match`)로
매달아 빌드할 때 노트에서 **그대로** 꺼낸다(요약본을 만들지 않는다).

이 모드가 필요한 이유는 ②가 구조적으로 놓치는 것이 있어서다: 선수관계는 세션이
`## 개념 지도`를 남긴 만큼만 쌓이므로, 그 관례가 생기기 전에 쓴 노트로 배운 개념은
**영원히 간선 0**이다(2026-08-09 실측: 개념 44개에 선수관계 0·분야 0). 그러면 이 시스템의
핵심인 **막힌 길목**이 계산되지 않는다. 레지스트리는 그 공백을 사람이 한 번 메우고,
이후 세션이 그 위에 쌓게 한다.

**두 모드는 갈라지지 않는다.** 레지스트리는 별도 빌드 경로가 아니라
`(mastery, edges, domain_of, sources)` 네 재료로 **번역**되어 아래 파이프라인에 합류한다.
그래서 지도 손보기(concepts-overrides)·분야 정규화(subjects)·개념/항목 분리가 한 벌로
유지되고, 사용자가 쓰는 손잡이가 모드와 무관하게 같다.

**레지스트리 모드에서도 노트를 계속 읽는다.** 레지스트리는 큐레이션한 것을 지키고,
거기 **없는** 개념·간선은 daily·materials의 `## 개념 지도`에서 받는다(`merge_note_ingredients`).
레지스트리만 SSOT로 쓰면 세션이나 앱이 새로 만든 개념 지도가 그래프에 영영 안 들어가서,
자료를 올려 증류까지 됐는데 노드가 안 느는 일이 생긴다 — 그러면 사람은 같은 자료를 또 올린다.

판정(state)은 레지스트리가 정하지 않는다 — `mastery:` 필드가 이해도 원장의 행을 가리키고,
`check_concept_ledger.py`가 둘의 드리프트를 잡는다. **원장이 판정의 SSOT다.**

실행: python3 scripts/build_concepts.py   (CI가 세션마다 부른다)
"""
import glob
import json
import os
import re
import sys

MASTERY = "mastery.md"
DAILY_DIR = "daily"
MATERIALS_DIR = "materials"
PAPERS_DIR = "papers"
DRILLS = "drills.md"
OUT = "concepts.json"
SECTION = "개념 지도"
SUBJECTS_PATH = "subjects.yaml"
OVERRIDES_PATH = "concepts-overrides.yaml"

# 개념 레지스트리 — 있으면 재료를 여기서 얻는다 (위 §두 모드).
REGISTRY = os.path.join("knowledge", "concepts.yaml")

# ─────────────────────────── 개념 vs 항목 (2층 구조) ───────────────────────────
#
# 2026-08-03: 토익 트랙에서 지식 그래프가 **단어 단위**로 생성되는 것이 발견됐다
# (`procurement`, `adjacent` … 가 각각 노드가 됐다). 원인은 러너의 잘못이 아니라
# **개념의 단위가 어디에도 정의돼 있지 않았다**는 것이다. 정의가 없으면 모델은 재료를
# 그대로 노드로 만든다 — 어휘를 공부하면 어휘가 노드가 된다.
#
# 그래서 층을 둘로 나눈다:
#
#   개념(concept) = **설명을 요구할 수 있는 것**. 그래프의 노드.
#                   "왜 그런가"에 여러 문장으로 답해야 하고, 처음 보는 사례에 전이되며,
#                   다른 개념을 막거나 다른 개념에 막힌다. (10~30개로 수렴한다)
#   항목(drill)   = **회상 대상**. 그래프에 넣지 않는다.
#                   단어·연도·공식 값처럼 답이 하나로 끝나고 위계에 참여하지 않는 것.
#                   (수백 개여도 된다 — 그래서 그래프에 넣으면 그래프가 죽는다)
#
# 항목을 **버리지는 않는다.** `concepts.json`의 별도 키 `drills`로 보존한다.
# Topdown은 `concepts`만 읽으므로 앱을 고치지 않아도 그래프가 깨끗해진다.
#
# 자동 판정은 보수적이다 — 사용자의 기록을 CI가 마음대로 지우면 안 된다.
# `drills.md`에 적힌 것이 항상 이기고, 자동 판정은 아래 두 조건을 **함께** 만족할 때만 한다.

# ① 어휘장 꼴 — "procurement = 조달", "adjacent - 인접한", "procure (조달하다)"
_VOCAB_GLOSS = re.compile(r"^[A-Za-z][A-Za-z'\-]{2,}\s*[=\-–—:(（]\s*\S")

# ② 소문자만으로 된 외국어 토큰 하나 — "procurement".
#    대문자가 섞이면 약어·고유명사로 보고 건드리지 않는다(SVD·PCA·ResNet·Transformer).
_BARE_LOWER = re.compile(r"^[a-z][a-z'\-]{2,19}$")

# ②는 약한 신호다. "backpropagation" 같은 정당한 개념도 이 모양이라, 하나둘 있는 것으로는
# 판정하지 않는다. 이만큼 쌓여야 "어휘를 통째로 부은 것"으로 본다.
WEAK_DUMP_MIN = 10

# 선수관계를 읽을 곳. daily는 세션마다 한두 줄씩 쌓이고, materials는 강의자료에서
# 증류한 개념 목록이라 한 번에 그래프의 뼈대가 들어온다. 둘 다 봐야 그래프가 채워진다.
#
# 2026-08-10: `papers/`를 더했다. 논문도 자료와 같은 방식으로 원문을 보존하게 되면서
# `papers/<slug>/distilled.md`에 `## 개념 지도`가 생기는데, 여기 없으면 그것이 **갈 곳이
# 없다** — 자료를 올려 증류까지 됐는데 그래프에 아무것도 안 들어가는 조용한 실패가 된다.
# 논문 세션 노트(`papers/<slug>/sessions/`)의 개념 지도도 같은 이유로 daily와 같게 다룬다.
EDGE_DIRS = (DAILY_DIR, MATERIALS_DIR, PAPERS_DIR)

# mastery.md 상태 → Topdown이 아는 어휘. `설명가능`만 '통과'로 친다.
MASTERED = {"설명가능"}

UNCLASSIFIED = "미분류"

# 노트 섹션 제목(부분 일치) → 근거의 종류. Topdown의 `RawSource.kind`가 이 어휘를 쓴다.
# 앞에 오는 것이 먼저 매칭되므로 더 구체적인 제목을 위에 둔다.
SOURCE_SECTIONS = [
    ("오늘 직접 학습한 지식", "지식"),
    ("예측", "내말"),
    ("교정", "교정"),
    ("취약", "취약"),
    ("퀴즈", "퀴즈"),
    ("계산", "계산"),
    ("유도", "계산"),
]

# 한국어는 조사가 단어에 붙는다("신경망은", "역전파를"). 그래서 "뒤에 한글이 오면 다른
# 단어"라는 단순 규칙을 쓰면 정상 매칭까지 죽는다. 붙어도 같은 단어로 보는 꼬리 목록.
JOSA = (
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로", "으로",
    "에서", "에게", "부터", "까지", "보다", "처럼", "라고", "이라고", "이나", "나",
    "이란", "란", "이며", "며", "이고", "고", "인", "임", "이다", "다", "적", "적인",
)

_WORDCHAR = re.compile(r"[0-9A-Za-z가-힣]")


def is_placeholder(text):
    """`<개념>` 같은 템플릿 자리표시자인가 — 아직 안 채운 칸을 개념으로 세우면 안 된다.

    session-card 템플릿을 그대로 복사한 노트가 들어와도 유령 개념이 생기지 않게 한다.
    """
    s = (text or "").strip()
    return not s or ("<" in s and ">" in s)


def slugify(text):
    s = re.sub(r"[^\w가-힣\s-]", "", (text or "").strip()).strip()
    s = re.sub(r"\s+", "-", s)
    return s.lower()[:60] or "concept"


def parse_mastery(path=MASTERY):
    """mastery.md 표 → {label: {state, importance, verified, evidence}} (마지막 줄이 이김)."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2:
                continue
            label = cells[0]
            if not label or label == "개념" or set(label) <= set("-: "):
                continue  # 헤더·구분선
            out[label] = {
                "state": cells[1] if len(cells) > 1 else "",
                "importance": cells[2] if len(cells) > 2 else "",
                "verified": cells[3] if len(cells) > 3 else "",
                "evidence": cells[4] if len(cells) > 4 else "",
            }
    return out


def is_example_note(text):
    """예시 노트인가 — frontmatter `tags:`에 `example`이 있으면 그렇다.

    템플릿이 함께 주는 `daily/2026-01-01-example-session.md`는 **가상의 세션**이다.
    그 문장이 사용자의 근거로 붙으면 하지도 않은 공부가 이해의 증거가 된다 —
    이 시스템이 막으려는 바로 그것("증거 없는 설명가능은 자기기만")이다.
    그래서 개념·선수관계·근거 어디에도 쓰지 않는다. 파일명이 아니라 표식으로 거른다.
    """
    m = re.match(r"^---\n(.*?)\n---", text or "", re.S)
    if not m:
        return False
    tags = re.search(r"^tags:\s*\[(.*?)\]", m.group(1), re.M)
    if not tags:
        return False
    return "example" in [t.strip().strip("\"'") for t in tags.group(1).split(",")]


def _daily_notes(dirs=DAILY_DIR):
    """수집 대상 노트 — 예시 노트는 뺀다.

    `dirs`에 materials/를 함께 넘기면 증류된 강의자료도 읽는다(개념 지도 전용).
    근거 수집에는 daily만 넘긴다 — 증류 자료는 사용자가 스스로 설명한 증거가 아니고,
    그 문장이 근거로 붙으면 `is_example_note`가 막으려는 것과 같은 자기기만이 된다.
    """
    # 2026-08-05: `**/*.md`로 넓혔다. 트랙 서랍(`daily/<track>/`)이 생기면서 한 층만
    # 보던 이 glob이 **트랙에 담긴 노트를 통째로 못 보게** 됐다. 노트는 쌓이는데
    # 그래프만 비어 가는 실패라, 조용하고 알아채기 어렵다.
    paths = []
    for d in ([dirs] if isinstance(dirs, str) else dirs):
        paths.extend(glob.glob(os.path.join(d, "**", "*.md"), recursive=True))
    for path in sorted(paths):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if is_example_note(text):
            continue
        yield path, text


def _section_body(text, title):
    """`## <title>` 절의 본문. 제목은 부분 일치(이모지·괄호 주석이 붙어도 찾도록)."""
    m = re.search(r"^##\s*.*%s.*$" % re.escape(title), text, re.M)
    if not m:
        return ""
    body = text[m.end():]
    nxt = re.search(r"^##\s", body, re.M)
    return body[: nxt.start()] if nxt else body


def parse_concept_map(daily_dir=DAILY_DIR):
    """`## 개념 지도` → (선수관계 목록, {개념: 분야}).

    분야는 절 안의 `### 소제목`이 정한다:

        ## 개념 지도
        ### 선형대수
        - 선형변환 ← 행렬
        ### ML
        - 딥러닝 ← 선형대수, 미분

    화살표 없이 이름만 적은 줄은 **분류만** 한다(선수관계는 안 만든다):

        ### 선형대수
        - 선형대수
        - 선형변환 ← 선형대수

    이 길이 필요한 이유: 분야는 화살표 **왼쪽**에만 붙는다. 선수 개념에까지 물려주면
    `### ML` 아래의 `딥러닝 ← 선형대수`가 선형대수를 ML로 잘못 분류한다. 그래서 뿌리
    개념(남의 선수이기만 하고 자신은 타깃이 안 되는 개념)은 이름만 적어 분류한다.

    같은 개념이 나중 세션에서 다시 분류되면 **마지막 명시가 이긴다**(mastery.md 관례와 동일).
    소제목 없이 적힌 개념은 분야를 남기지 않는다 → 나중에 `미분류`가 된다.
    """
    edges = []
    domain_of = {}
    for _path, text in _daily_notes(EDGE_DIRS):
        body = _section_body(text, SECTION)
        if not body:
            continue
        current_domain = ""
        for line in body.splitlines():
            head = re.match(r"^\s*#{3,}\s*(.+?)\s*$", line)
            if head:
                name = head.group(1).strip().strip("`")
                current_domain = "" if is_placeholder(name) else name
                continue
            line = line.strip().lstrip("-*").strip()
            if not line:
                continue
            # `A ← B, C`  (화살표는 ←, <-, <= 를 허용)
            parts = re.split(r"←|<-|<=", line, maxsplit=1)
            if len(parts) != 2:
                # 화살표 없는 줄 = 분류만. 소제목 아래일 때만 뜻이 있다.
                name = line.strip("`").strip()
                if current_domain and not is_placeholder(name):
                    domain_of[name] = current_domain
                continue
            target = parts[0].strip().strip("`")
            if is_placeholder(target):
                continue
            if current_domain:
                domain_of[target] = current_domain
            for prereq in parts[1].split(","):
                prereq = prereq.strip().strip("`")
                if not is_placeholder(prereq) and target != prereq:
                    edges.append((target, prereq))
    return edges, domain_of


def _bullets(body):
    """절 본문 → 불릿 한 줄씩. 인용문(`>`)은 설명이지 기록이 아니라 버린다."""
    out = []
    for line in body.splitlines():
        if re.match(r"^\s*>", line):
            continue
        if not re.match(r"^\s*(?:[-*+]|\d+[.)])\s", line):
            continue
        out.append(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s*", "", line).strip())
    return [b for b in out if b]


def _mentions(text, label):
    """`text` 안에 `label`이 **낱말로** 나오는가.

    앞은 낱말 문자면 안 되고(“비선형대수”의 “선형대수”는 다른 말), 뒤는 낱말 문자가
    아니거나 조사여야 한다(“신경망은”은 “신경망”이 맞다). 이 두 검사가 없으면
    "미분"이 "미분방정식"에 걸리는 식의 오탐이 쏟아진다.
    """
    if len(label) < 2:
        return False  # 한 글자 라벨은 오탐만 만든다
    start = 0
    while True:
        i = text.find(label, start)
        if i == -1:
            return False
        j = i + len(label)
        before_ok = i == 0 or not _WORDCHAR.match(text[i - 1])
        tail = text[j:]
        after_ok = (not tail) or (not _WORDCHAR.match(tail[0])) or tail.startswith(JOSA)
        if before_ok and after_ok:
            return True
        start = i + 1


def collect_sources(labels, daily_dir=DAILY_DIR):
    """개념 → 그 개념을 언급한 노트 줄들(원문 그대로).

    **긴 라벨 우선**으로 본다: 한 줄이 "선형대수"를 담고 있으면 "선형"은 그 줄을 가져가지
    못한다. 포함 관계로 생기는 오탐을 라벨 길이만으로 막는 값싼 방법이다.
    """
    sources = {lb: [] for lb in labels}
    by_len = sorted(labels, key=len, reverse=True)

    for path, text in _daily_notes(daily_dir):
        for title, kind in SOURCE_SECTIONS:
            body = _section_body(text, title)
            if not body:
                continue
            for line in _bullets(body):
                claimed = []  # 이 줄을 이미 가져간 (더 긴) 라벨들
                for lb in by_len:
                    if any(lb in c for c in claimed):
                        continue  # 더 긴 라벨 안에 들어가는 말 — 그 라벨의 근거로 족하다
                    if _mentions(line, lb):
                        claimed.append(lb)
                        sources[lb].append({"file": path, "kind": kind, "match": line})
    return sources


def parse_drills(path=DRILLS):
    """`drills.md`의 불릿 → 항목 라벨 집합. 여기 적힌 것은 **항상** 항목이다(자동 판정보다 우선).

    러너가 어휘·연호처럼 회상 대상인 것을 여기 모으면, 그래프는 개념만 남는다.
    파일이 없으면 빈 집합 — 전공 트랙은 이 파일 없이도 그대로 동작한다.
    """
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        text = f.read()
    out = set()
    for line in _bullets(text):
        name = line.split("—")[0].split(" - ")[0].strip().strip("`").strip()
        if not name or is_placeholder(name):
            continue
        out.add(name)
        # `procurement = 조달`로 적어 두고 원장에는 `procurement`만 올라오는 경우가 흔하다.
        # 뜻을 떼어낸 표제어도 같이 등록해 둘이 어긋나지 않게 한다.
        head = re.split(r"\s*[=:(（]", name, maxsplit=1)[0].strip()
        if head and head != name:
            out.add(head)
    return out


def classify_labels(labels, prereq_of, id_of, explicit_drills):
    """라벨을 개념과 항목으로 가른다 → (개념 목록, 항목 목록, 판정 사유).

    **위계에 참여하면 무조건 개념이다.** 선수 개념을 갖거나 남의 선수이면, 모양이 어휘
    같아도 노드로 남긴다 — 그래프에서 실제로 일을 하고 있기 때문이다. 이 규칙이 있어서
    "backpropagation ← chain-rule" 같은 정당한 개념이 어휘로 오인되지 않는다.
    """
    has_dependents = set()
    for _cid, plist in prereq_of.items():
        has_dependents.update(plist)

    def in_hierarchy(lb):
        cid = id_of[lb]
        return bool(prereq_of.get(cid)) or cid in has_dependents

    strong, weak = [], []
    for lb in labels:
        if lb in explicit_drills or in_hierarchy(lb):
            continue
        if _VOCAB_GLOSS.match(lb):
            strong.append(lb)
        elif _BARE_LOWER.match(lb) or len(lb.strip()) <= 2:
            weak.append(lb)

    drills, reason = set(), {}
    for lb in labels:
        if lb in explicit_drills:
            drills.add(lb)
            reason[lb] = "drills.md에 적힘"
    for lb in strong:
        drills.add(lb)
        reason[lb] = "어휘장 꼴(단어=뜻)이고 선수관계가 없음"
    if len(weak) >= WEAK_DUMP_MIN:
        for lb in weak:
            drills.add(lb)
            reason[lb] = "선수관계 없는 단일 외국어 토큰이 %d개 — 어휘 목록으로 판정" % len(weak)

    concepts = [lb for lb in labels if lb not in drills]
    return concepts, [lb for lb in labels if lb in drills], reason


# `info`(원장 행)에 있으면 그대로 실어 보내는 선택 키 — Topdown `RawConcept`이 선언하는 것들.
# 노트 모드의 `parse_mastery`는 이 키를 만들지 않으므로 전부 빠진다(출력 그대로).
# 레지스트리 모드에서만 채워지고, 없는 키는 아예 넣지 않는다 — 빈 값이 "비어 있음"을
# 주장하는 것과 키가 없는 것은 다르다.
OPTIONAL_INFO_KEYS = ("verified", "wikipedia", "related", "open_questions")


def build(mastery, edges, domain_of, sources, ids=None):
    """노드(개념) + 선수관계 + 분야 + 원문 근거 → concepts.json 구조.

    `ids`: {라벨: 개념 id}. 레지스트리가 **큐레이션한 id**(`matrix-vector-map`)를 slugify가
    덮지 않게 한다 — Hunwiki `graph.json`이 같은 id를 쓰므로 여기서 새로 지으면 두 그래프가
    같은 개념을 다른 점으로 그린다. 안 주면 지금까지처럼 라벨을 slugify한다.
    """
    ids = ids or {}
    labels = list(mastery.keys())
    for target, prereq in edges:  # 원장에 아직 없는 개념도 노드로 세운다
        for lb in (target, prereq):
            if lb not in labels:
                labels.append(lb)
    for lb in domain_of:  # 분류만 된 개념(화살표 없는 줄)도 개념이다
        if lb not in labels:
            labels.append(lb)

    id_of = {lb: ids.get(lb) or slugify(lb) for lb in labels}
    prereq_of = {}
    for target, prereq in edges:
        prereq_of.setdefault(id_of[target], [])
        pid = id_of[prereq]
        if pid not in prereq_of[id_of[target]]:
            prereq_of[id_of[target]].append(pid)

    # 개념/항목 분리 — 항목은 그래프에서 빠지되 버려지지 않는다.
    concept_labels, drill_labels, drill_reason = classify_labels(
        labels, prereq_of, id_of, parse_drills()
    )
    drill_set = set(drill_labels)

    concepts, drills = [], []
    for lb in labels:
        info = mastery.get(lb, {})
        cid = id_of[lb]
        # 원장의 증거 칸에 적힌 daily 링크도 근거로 친다(인용문 없이 파일만).
        collected = list(sources.get(lb, []))
        seen = {(s["file"], s["match"]) for s in collected}
        # 경로에 `/`를 허용한다 — 트랙 서랍이 생기며 증거가 `daily/<track>/…md`가 됐다.
        for m in re.finditer(r"[\w./-]*daily/[\w./\-가-힣]+\.md", info.get("evidence", "")):
            if (m.group(0), "") not in seen:
                collected.append({"file": m.group(0), "kind": "원장", "match": ""})
        entry = {
            "id": cid,
            "label": lb,
            "domain": domain_of.get(lb) or UNCLASSIFIED,
            "state": info.get("state", "미학습") or "미학습",
            "importance": (info.get("importance") or "M")[:1].upper() if info.get("importance") else "M",
            "prereq": prereq_of.get(cid, []),
            "sources": collected,
            # 원장에는 `note` 칸이 없어 지금까지 **검증일**이 여기 들어왔다. 레지스트리는
            # 진짜 설명을 담으므로 그쪽이 있으면 그것이 이긴다(없으면 지금 동작 그대로).
            "note": info["note"] if "note" in info else info.get("verified", ""),
        }
        for key in OPTIONAL_INFO_KEYS:
            if info.get(key):
                entry[key] = info[key]
        if lb in drill_set:
            entry["why_drill"] = drill_reason.get(lb, "")
            drills.append(entry)
        else:
            concepts.append(entry)

    # `concepts`만 그래프가 된다. Topdown은 이 키만 읽으므로 앱 수정 없이 반영된다.
    return {"concepts": concepts, "drills": drills}


# ─────────────────── 레지스트리 → 네 재료 (knowledge/concepts.yaml) ───────────────────
#
# 여기서 하는 일은 **번역뿐이다.** 레지스트리를 별도 빌드 경로로 만들지 않고
# `(mastery, edges, domain_of, sources)`로 옮겨 위의 파이프라인에 그대로 태운다.
# 그래야 지도 손보기·분야 정규화·개념/항목 분리가 모드와 무관하게 한 벌로 돈다.
#
# 앵커 해석은 Hunwiki `scripts/build_knowledge_graph.py`의 `extract_block`과 **같은 의미**여야
# 한다 — 같은 노트를 읽는 두 빌더가 다른 조각을 꺼내면 두 그래프가 조용히 갈린다.

LIST_MARKER = re.compile(r"^\s*(?:[-*>]|\d+\.)\s")
MATH_INLINE = re.compile(r"\\\((.+?)\\\)", re.S)
MATH_BLOCK = re.compile(r"\\\[(.+?)\\\]", re.S)


def normalize_math(text):
    """`\\( … \\)` → `$ … $`, `\\[ … \\]` → `$$ … $$`.

    **내용은 한 글자도 바꾸지 않는다 — 구분자만 옮긴다.** 원본 노트가 쓰는 `\\( \\)`는
    Obsidian·GitHub·앱 어디서도 렌더되지 않아 날LaTeX으로 보인다. `$`는 셋 다 렌더한다.
    """
    if not text:
        return text
    text = MATH_BLOCK.sub(lambda m: "$$" + m.group(1).strip() + "$$", text)
    return MATH_INLINE.sub(lambda m: "$" + m.group(1).strip() + "$", text)


def extract_block(text, needle):
    """needle이 있는 곳의 **원문 블록**을 그대로 돌려준다 (요약·재작성 없음).

    목록 항목이면 그 항목(+들여쓴 이어짐)만, 아니면 문단 전체. 못 찾으면 None.
    """
    idx = text.find(needle)
    if idx < 0:
        return None
    lines = text.splitlines()
    pos, ln = 0, 0
    for i, line in enumerate(lines):
        if pos + len(line) >= idx:
            ln = i
            break
        pos += len(line) + 1

    if LIST_MARKER.match(lines[ln]):
        block = [lines[ln]]
        for k in range(ln + 1, len(lines)):
            nxt = lines[k]
            if not nxt.strip() or nxt.startswith("#"):
                break
            if LIST_MARKER.match(nxt) and not nxt.startswith(("  ", "\t")):
                break
            block.append(nxt)
    else:
        start = end = ln
        while start > 0 and lines[start - 1].strip() and not lines[start - 1].startswith("#"):
            start -= 1
        while end + 1 < len(lines) and lines[end + 1].strip():
            end += 1
        block = lines[start:end + 1]
    return "\n".join(block).strip()


def load_registry(path=REGISTRY):
    """`knowledge/concepts.yaml` → 개념 목록. 없으면 빈 목록(= 노트 모드)."""
    if not os.path.exists(path):
        return []
    try:
        import yaml  # type: ignore
    except ImportError:
        # 조용히 노트 모드로 내려가지 않는다 — 그러면 그래프가 **이유 없이** 빈약해지고,
        # 사용자는 자기 레지스트리가 무시된 줄 모른 채 간선 0을 본다.
        sys.exit(f"{path}가 있는데 PyYAML이 없다 — pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("concepts") or []


def _read_cached(rel, cache):
    if rel not in cache:
        try:
            with open(rel, encoding="utf-8") as f:
                cache[rel] = f.read()
        except OSError:
            cache[rel] = None
    return cache[rel]


def _resolve_anchors(cid, anchors, cache, problems):
    """앵커(`file` + 원문에 그대로 있는 짧은 문자열) → 원문 조각. 요약하지 않는다."""
    out = []
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        rel = str(anchor.get("file") or "")
        needle = str(anchor.get("match") or "")
        text = _read_cached(rel, cache)
        if text is None:
            problems.append(f"{cid}: 소스 파일 없음 {rel}")
            continue
        block = extract_block(text, needle)
        if block is None:
            problems.append(f"{cid}: 앵커 실패 {rel} :: {needle[:40]!r}")
            continue
        out.append({
            "file": rel,
            "kind": anchor.get("kind", "지식"),
            "match": normalize_math(block),
        })
    return out


def registry_ingredients(concepts):
    """레지스트리 → (mastery, edges, domain_of, sources, ids, 문제 목록).

    `mastery`의 값에는 원장 네 칸(state·importance·verified·evidence) 외에 `note`·`related`·
    `wikipedia`·`open_questions`도 담는다 — `build()`가 선택 키로 그대로 실어 보낸다.
    """
    label_of, ids, problems = {}, {}, []
    for c in concepts:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip()
        if not cid:
            problems.append(f"id 없는 항목 — 건너뜀 ({str(c.get('label'))[:30]!r})")
            continue
        label = normalize_math(str(c.get("label") or "").strip()) or cid
        label_of[cid] = label
        ids[label] = cid

    mastery, edges, domain_of, sources = {}, [], {}, {}
    cache = {}
    for c in concepts:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        lb = label_of[cid]

        # 판정(state)은 레지스트리가 정하지 않는다 — 원장에서 옮겨 적은 사본이고,
        # 어긋나면 check_concept_ledger.py가 잡는다. 여기서는 옮기기만 한다.
        info = {
            "state": c.get("state") or "",
            "importance": c.get("importance") or "",
            "verified": str(c.get("verified") or ""),
            "evidence": "",
            # 키를 항상 둔다 — 없으면 `build()`가 검증일을 note로 쓰는 옛 동작으로 떨어진다.
            "note": normalize_math(str(c.get("note") or "")),
        }
        for key in ("wikipedia", "related", "open_questions"):
            if c.get(key):
                info[key] = c[key]
        mastery[lb] = info

        if c.get("domain"):
            domain_of[lb] = str(c["domain"]).strip()

        for pid in c.get("prereq") or []:
            # 끊긴 화살표는 그래프에서 조용히 사라진다 — 지우지 말고 말한다.
            if pid in label_of:
                edges.append((lb, label_of[pid]))
            else:
                problems.append(f"{cid}: 없는 선수 개념 {pid}")

        sources[lb] = _resolve_anchors(cid, c.get("sources") or [], cache, problems)

    return mastery, edges, domain_of, sources, ids, problems


def merge_note_ingredients(mastery, edges, domain_of, sources, ids):
    """레지스트리 재료에 노트 재료를 합친다. **레지스트리가 이긴다 — 노트는 빈 곳만 채운다.**

    왜 합치는가 (2026-08-09): 레지스트리만 SSOT로 쓰면 세션이나 앱이 새로 만든
    `## 개념 지도`가 그래프에 **영영 안 들어간다**. 자료를 올려 증류까지 됐는데 노드가
    하나도 안 늘면, 사람은 "증류가 안 됐나" 하고 같은 자료를 다시 올린다.
    그래서 레지스트리는 큐레이션한 것을 지키고, 거기 **없는** 개념·간선은 노트에서 받는다.

    합치는 규칙:
      · 간선 — 레지스트리에 없는 쌍만 더한다.
      · 개념 — 레지스트리에 없는 라벨만 노드로 세우고, 판정은 이해도 원장에서 가져온다.
      · 분야 — 레지스트리 분야가 이긴다. 노트 분야는 레지스트리 밖 개념에만 붙는다.
      · 근거 — 레지스트리 개념의 근거는 **큐레이션된 앵커뿐이다**(노트에서 더 긁지 않는다).
                밖의 개념만 노트에서 근거를 모은다.

    이름이 달라 같은 개념이 둘로 보이면 `concepts-overrides.yaml`의 `renamed`로 합친다
    (이 함수 뒤에 도는 지도 손보기가 그 일을 한다).

    돌려주는 것: (새 개념 수, 새 간선 수).
    """
    reg_labels = set(mastery)
    note_edges, note_domains = parse_concept_map()

    seen = set(edges)
    n_edges = 0
    for pair in note_edges:
        if pair not in seen:
            edges.append(pair)
            seen.add(pair)
            n_edges += 1

    new_labels = {lb for pair in note_edges for lb in pair} | set(note_domains)
    new_labels -= reg_labels
    if new_labels:
        ledger = parse_mastery()
        for lb in sorted(new_labels):
            # 판정은 원장이 SSOT다 — 레지스트리 밖이라고 다르지 않다. 없으면 미학습.
            mastery[lb] = dict(ledger.get(lb, {}))
        sources.update(collect_sources(sorted(new_labels)))

    for lb, domain in note_domains.items():
        if lb not in reg_labels:
            domain_of[lb] = domain

    return len(new_labels), n_edges


def _rename_keys(table, renamed, merge=False):
    """라벨을 키로 쓰는 표(ids·sources)를 이름 합치기에 맞춰 옮긴다.

    이름이 바뀌지 않는 항목을 먼저 넣는다 — 둘이 하나로 합쳐질 때 **살아남는 이름 쪽**의
    id가 남아야 큐레이션된 id가 유지된다.
    """
    out = {}
    for lb in sorted(table, key=lambda x: renamed.get(_fold(x), x) != x):
        nlb = renamed.get(_fold(lb), lb)
        if merge and nlb in out:
            out[nlb] = out[nlb] + table[lb]
        else:
            out.setdefault(nlb, table[lb])
    return out


# ───────────────── 지도 손보기 (concepts-overrides.yaml) ─────────────────
#
# 2026-08-07 (유지훈): *"이런 노드 중에서 사용자가 필요없다고 생각되면 바로 삭제하거나
# 이름 수정할 수 있도록 해야할 듯."*
#
# 노드는 어디에도 저장돼 있지 않다 — 매 빌드마다 daily 노트의 `## 개념 지도`에서 다시
# 만들어진다. 그래서 진짜 "삭제"는 과거 세션 노트를 고치는 일이 되는데, 그건 하지 않는다:
# 이 저장소의 주장이 "기록이 곧 증거"라서, 지도가 지저분하다고 그날 한 말을 지우면
# 증거가 거짓이 된다. 대신 **지도 위에 얇게 덮는다.**
#
# 되돌릴 수 있다는 것이 이 설계의 값이다 — overrides 한 줄을 지우면 노드가 그대로 돌아온다.


def load_overrides(path=None):
    """concepts-overrides.yaml → (감출 이름 집합, {옛 이름(정규화): 새 이름})."""
    path = path or OVERRIDES_PATH
    if not os.path.exists(path):
        return set(), {}
    try:
        import yaml  # type: ignore
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        # 파일이 깨졌다고 그래프를 통째로 잃지 않는다 — 손보기는 곁다리다.
        return set(), {}

    hidden = {str(h).strip() for h in (data.get("hidden") or []) if str(h).strip()}
    renamed = {}
    for entry in (data.get("renamed") or []):
        if not isinstance(entry, dict):
            continue
        src = str(entry.get("from") or "").strip()
        dst = str(entry.get("to") or "").strip()
        # 자기 자신으로의 이름 바꾸기는 무한 루프의 씨앗이라 애초에 받지 않는다.
        if src and dst and _fold(src) != _fold(dst):
            renamed[_fold(src)] = dst
    return hidden, renamed


def apply_overrides(edges, domain_of, mastery, hidden, renamed):
    """이름 합치기 → 감추기. **이 순서여야 한다** — 옛 이름으로 감춘 것도 잡아야 한다.

    감출 때는 그 노드에 걸린 선수관계도 함께 뺀다. 안 그러면 그래프에 이름 없는 점이
    남는다(엣지가 가리키는 노드가 없으면 화면은 id를 그대로 그린다).
    """
    def rename(label):
        return renamed.get(_fold(label), label)

    hidden_folded = {_fold(h) for h in hidden} | {_fold(rename(h)) for h in hidden}

    def is_hidden(label):
        return _fold(label) in hidden_folded

    new_edges = []
    for target, prereq in edges:
        t, p = rename(target), rename(prereq)
        if is_hidden(t) or is_hidden(p) or t == p:
            continue
        if (t, p) not in new_edges:
            new_edges.append((t, p))

    new_domain = {}
    for label, domain in domain_of.items():
        lb = rename(label)
        if not is_hidden(lb):
            new_domain[lb] = domain

    # 원장은 마지막 명시가 이긴다 — 합쳐질 때 새 이름 쪽 기록을 남긴다.
    new_mastery = {}
    for label, info in mastery.items():
        lb = rename(label)
        if is_hidden(lb):
            continue
        new_mastery[lb] = {**new_mastery.get(lb, {}), **info}

    n_hidden = len(mastery) + len(domain_of) - len(new_mastery) - len(new_domain)
    return new_edges, new_domain, new_mastery, max(n_hidden, 0)


# ────────────────────────── 분야 정규화 (subjects.yaml) ──────────────────────────
#
# 2026-08-04: 같은 과목이 여러 분야로 쪼개지는 것이 발견됐다 — 한 학습자의 그래프에서
# "회로 등가화"(8)와 "전자회로 기초"(4)가 서로 다른 색으로 갈렸고, 21개는 아예 미분류였다.
# 원인은 2026-08-03의 "개념의 단위" 사건과 같은 종류다: **분야의 단위가 어디에도 정의돼
# 있지 않았다.** 정의가 없으면 모델은 그 세션에서 다룬 소주제를 소제목으로 단다.
#
# 여기서 하는 것은 둘뿐이다:
#   ① 별칭 합치기 — `subjects.yaml`에 적힌 이름으로 통일한다(비어 있으면 아무것도 안 한다).
#   ② 미분류 전파 — 선수관계로 이어진 이웃이 한 분야로만 분류돼 있으면 그 분야로 본다.
#      이웃이 여러 분야면 **찍지 않는다** — 조용히 틀리는 것보다 미분류가 낫다.
#
# 분야는 라벨이지 학습 순서가 아니다(subjects.yaml 헤더 참조). 여기서 정규화하는 것은
# 보는 축일 뿐이고, 무엇을 배울지는 이 파일이 정하지 않는다.


def load_subjects():
    """subjects.yaml → {별칭(정규화): 대표 이름}. 없거나 비면 빈 표(정규화 안 함)."""
    if not os.path.exists(SUBJECTS_PATH):
        return {}
    try:
        import yaml  # type: ignore
        with open(SUBJECTS_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}
    alias_of = {}
    for entry in (data.get("subjects") or []):
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        for alias in [name] + list(entry.get("aliases") or []):
            alias = str(alias).strip()
            if alias:
                alias_of[_fold(alias)] = name
    return alias_of


def _fold(text):
    """비교용 정규화 — 공백·기호를 지운다('회로 등가화' == '회로등가화')."""
    return re.sub(r"[^\w가-힣]", "", str(text)).lower()


def normalize_domains(domain_of, alias_of):
    """노트에 적힌 분야 이름을 subjects.yaml의 대표 이름으로 합친다."""
    if not alias_of:
        return domain_of, 0
    out, merged = {}, 0
    for label, domain in domain_of.items():
        canon = alias_of.get(_fold(domain))
        if canon and canon != domain:
            merged += 1
        out[label] = canon or domain
    return out, merged


def propagate_domains(domain_of, edges, labels):
    """미분류 개념을 선수관계 이웃의 분야로 채운다 — 이웃이 한 분야일 때만."""
    neighbors = {}
    for target, prereq in edges:
        neighbors.setdefault(target, set()).add(prereq)
        neighbors.setdefault(prereq, set()).add(target)

    filled = {}
    for label in labels:
        if domain_of.get(label):
            continue
        found = {domain_of[n] for n in neighbors.get(label, ()) if domain_of.get(n)}
        # 이웃이 두 분야 이상이면 찍지 않는다 — 가로지르는 개념일 수 있고,
        # 그런 개념을 한쪽으로 밀어 넣으면 "어디에 걸쳐 있나"라는 정보가 사라진다.
        if len(found) == 1:
            filled[label] = next(iter(found))
    domain_of = {**domain_of, **filled}
    return domain_of, len(filled)


def _labels_of(mastery, edges, domain_of=()):
    labels = set(mastery)
    for t, p in edges:
        labels.add(t)
        labels.add(p)
    return labels | set(domain_of)


def main():
    # 재료를 어디서 얻을지만 여기서 갈린다 — 아래 파이프라인은 두 모드가 함께 쓴다.
    # **빈 레지스트리는 모드를 켜지 않는다.** 템플릿이 함께 주는 견본(`concepts: []`)이
    # 노트 모드를 꺼 버리면, 아무것도 안 한 사용자의 그래프가 이유 없이 비어 버린다.
    registry = load_registry()
    n_note_concepts = n_note_edges = 0
    if registry:
        mastery, edges, domain_of, sources, ids, anchor_problems = registry_ingredients(registry)
        # 레지스트리가 이기되, 거기 없는 개념·간선은 노트에서 받는다 — 안 그러면 세션이나
        # 앱이 새로 만든 `## 개념 지도`가 그래프에 영영 안 들어간다.
        n_note_concepts, n_note_edges = merge_note_ingredients(
            mastery, edges, domain_of, sources, ids
        )
    else:
        ids, anchor_problems = {}, []
        mastery = parse_mastery()
        edges, domain_of = parse_concept_map()
        sources = collect_sources(sorted(_labels_of(mastery, edges)))

    # 지도 손보기 — 사용자가 감추거나 이름을 합친 것. 분야 정규화보다 **먼저** 한다:
    # 감춘 개념까지 분야를 채우고 이웃에 전파하면, 지운 것이 지도에 자국을 남긴다.
    hidden, renamed = load_overrides()
    if hidden or renamed:
        edges, domain_of, mastery, n_dropped = apply_overrides(
            edges, domain_of, mastery, hidden, renamed
        )
        if registry:
            # 레지스트리 모드는 근거를 노트에서 다시 긁지 않는다(앵커가 정한다).
            # 그래서 이름이 바뀐 만큼 표를 옮겨 준다.
            ids = _rename_keys(ids, renamed)
            sources = _rename_keys(sources, renamed, merge=True)
        else:
            sources = collect_sources(sorted(_labels_of(mastery, edges, domain_of)))
    else:
        n_dropped = 0
    labels = _labels_of(mastery, edges, domain_of)

    # 분야 정규화 — 별칭 합치기 → 미분류 전파. 둘 다 안전 기본값(못 정하면 안 바꾼다).
    domain_of, n_merged = normalize_domains(domain_of, load_subjects())
    domain_of, n_filled = propagate_domains(domain_of, edges, labels | set(domain_of))

    data = build(mastery, edges, domain_of, sources, ids)

    n = len(data["concepts"])
    n_drills = len(data["drills"])
    n_edges = sum(len(c["prereq"]) for c in data["concepts"])
    n_mastered = sum(1 for c in data["concepts"] if c["state"] in MASTERED)
    n_sources = sum(len(c["sources"]) for c in data["concepts"])
    n_domains = len({c["domain"] for c in data["concepts"]} - {UNCLASSIFIED})

    if n == 0 and n_drills == 0:
        print("개념 없음 — concepts.json 생성 건너뜀 (mastery.md가 비어 있고 개념 지도도 없음)")
        return 0

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=False)
    print(
        f"✅ {OUT}{' (레지스트리 모드)' if registry else ''} — 개념 {n} · 선수관계 {n_edges} · "
        f"설명가능 {n_mastered} · 원문 근거 {n_sources}조각 · 분야 {n_domains}개"
    )
    if n_note_concepts or n_note_edges:
        print(f"   ➕ 레지스트리 밖에서 개념 {n_note_concepts}개 · 선수관계 {n_note_edges}개를 "
              "노트에서 받았다(daily · materials의 `## 개념 지도`).")
        print("      큐레이션에 넣고 싶으면 knowledge/concepts.yaml로 옮겨 적는다. "
              "이름이 겹쳐 보이면 concepts-overrides.yaml의 renamed로 합친다.")
    if anchor_problems:
        # 실패시키지 않는다 — 기록이 먼저다. 다만 조용히 넘어가지도 않는다.
        print(f"   ⚠️ 레지스트리 문제 {len(anchor_problems)}건 (개념은 남고 그 근거만 빈다):")
        for p in anchor_problems[:20]:
            print(f"      - {p}")
        if len(anchor_problems) > 20:
            print(f"      - … 외 {len(anchor_problems) - 20}건")
    if n_drills:
        print(f"   📇 항목(회상 대상) {n_drills}개는 그래프에서 뺐다 — 그래프는 설명 대상만 담는다.")
        for d in data["drills"][:6]:
            print(f"      · {d['label']}  ({d['why_drill']})")
        if n_drills > 6:
            print(f"      · … 외 {n_drills - 6}개")
        print("      개념인데 항목으로 잘못 빠졌다면 `## 개념 지도`에 `그 개념 ← 선수 개념` 한 줄을")
        print("      남기면 다음 빌드에서 개념으로 돌아온다(위계에 참여하면 항상 개념이다).")
    if n_edges == 0:
        print("   ℹ️  선수관계가 아직 없다. 세션에서 러너가 `## 개념 지도`에 `A ← B` 를 남기면 쌓인다.")
    if n_dropped or renamed:
        print(
            f"   ✂️  지도 손보기 — 감춘 개념 {n_dropped}개 · 이름 합치기 {len(renamed)}건 "
            "(concepts-overrides.yaml). 노트와 원장은 그대로다."
        )
    if n_merged:
        print(f"   🔗 분야 별칭 {n_merged}건을 subjects.yaml의 대표 이름으로 합쳤다.")
    if n_filled:
        print(f"   🧭 미분류 {n_filled}개를 선수관계 이웃의 분야로 채웠다(이웃이 한 분야일 때만).")
    n_unclassified = sum(1 for c in data["concepts"] if c["domain"] == UNCLASSIFIED)
    if n_unclassified:
        print(
            f"   ℹ️  아직 미분류 {n_unclassified}개 — 이웃이 여러 분야이거나 연결이 없다. "
            "찍지 않고 남겨 둔다."
        )
    if n_domains == 0:
        print("   ℹ️  분야가 아직 없다. `## 개념 지도` 안에 `### 선형대수` 같은 소제목을 두면 분류된다.")
    if n_sources == 0:
        print("   ℹ️  원문 근거가 아직 없다. 노트 본문에서 개념 이름이 그대로 언급되면 자동으로 걸린다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
