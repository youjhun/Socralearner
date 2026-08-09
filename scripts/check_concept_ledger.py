#!/usr/bin/env python3
"""개념 레지스트리 ↔ 이해도 원장 드리프트 검사기.

왜 이게 필요한가 (2026-08-09에 실제로 겪은 것):
개념 그래프(`knowledge/concepts.yaml`)와 이해도 원장(`mastery.md`)은 같은 개념을 두 번
적는다 — 그래프는 정체(도메인·선수관계)를, 원장은 판정(암기/설명가능)을. 둘을 손으로만
맞추다 보니 **조용히 갈렸다**: 원장에는 있는데 그래프에는 없는 개념이 13개였고
(Fréchet mean·BH/FDR·bootstrap 등 가장 최근에 배운 것들), 그래서 그래프는 "요즘 뭘
배웠는지"를 통째로 못 비추고 있었다. 발전이 안 보이면 시스템은 정체로 비춘다.

그래서 계약을 명시로 바꿨다 — 레지스트리 항목은 `mastery:`로 원장의 **행 이름**을 가리키고,
판정은 원장이 이긴다(판정은 세션의 몫이고 레지스트리는 옮겨 적을 뿐이다).
이 스크립트는 그 계약이 지켜지는지 본다. 조용히 갈리는 것보다 시끄럽게 틀리는 게 낫다.

검사 넷:
  1. 원장에 있는데 어떤 레지스트리 항목도 가리키지 않는 행 → 그래프에서 사라진 개념
  2. `mastery:`가 원장에 없는 행을 가리킴 → 원장에서 이름이 바뀐 뒤 링크가 끊긴 것
  3. state/중요도/검증일이 원장과 다름 → 옮겨 적기가 밀린 것
  4. 끊긴 선수관계 → 그래프에서 화살표가 조용히 사라진다

실행: python3 scripts/check_concept_ledger.py        (CI·수동)
종료 코드: 문제가 있으면 1.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_concepts as B  # noqa: E402

REGISTRY = B.REGISTRY
MASTERY = B.MASTERY


def date_of(value):
    m = re.search(r"\d{4}-\d{2}-\d{2}", value or "")
    return m.group(0) if m else ""


def main():
    # 빈 레지스트리는 모드를 켜지 않는다(build_concepts.py와 같은 규칙). 템플릿이 함께 주는
    # 견본을 그대로 둔 사용자에게 "원장 행이 그래프에 없다"를 44줄 쏟지 않기 위해서다.
    concepts = B.load_registry()
    if not concepts:
        print(f"{REGISTRY} 비어 있음 — 노트 모드다. 검사할 것이 없다.")
        return 0

    mastery = B.parse_mastery(MASTERY)
    by_id = {c["id"]: c for c in concepts}

    problems = []
    linked_labels = set()

    for c in concepts:
        labels = c.get("mastery") or []
        if isinstance(labels, str):   # 한 행만 붙은 경우도 허용한다
            labels = [labels]
        rows = []
        for label in labels:
            if label not in mastery:
                problems.append(
                    f"[끊긴 링크] {c['id']}의 mastery: {label!r} — 원장에 그런 행이 없다 "
                    f"(원장에서 이름을 바꿨다면 여기도 바꿔라)")
                continue
            linked_labels.add(label)
            rows.append((date_of(mastery[label].get("verified")), label, mastery[label]))
        if not rows:
            continue

        # 판정은 원장이 이긴다. 여러 행이 붙었으면 **가장 늦게 검증된 행**이 대표한다.
        rows.sort(key=lambda r: r[0])
        _date, label, info = rows[-1]
        if c.get("state") != info.get("state"):
            problems.append(
                f"[상태 불일치] {c['id']}: 그래프={c.get('state')} / 원장={info.get('state')} "
                f"({label!r}) — 판정은 원장이 이긴다")
        imp = (info.get("importance") or "")[:1].upper()
        if imp and c.get("importance") != imp:
            problems.append(
                f"[중요도 불일치] {c['id']}: 그래프={c.get('importance')} / 원장={imp} ({label!r})")
        verified = date_of(info.get("verified"))
        if verified and str(c.get("verified") or "") != verified:
            problems.append(
                f"[검증일 불일치] {c['id']}: 그래프={c.get('verified')} / 원장={verified} ({label!r})")

    for label in mastery:
        if label not in linked_labels:
            problems.append(
                f"[그래프에 없음] 원장 행 {label!r} — 어떤 개념도 이 행을 가리키지 않는다. "
                f"레지스트리에 개념을 추가하고 `mastery:` 목록에 이 행 이름을 넣어라")

    for c in concepts:
        for key in ("prereq", "related"):
            for ref in c.get(key) or []:
                if ref not in by_id:
                    problems.append(f"[끊긴 {key}] {c['id']} → {ref} — 그래프에서 화살표가 사라진다")

    if not problems:
        print(f"레지스트리 ↔ 원장 일치 "
              f"(개념 {len(concepts)} · 원장 행 {len(mastery)} · 링크 {len(linked_labels)})")
        return 0

    print(f"레지스트리 ↔ 원장 불일치 {len(problems)}건:\n")
    for p in problems:
        print(f"  - {p}")
    print("\n판정은 원장(mastery.md)이 SSOT다. 그래프를 원장에 맞춰라.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
