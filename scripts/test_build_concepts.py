#!/usr/bin/env python3
"""`build_concepts.py`의 개념/항목 분리 테스트.

이 분리는 사용자의 기록을 그래프에서 빼는 판단이라 **오탐이 곧 손해**다. 그래서
"어휘 목록은 빠지는가"만큼 "정당한 개념은 남는가"를 같은 무게로 검사한다.

실행: python3 scripts/test_build_concepts.py   (의존성 없음)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_concepts as bc  # noqa: E402


def classify(labels, edges=(), explicit=()):
    """테스트 편의 래퍼 — 라벨과 (대상, 선수) 간선으로 분류를 돌린다."""
    id_of = {lb: bc.slugify(lb) for lb in labels}
    prereq_of = {}
    for target, prereq in edges:
        prereq_of.setdefault(id_of[target], []).append(id_of[prereq])
    return bc.classify_labels(labels, prereq_of, id_of, set(explicit))


VOCAB = ["procurement", "adjacent", "itinerary", "reimburse", "tentative",
         "warranty", "invoice", "premises", "vendor", "appraisal",
         "deductible", "compliance"]


class TestDrillSeparation(unittest.TestCase):
    def test_vocabulary_dump_is_pulled_out_of_the_graph(self):
        """토익 어휘를 통째로 부으면 전부 항목이 된다 — 그래프가 단어로 덮이지 않는다."""
        concepts, drills, _ = classify(VOCAB)
        self.assertEqual(concepts, [])
        self.assertEqual(len(drills), len(VOCAB))

    def test_gloss_shape_is_a_drill_even_when_few(self):
        """'단어 = 뜻' 꼴은 하나만 있어도 어휘장이다 — 강한 신호라 개수를 안 따진다."""
        _concepts, drills, reason = classify(["procurement = 조달", "적분 = 넓이"])
        self.assertIn("procurement = 조달", drills)
        self.assertIn("어휘장", reason["procurement = 조달"])

    def test_a_few_bare_words_stay_concepts(self):
        """소문자 토큰 몇 개로는 판정하지 않는다 — 새 개념이 그 모양일 수 있다."""
        concepts, drills, _ = classify(["backpropagation", "softmax", "attention"])
        self.assertEqual(drills, [])
        self.assertEqual(len(concepts), 3)

    def test_hierarchy_beats_shape(self):
        """위계에 참여하면 모양이 어휘 같아도 개념이다 — 그래프에서 실제로 일을 한다."""
        labels = VOCAB + ["backpropagation", "chain-rule"]
        concepts, drills, _ = classify(labels, edges=[("backpropagation", "chain-rule")])
        self.assertIn("backpropagation", concepts)
        self.assertIn("chain-rule", concepts)
        self.assertNotIn("backpropagation", drills)

    def test_being_someone_elses_prerequisite_also_protects(self):
        """남의 선수이기만 해도 개념이다 — 뿌리 개념은 자기 선수가 없다."""
        labels = VOCAB + ["vector"]
        concepts, _drills, _ = classify(labels, edges=[("procurement", "vector")])
        self.assertIn("vector", concepts)

    def test_uppercase_and_korean_are_never_auto_drilled(self):
        """약어·고유명사·한글 개념은 자동 판정 대상이 아니다."""
        labels = VOCAB + ["SVD", "ResNet", "푸리에 변환", "고윳값"]
        concepts, _drills, _ = classify(labels)
        for lb in ["SVD", "ResNet", "푸리에 변환", "고윳값"]:
            self.assertIn(lb, concepts)

    def test_explicit_drills_file_always_wins(self):
        """drills.md에 적었으면 위계가 있어도 항목이다 — 사람의 판단이 최종이다."""
        _concepts, drills, reason = classify(
            ["Part5 시제 일치", "procurement"],
            edges=[("Part5 시제 일치", "procurement")],
            explicit=["Part5 시제 일치"],
        )
        self.assertIn("Part5 시제 일치", drills)
        self.assertEqual(reason["Part5 시제 일치"], "drills.md에 적힘")

    def test_empty_input_is_safe(self):
        self.assertEqual(classify([]), ([], [], {}))


class TestBuildOutput(unittest.TestCase):
    def test_build_splits_concepts_and_drills(self):
        """concepts.json은 두 키를 낸다 — Topdown은 concepts만 읽어 그래프가 깨끗해진다."""
        mastery = {lb: {"state": "암기"} for lb in VOCAB}
        mastery["Part5 시제 일치"] = {"state": "설명가능"}
        data = bc.build(mastery, [("Part5 시제 일치", "동사 시제 기본")], {}, {})
        labels = [c["label"] for c in data["concepts"]]
        self.assertIn("Part5 시제 일치", labels)
        self.assertIn("동사 시제 기본", labels)
        self.assertEqual(len(data["drills"]), len(VOCAB))
        self.assertTrue(all(d["why_drill"] for d in data["drills"]))


class TestOverrides(unittest.TestCase):
    """지도 손보기 — 감추기·이름 합치기. 기록(노트)은 건드리지 않는다."""

    def test_hidden_drops_the_node_and_its_edges(self):
        edges = [("딥러닝", "선형대수"), ("오늘 한 것", "선형대수")]
        domain = {"딥러닝": "ML", "오늘 한 것": "잡동사니"}
        mastery = {"딥러닝": {"state": "암기"}, "오늘 한 것": {"state": "미학습"}}
        edges, domain, mastery, n = bc.apply_overrides(
            edges, domain, mastery, {"오늘 한 것"}, {}
        )
        # 엣지를 같이 빼지 않으면 그래프에 이름 없는 점이 남는다.
        self.assertEqual(edges, [("딥러닝", "선형대수")])
        self.assertNotIn("오늘 한 것", domain)
        self.assertNotIn("오늘 한 것", mastery)
        self.assertEqual(n, 2)

    def test_rename_merges_two_names_into_one(self):
        edges = [("Fréchet 평균", "측지선"), ("Fréchet mean", "리만다양체")]
        mastery = {"Fréchet 평균": {"state": "암기"}, "Fréchet mean": {"state": "설명가능"}}
        edges, domain, mastery, _ = bc.apply_overrides(
            edges, {}, mastery, set(), {bc._fold("Fréchet 평균"): "Fréchet mean"}
        )
        self.assertEqual(
            edges, [("Fréchet mean", "측지선"), ("Fréchet mean", "리만다양체")]
        )
        self.assertEqual(list(mastery), ["Fréchet mean"])

    def test_hiding_by_the_old_name_still_works(self):
        """이름을 바꾼 뒤 옛 이름으로 감춰도 잡힌다 — 순서가 반대면 새 이름이 살아남는다."""
        edges, _, mastery, _ = bc.apply_overrides(
            [("옛 이름", "선형대수")], {}, {"옛 이름": {}},
            {"옛 이름"}, {bc._fold("옛 이름"): "새 이름"},
        )
        self.assertEqual(edges, [])
        self.assertEqual(mastery, {})

    def test_self_rename_is_refused(self):
        """A → A는 무한 루프의 씨앗이라 로더가 애초에 받지 않는다."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("hidden: []\nrenamed:\n  - from: A\n    to: A\n")
            path = f.name
        try:
            _, renamed = bc.load_overrides(path)
        finally:
            os.unlink(path)
        self.assertEqual(renamed, {})

    def test_missing_file_changes_nothing(self):
        self.assertEqual(bc.load_overrides("does-not-exist.yaml"), (set(), {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
