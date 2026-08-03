#!/usr/bin/env python3
"""논문 스케줄러 — `topics.yaml`의 주제로 새 논문을 찾아 `papers/`에 모은다.

왜 이 경로인가:
"반도체 OO lab" 같은 연구 주제를 걸어 두면, 매주 그 분야의 새 논문이 자동으로
학습 큐에 들어와야 한다. 그런데 서버를 두면 그 순간 운영·비용·계정이 생긴다.
그래서 **각자 repo의 GitHub Actions**가 주 1회 돌며 공개 API(OpenAlex — 키 불필요)를
조회하고, 결과를 `papers/`에 커밋한다. 서버 0, 비용 0, LLM 토큰 0.

읽는 사람: 러너(Custom GPT)가 세션 시작 시 `papers/inbox.md`를 읽어 이번 주 새 논문을
학습에 엮는다. 사람도 Issue 알림으로 본다.

실행: python3 scripts/scan_papers.py            (CI가 이렇게 부른다)
      python3 scripts/scan_papers.py --dry-run  (네트워크 없이 로직만 확인)
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOPICS_PATH = "topics.yaml"
PAPERS_DIR = "papers"
SEEN_PATH = os.path.join(PAPERS_DIR, "seen.json")
INBOX_PATH = os.path.join(PAPERS_DIR, "inbox.md")
OPENALEX = "https://api.openalex.org/works"
UA = "Socralearner/1.0 (learning repo; https://github.com/topics/socralearner)"

# OpenAlex는 `mailto`를 준 요청을 **polite pool**로 보낸다. 안 주면 공용 풀인데,
# GitHub Actions 러너는 IP를 대량으로 공유해서 공용 풀이 429/403으로 자주 막힌다
# (2026-08-03: "topics를 넣었는데 안 돈다"의 원인 중 하나). topics.yaml에
# `mailto: 내주소@example.com` 한 줄을 두면 그 줄로 옮겨 간다. 없으면 그대로 동작한다.
MAILTO = ""


# ---------------------------------------------------------------- 유틸 (순수)

def today_iso():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date().isoformat()


def load_yaml(path):
    """의존성 없이 쓰기 위한 아주 작은 YAML 로더 대체 — pyyaml이 있으면 그걸 쓴다."""
    try:
        import yaml  # type: ignore
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass
    # pyyaml이 없을 때의 최소 파서 (topics.yaml 형태만 지원)
    data = {"topics": []}
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = re.match(r"^(\w+):\s*(.*)$", line)
            if m and not line.startswith(" "):
                key, val = m.group(1), m.group(2).strip()
                if val:
                    data[key] = int(val) if val.isdigit() else val.strip('"\'')
                continue
            m = re.match(r"^\s*-\s*(\w+):\s*(.*)$", line)
            if m:
                cur = {m.group(1): m.group(2).strip().strip('"\'')}
                data["topics"].append(cur)
                continue
            m = re.match(r"^\s+(\w+):\s*(.*)$", line)
            if m and cur is not None:
                cur[m.group(1)] = m.group(2).strip().strip('"\'')
    return data


def normalize_work(w):
    """OpenAlex work → 우리가 쓰는 얇은 형태. 초록은 역색인이라 복원한다."""
    inv = w.get("abstract_inverted_index") or {}
    abstract = ""
    if inv:
        positions = []
        for word, idxs in inv.items():
            for i in idxs:
                positions.append((i, word))
        abstract = " ".join(w for _, w in sorted(positions))[:400]
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in (w.get("authorships") or [])[:3]
    ]
    loc = (w.get("primary_location") or {})
    return {
        "id": w.get("id", ""),
        "title": (w.get("title") or "").strip(),
        "date": w.get("publication_date", ""),
        "citations": w.get("cited_by_count", 0),
        "authors": [a for a in authors if a],
        "venue": (loc.get("source") or {}).get("display_name", "") or "",
        "url": (w.get("doi") or loc.get("landing_page_url") or w.get("id") or ""),
        "abstract": abstract,
    }


def build_inbox(date, found, window_days, failed=()):
    """주제별 새 논문 → inbox 마크다운 (순수 — 테스트 가능).

    `failed`는 조회 자체가 실패한 주제들이다. **"새 논문이 없다"와 "가져오지 못했다"는
    다른 상태**인데, 예전에는 둘 다 "0편"으로 적혀 구별할 수 없었다.
    """
    total = sum(len(v) for v in found.values())
    lines = [
        "---",
        f"title: \"논문 인박스 — {date}\"",
        f"updated: {date}",
        "kind: papers",
        "---",
        "",
        f"# 📬 논문 인박스 — {date}",
        "",
        f"> 새 논문 **{total}편** — 🆕 신간(최근 {window_days}일, 최신순) + ✅ 검증(최근 2년, 인용순). 🚧 = 내 막힌 길목과 닿는 논문.",
        "> 세션에서 *\"이번 주 새 논문 같이 보자\"* 라고 하면 러너가 여기서 골라 준다.",
        "> 다 읽을 필요 없다 — **제목과 초록만 훑고 1편만 골라** 깊게 보는 편이 낫다.",
        "",
    ]
    if failed:
        lines += [
            f"> ⚠️ **조회 실패 {len(failed)}개 주제** — {', '.join(failed)}",
            "> 새 논문이 없는 것이 아니라 **가져오지 못한** 것이다. Actions 로그를 보고",
            "> `paper-scan → Run workflow`로 다시 돌리면 된다.",
            "",
        ]

    if total == 0:
        lines += [
            "가져온 새 논문이 없다."
            if failed
            else "이번 주는 새로 걸린 논문이 없다. (주제를 넓히려면 `topics.yaml`의 query를 손보면 된다.)",
            "",
        ]
        return "\n".join(lines)

    for label, papers in found.items():
        if not papers:
            continue
        lines.append(f"## {label}")
        lines.append("")
        for p in papers:
            who = ", ".join(p["authors"]) + (" 외" if len(p["authors"]) >= 3 else "")
            badge = "🆕" if p.get("track") == "신간" else "✅" if p.get("track") == "검증" else ""
            hit = (" · 🚧 " + " · ".join(p["blocked_hits"])) if p.get("blocked_hits") else ""
            meta = " · ".join(x for x in [p["date"], who, p["venue"]] if x) + hit
            lines.append(f"### {badge} [{p['title']}]({p['url']})")
            lines.append(f"<sub>{meta}</sub>")
            lines.append("")
            if p["abstract"]:
                lines.append(f"> {p['abstract']}")
            else:
                lines.append("> _(초록이 공개돼 있지 않다 — 제목·저널로 판단하거나 원문을 열어 보자.)_")
            lines.append("")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 선별 (순수)

CONCEPTS_PATH = "concepts.json"
PROVEN_DAYS = 730  # 검증 트랙: 최근 2년 — 인용이 신호가 되는 최소 기간


def load_blocked_terms(path=CONCEPTS_PATH):
    """내 지식 그래프에서 **막힌 길목** 개념의 검색어를 뽑는다 → [(라벨, [영문 토큰])].

    막힌 길목 = `설명가능`이 아닌데 다른 개념의 선수인 것. 이 개념이 초록에
    등장하는 논문을 위로 올린다 — "지금 막힌 곳을 뚫어 주는 논문"이 먼저 온다.
    한국어 라벨은 영어 초록과 안 맞으므로 영문·숫자 토큰(3자+)만 매칭에 쓴다.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    concepts = data.get("concepts") or []
    mastered = {c["id"] for c in concepts if c.get("state") == "설명가능"}
    is_prereq = {p for c in concepts for p in (c.get("prereq") or [])}
    out = []
    for c in concepts:
        if c["id"] in is_prereq and c["id"] not in mastered:
            terms = [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", c.get("label", ""))]
            if terms:
                out.append((c.get("label", c["id"]), terms))
    return out


def _blocked_hits(paper, blocked):
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    return [label for label, terms in blocked if any(t in text for t in terms)]


def select_papers(recent, proven, seen_ids, per_topic, blocked):
    """2트랙 선별 (순수 — 테스트 가능).

    왜 2트랙인가: 출간 2주 된 논문은 인용이 거의 0이라 신간에 인용정렬을 걸면
    사실상 무작위다("최신+좋은 것"이 아니라 "최신+운"). 그래서
    · 🆕 신간(최신순, ~60%) — 따끈한 것. 인용으로 거를 수 없음을 인정한다.
    · ✅ 검증(최근 2년 인용순, 나머지) — 시간이 걸러 준 것.
    공통 필터: 이미 본 것 제외 · 같은 1저자/저널 2편 초과 제외(5편이 한 그룹
    후속작이면 선택지가 1개다).

    **초록은 있으면 앞으로 올리되, 없다고 버리지 않는다** (2026-08-03 수정).
    예전에는 초록이 없으면 제외했는데, OpenAlex는 출판사 라이선스 때문에 상당수
    논문의 초록을 주지 않는다 — 특히 신간이 그렇다. 그래서 API가 25편을 정상으로
    돌려줘도 선별 결과가 **0편**이 되어, 사용자에게는 "topics를 넣었는데 아무것도
    안 걸린다"로 보였다. 초록이 없어도 제목·저널·저자로 고를 수 있다.

    막힌 길목과 닿는 논문은 각 트랙 안에서 앞으로 온다(안정 정렬 — 원래 순서 보존).
    """
    n_recent = max(1, round(per_topic * 0.6))
    n_proven = max(0, per_topic - n_recent)

    def usable(p):
        return bool(p.get("id")) and p["id"] not in seen_ids

    picked, picked_ids, authors, venues = [], set(), {}, {}

    def take(pool, n, track):
        count = 0
        # 막힌 길목과 닿는 것 먼저, 그다음 초록이 있는 것 먼저. 안정 정렬이라
        # 같은 등급 안에서는 API가 준 순서(신간=최신순 / 검증=인용순)가 보존된다.
        ranked = sorted(
            [p for p in pool if usable(p)],
            key=lambda p: (-len(_blocked_hits(p, blocked)), 0 if p.get("abstract") else 1),
        )
        for p in ranked:
            if count >= n or p["id"] in picked_ids:
                continue
            first_author = p["authors"][0] if p.get("authors") else ""
            venue = p.get("venue", "")
            if first_author and authors.get(first_author, 0) >= 2:
                continue
            # arXiv 등 프리프린트 서버는 저널 다양성 카운트에서 제외한다 —
            # 신간 CS/EE 논문은 대부분 arXiv라, 세면 신간 트랙이 부당하게 잘린다.
            is_preprint = "arxiv" in venue.lower() if venue else False
            if venue and not is_preprint and venues.get(venue, 0) >= 2:
                continue
            q = dict(p)
            q["track"] = track
            q["blocked_hits"] = _blocked_hits(p, blocked)[:2]
            picked.append(q)
            picked_ids.add(p["id"])
            if first_author:
                authors[first_author] = authors.get(first_author, 0) + 1
            if venue and not is_preprint:
                venues[venue] = venues.get(venue, 0) + 1
            count += 1

    take(recent, n_recent, "신간")
    take(proven, n_proven, "검증")
    return picked


# ---------------------------------------------------------------- 네트워크

def _fetch(params, attempts=3):
    """OpenAlex 조회. 일시적인 한도·장애는 물러났다 다시 시도한다.

    한 번의 429로 그 주의 수집이 통째로 비는 것을 막는다 — 주 1회 도는 작업이라
    다음 기회가 일주일 뒤다.
    """
    if MAILTO:
        params = dict(params, mailto=MAILTO)
    url = f"{OPENALEX}?{urllib.parse.urlencode(params)}"
    ua = UA if not MAILTO else f"{UA} mailto:{MAILTO}"
    last = None
    for i in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.load(r)
            return [normalize_work(w) for w in data.get("results", [])]
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (403, 429, 500, 502, 503, 504) or i == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            if i == attempts - 1:
                raise
        time.sleep(2 ** i)
    raise last  # 도달하지 않는다 — 위에서 항상 raise 하거나 return 한다


def fetch_recent(query, window_days):
    """신간 트랙 — 최근 N일, **최신순**. 신간은 인용으로 못 거른다."""
    since = (datetime.date.today() - datetime.timedelta(days=window_days)).isoformat()
    return _fetch({
        "search": query,
        "filter": f"from_publication_date:{since}",
        "sort": "publication_date:desc",
        "per-page": "25",
    })


def fetch_proven(query):
    """검증 트랙 — 최근 2년, **인용순**. 여기선 인용이 진짜 신호다."""
    since = (datetime.date.today() - datetime.timedelta(days=PROVEN_DAYS)).isoformat()
    return _fetch({
        "search": query,
        "filter": f"from_publication_date:{since}",
        "sort": "cited_by_count:desc",
        "per-page": "25",
    })


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="topics.yaml → papers/inbox.md 논문 수집기")
    ap.add_argument("--dry-run", action="store_true", help="네트워크 없이 로직만 확인")
    ap.add_argument("--today", default=None)
    args = ap.parse_args()

    if not os.path.exists(TOPICS_PATH):
        print("topics.yaml 없음 — 건너뜀")
        return 0

    cfg = load_yaml(TOPICS_PATH)
    topics = [t for t in (cfg.get("topics") or []) if t.get("query")]
    if not topics:
        print("topics 비어 있음 — 건너뜀 (topics.yaml에 주제를 추가하세요)")
        return 0

    global MAILTO
    MAILTO = str(cfg.get("mailto") or "").strip()

    window = int(cfg.get("window_days", 14) or 14)
    per_topic = int(cfg.get("max_per_topic", 5) or 5)
    date = args.today or today_iso()

    os.makedirs(PAPERS_DIR, exist_ok=True)
    seen = {}
    if os.path.exists(SEEN_PATH):
        try:
            with open(SEEN_PATH, encoding="utf-8") as f:
                seen = json.load(f)
        except (json.JSONDecodeError, OSError):
            seen = {}

    blocked = load_blocked_terms()
    if blocked:
        print(f"막힌 길목 {len(blocked)}개를 가중치로 사용: " + ", ".join(l for l, _ in blocked[:3]) + ("…" if len(blocked) > 3 else ""))

    found, new_ids, failed = {}, [], []
    for t in topics:
        label = t.get("label") or t.get("id") or t["query"]
        try:
            recent = [] if args.dry_run else fetch_recent(t["query"], window)
            proven = [] if args.dry_run else fetch_proven(t["query"])
        except Exception as e:  # 한 주제가 실패해도 나머지는 계속
            print(f"⚠️  '{label}' 조회 실패: {e}", file=sys.stderr)
            found[label] = []
            failed.append(label)
            continue
        fresh = select_papers(recent, proven, set(seen), per_topic, blocked)
        for p in fresh:
            new_ids.append(p["id"])
        found[label] = fresh
        hits = sum(1 for p in fresh if p.get("blocked_hits"))
        print(f"- {label}: 새 논문 {len(fresh)}편 (막힌 길목 관련 {hits}편)")

    total = sum(len(v) for v in found.values())
    with open(INBOX_PATH, "w", encoding="utf-8") as f:
        f.write(build_inbox(date, found, window, failed))

    for i in new_ids:
        seen[i] = date
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=0, sort_keys=True)

    print(f"✅ {INBOX_PATH} 갱신 — 새 논문 {total}편 (누적 확인 {len(seen)}편)")
    # 워크플로가 Issue 알림 여부를 판단할 수 있게 출력
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"new_count={total}\n")

    # 전부 실패했으면 **실패로 끝낸다** (2026-08-03 수정).
    # 예전에는 모든 주제의 조회가 죽어도 exit 0이라, 인박스에 "0편"이 적히고
    # 워크플로의 실패 알림도 뜨지 않았다. 사용자에게는 "주제를 넣었는데 아무 일도
    # 일어나지 않는다"로만 보이고 단서가 없었다 — 조용한 실패가 제일 나쁘다.
    if failed and len(failed) == len(topics):
        print(f"❌ 모든 주제({len(failed)}개)의 조회가 실패했다 — 수집이 이뤄지지 않았다.", file=sys.stderr)
        return 1
    if failed:
        print(f"⚠️  일부 주제 실패: {', '.join(failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
