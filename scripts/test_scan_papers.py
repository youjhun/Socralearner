#!/usr/bin/env python3
"""scan_papers 회귀 테스트 — 네트워크 없이 순수 로직만 검사한다.

실행: python3 scripts/test_scan_papers.py

2026-08-03에 잡은 버그 세 개를 여기서 지킨다:
  ① 초록 없는 논문을 전부 버려 결과가 0편이 되던 것
  ② 조회가 전부 실패해도 "0편"으로 성공 처리되던 것
  ③ 인박스가 "없음"과 "못 가져옴"을 구별하지 못하던 것
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_papers as sp  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


def work(i, abstract=True, author=None, venue="arXiv", date="2026-07-30"):
    """OpenAlex 응답 한 건을 흉내낸다."""
    return sp.normalize_work({
        "id": f"https://openalex.org/W{i}",
        "title": f"Neural decoding paper {i}",
        "publication_date": date,
        "cited_by_count": 10 - i,
        "authorships": [{"author": {"display_name": author or f"Author {i}"}}],
        "primary_location": {"source": {"display_name": venue}},
        # OpenAlex는 출판사 라이선스 때문에 초록을 주지 않는 경우가 매우 흔하다.
        "abstract_inverted_index": {"We": [0], "study": [1], "decoding": [2]} if abstract else None,
    })


print("① 초록이 없어도 버리지 않는다 (예전엔 0편이 됐다)")
no_abs = [work(i, abstract=False) for i in range(25)]
picked = sp.select_papers(no_abs, no_abs, set(), 5, [])
check("초록 0편짜리 응답에서도 5편을 고른다", len(picked) == 5, f"고른 수={len(picked)}")

print("② 초록 있는 것이 먼저 온다 (버리지 않되 뒤로 민다)")
mixed = [work(i, abstract=(i >= 20)) for i in range(25)]
picked = sp.select_papers(mixed, [], set(), 3, [])
check("초록 있는 것이 앞자리를 차지한다", all(p["abstract"] for p in picked[:1]),
      f"첫 항목 초록={bool(picked[0]['abstract']) if picked else 'N/A'}")

print("③ 막힌 길목과 닿는 논문이 초록 유무보다 우선한다")
# 2트랙이라 recent만 주면 per_topic의 60%(신간 몫)까지만 뽑힌다 — 설계대로다.
blocked = [("디코딩", ["decoding"])]
pool3 = [work(i, abstract=False) for i in range(5)]          # 제목에 decoding 있음
pool3 += [work(90 + i, abstract=True) for i in range(5)]      # 역시 있음
for p in pool3[5:]:
    p["title"] = "Unrelated topic"
picked = sp.select_papers(pool3, [], set(), 5, blocked)
check("신간 몫(3편)이 다 채워진다 — 초록 없다고 비지 않는다", len(picked) == 3, f"고른 수={len(picked)}")
check("막힌 개념이 든 것이 먼저 온다", all(p["blocked_hits"] for p in picked),
      f"hits={[bool(p['blocked_hits']) for p in picked]}")

print("④ 이미 본 논문은 다시 뽑지 않는다")
pool = [work(i) for i in range(10)]
seen = {p["id"] for p in pool[:8]}
picked = sp.select_papers(pool, [], set(seen), 5, [])
check("seen에 든 것은 제외된다", all(p["id"] not in seen for p in picked))

print("⑤ 같은 1저자가 트랙을 독차지하지 않는다")
same = [work(i, author="Same Person") for i in range(10)]
picked = sp.select_papers(same, [], set(), 5, [])
check("한 저자 2편까지만", len(picked) <= 2, f"고른 수={len(picked)}")

print("⑥ 인박스가 '없음'과 '못 가져옴'을 구별한다")
empty = sp.build_inbox("2026-08-03", {"BCI": []}, 14, failed=[])
broken = sp.build_inbox("2026-08-03", {"BCI": []}, 14, failed=["BCI"])
check("실패가 없으면 '새로 걸린 논문이 없다'", "새로 걸린 논문이 없다" in empty)
check("실패하면 '가져오지 못한' 것이라고 말한다", "가져오지 못한" in broken and "조회 실패" in broken)
check("실패 주제 이름이 인박스에 남는다", "BCI" in broken)

print("⑦ 초록 없는 논문도 인박스에 이유와 함께 실린다")
md = sp.build_inbox("2026-08-03", {"BCI": [dict(work(1, abstract=False), track="신간")]}, 14)
check("초록이 없다는 사실을 적는다", "초록이 공개돼 있지 않다" in md)

print()
if FAILED:
    print(f"실패 {len(FAILED)}개: " + ", ".join(FAILED))
    sys.exit(1)
print("전부 통과")
