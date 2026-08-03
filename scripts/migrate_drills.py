#!/usr/bin/env python3
"""이미 쓰고 있던 저장소의 그래프 청소기 — 단어 단위 노드를 항목으로 내린다.

왜 필요한가 (2026-08-03):
개념의 단위가 정의돼 있지 않던 시절에 만들어진 저장소는 그래프가 **재료 그대로** 쌓여 있다.
토익 트랙에서 어휘 하나하나가 노드가 된 것이 그 예다. 노드가 수백 개가 되면 막힌 길목이
묻혀 그래프가 아무것도 말해 주지 않는다.

이 스크립트가 하는 일은 **하나뿐이다** — 항목으로 판정된 라벨을 `drills.md`에 적는다.
`mastery.md`는 건드리지 않는다:

  · 원장은 사용자의 기록이다. 스크립트가 지울 것이 아니다.
  · `mastery.md`의 AUTO 표는 `mastery/` 조각에서 재생성되므로, 거기서 지워 봤자 다음
    consolidate에서 되살아난다 — 지우는 시늉만 하는 셈이다.
  · `build_concepts.py`가 `drills.md`를 보고 그래프에서 빼므로, 적기만 하면 목적은 달성된다.

되돌리려면 `drills.md`에서 그 줄을 지우고 다시 빌드하면 된다. 파괴적인 단계가 없다.

실행:
    python3 scripts/migrate_drills.py           # 진단만 — 무엇이 항목으로 빠질지 보여준다
    python3 scripts/migrate_drills.py --apply   # drills.md에 기록하고 concepts.json 재생성
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_concepts as bc  # noqa: E402


def analyze():
    """현재 저장소 상태로 개념/항목을 갈라 본다 — build_concepts와 같은 판단을 쓴다."""
    mastery = bc.parse_mastery()
    edges, domain_of = bc.parse_concept_map()

    labels = list(mastery.keys())
    for target, prereq in edges:
        for lb in (target, prereq):
            if lb not in labels:
                labels.append(lb)
    for lb in domain_of:
        if lb not in labels:
            labels.append(lb)

    id_of = {lb: bc.slugify(lb) for lb in labels}
    prereq_of = {}
    for target, prereq in edges:
        prereq_of.setdefault(id_of[target], [])
        pid = id_of[prereq]
        if pid not in prereq_of[id_of[target]]:
            prereq_of[id_of[target]].append(pid)

    existing = bc.parse_drills()
    concepts, drills, reason = bc.classify_labels(labels, prereq_of, id_of, existing)
    fresh = [lb for lb in drills if lb not in existing]
    return concepts, drills, fresh, reason


def append_to_drills(labels, path=bc.DRILLS):
    """항목 라벨을 `drills.md`에 덧붙인다. 파일이 없으면 머리말과 함께 만든다."""
    header = [
        "---",
        'title: "드릴 항목 (회상 대상)"',
        "kind: drills",
        "---",
        "",
        "# 드릴 항목 — 그래프에 넣지 않는 것",
        "",
        "> 답이 하나로 끝나고 위계에 참여하지 않는 것(단어 뜻·연호·값)을 모은다.",
        "> 개념 그래프는 *설명 대상*만 담는다 — 여기 있는 것은 복습에 쓰되 노드가 되지 않는다.",
        "",
    ]
    lines = header
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().rstrip().splitlines()
    lines += ["", "## 그래프 청소로 옮겨진 항목 (migrate_drills.py)"]
    lines += ["- %s" % lb for lb in labels]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def main():
    ap = argparse.ArgumentParser(description="단어 단위 노드를 항목으로 내린다")
    ap.add_argument("--apply", action="store_true",
                    help="drills.md에 기록하고 concepts.json을 다시 만든다 (기본은 진단만)")
    args = ap.parse_args()

    if not os.path.exists(bc.MASTERY):
        print("mastery.md가 없다 — 저장소 루트에서 실행하세요.")
        return 1

    concepts, drills, fresh, reason = analyze()
    total = len(concepts) + len(drills)

    print(f"지금 라벨 {total}개 → 개념 {len(concepts)} · 항목 {len(drills)}")
    if not fresh:
        print("\n✅ 옮길 것이 없습니다 — 그래프에 단어 단위 노드가 보이지 않습니다.")
        return 0

    print(f"\n항목으로 내릴 후보 {len(fresh)}개:")
    for lb in fresh[:30]:
        print(f"  · {lb}  ({reason.get(lb, '')})")
    if len(fresh) > 30:
        print(f"  · … 외 {len(fresh) - 30}개")

    print("\n남는 개념:")
    for lb in concepts[:20]:
        print(f"  ✓ {lb}")
    if len(concepts) > 20:
        print(f"  ✓ … 외 {len(concepts) - 20}개")

    if not args.apply:
        print("\n진단만 했습니다. 목록이 맞으면 다시 실행하세요:")
        print("    python3 scripts/migrate_drills.py --apply")
        print("\n개념인데 후보에 잘못 들어온 것이 있으면, 그 개념에 선수관계를 하나 주세요 —")
        print("daily 노트의 `## 개념 지도`에 `그 개념 ← 선수 개념` 한 줄이면 개념으로 남습니다")
        print("(위계에 참여하는 라벨은 절대 항목으로 내려가지 않습니다).")
        return 0

    append_to_drills(fresh)
    print(f"\n✅ `{bc.DRILLS}`에 {len(fresh)}개 기록. mastery.md는 그대로 뒀습니다(기록은 기록이다).")
    print("   되돌리려면 drills.md에서 그 줄을 지우고 다시 빌드하세요.\n")
    return bc.main()


if __name__ == "__main__":
    sys.exit(main())
