#!/usr/bin/env python3
"""`build_concepts.py` 테스트 — 개념/항목 분리, 지도 손보기, 레지스트리 번역.

개념/항목 분리는 사용자의 기록을 그래프에서 빼는 판단이라 **오탐이 곧 손해**다. 그래서
"어휘 목록은 빠지는가"만큼 "정당한 개념은 남는가"를 같은 무게로 검사한다.

레지스트리 번역은 **두 모드가 갈라지지 않는가**를 본다 — 레지스트리는 별도 빌드 경로가
아니라 네 재료로 번역되어 같은 파이프라인을 타야 한다. 갈라지면 지도 손보기·분야 정규화가
한쪽에서만 돌고, 사용자가 쓰는 손잡이가 모드에 따라 달라진다.

실행: python3 scripts/test_build_concepts.py   (의존성 없음 — PyYAML이 없으면 해당 테스트만 건너뛴다)
"""
import os
import sys
import tempfile
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


NOTE = """\
# 2026-07-19 세션

## 오늘 직접 학습한 지식

- 행렬-벡터 곱은 입력 벡터를 선형변환에 통과시키는 연산이다.
  이어지는 들여쓴 줄은 같은 항목이다.
- 다음 항목은 여기서 끊긴다.

## 교정

문단 첫 줄이다.
입력 벡터 \\(v\\)와 출력 벡터 \\(Av\\)는 같은 공간에 있다.
문단 마지막 줄이다.
"""


class TestAnchors(unittest.TestCase):
    """앵커 해석 — Hunwiki `build_knowledge_graph.py`의 `extract_block`과 **같은 의미**여야 한다.

    같은 노트를 읽는 두 빌더가 다른 조각을 꺼내면 두 그래프가 조용히 갈린다.
    """

    def test_list_item_takes_its_indented_continuation(self):
        block = bc.extract_block(NOTE, "행렬-벡터 곱은")
        self.assertIn("이어지는 들여쓴 줄", block)
        self.assertNotIn("다음 항목은", block)

    def test_paragraph_takes_the_whole_paragraph(self):
        block = bc.extract_block(NOTE, "출력 벡터")
        self.assertIn("문단 첫 줄이다.", block)
        self.assertIn("문단 마지막 줄이다.", block)
        self.assertNotIn("## 교정", block)

    def test_first_occurrence_wins(self):
        """앵커는 **처음 걸린 자리**를 꺼낸다 — 앞 문단에도 있는 말을 앵커로 쓰면 그쪽이 나온다.

        Hunwiki 빌더와 같은 규칙이다. 좁은 앵커를 고르는 것이 러너의 몫이라는 뜻이기도 하다.
        """
        block = bc.extract_block(NOTE, "입력 벡터")
        self.assertIn("행렬-벡터 곱은", block)

    def test_missing_needle_is_none_not_empty(self):
        """못 찾은 것과 빈 것은 다르다 — 전자는 보고해야 하고 후자는 정상이다."""
        self.assertIsNone(bc.extract_block(NOTE, "여기 없는 문장"))

    def test_normalize_math_moves_delimiters_only(self):
        self.assertEqual(bc.normalize_math(r"\(Av\)를 본다"), "$Av$를 본다")
        self.assertEqual(bc.normalize_math(r"\[x=1\]"), "$$x=1$$")
        # 내용은 한 글자도 바뀌지 않는다.
        self.assertEqual(bc.normalize_math(r"\(\mathbb{R}^2\)"), r"$\mathbb{R}^2$")

    def test_plain_text_is_untouched(self):
        self.assertEqual(bc.normalize_math("수식 없는 줄"), "수식 없는 줄")


class TestRegistryTranslation(unittest.TestCase):
    """레지스트리 → (mastery, edges, domain_of, sources) 번역."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.note = os.path.join(self.tmp.name, "note.md")
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(NOTE)
        self.addCleanup(self.tmp.cleanup)

    def registry(self, **over):
        entry = {
            "id": "matrix-vector-map",
            "label": "행렬-벡터 곱 = 선형변환",
            "domain": "linear-algebra",
            "state": "설명가능",
            "importance": "H",
            "verified": "2026-07-22",
            "sources": [{"file": self.note, "kind": "지식", "match": "행렬-벡터 곱은"}],
        }
        entry.update(over)
        return [entry, {"id": "vector-space", "label": "벡터공간", "domain": "linear-algebra",
                        "state": "암기", "importance": "M"}]

    def test_curated_id_survives_slugify(self):
        """`matrix-vector-map`이 라벨 slugify로 덮이면 Hunwiki graph.json과 점이 갈린다."""
        mastery, edges, domain_of, sources, ids, problems = bc.registry_ingredients(
            self.registry(prereq=["vector-space"])
        )
        data = bc.build(mastery, edges, domain_of, sources, ids)
        by_label = {c["label"]: c for c in data["concepts"]}
        self.assertEqual(by_label["행렬-벡터 곱 = 선형변환"]["id"], "matrix-vector-map")
        self.assertEqual(by_label["행렬-벡터 곱 = 선형변환"]["prereq"], ["vector-space"])
        self.assertEqual(problems, [])

    def test_optional_keys_ride_through_build(self):
        """Topdown RawConcept이 선언하는 선택 키를 `build()`가 버리지 않는다."""
        mastery, edges, domain_of, sources, ids, _ = bc.registry_ingredients(
            self.registry(related=["vector-space"], open_questions=["왜 그런가"],
                          wikipedia={"en": ["Linear map"]}, note="열벡터 가중결합")
        )
        entry = bc.build(mastery, edges, domain_of, sources, ids)["concepts"][0]
        self.assertEqual(entry["related"], ["vector-space"])
        self.assertEqual(entry["open_questions"], ["왜 그런가"])
        self.assertEqual(entry["wikipedia"], {"en": ["Linear map"]})
        self.assertEqual(entry["verified"], "2026-07-22")
        self.assertEqual(entry["note"], "열벡터 가중결합")

    def test_absent_optional_keys_are_absent_not_empty(self):
        """키가 없는 것과 빈 값은 다르다 — 빈 값은 '비어 있음'을 주장한다."""
        mastery, edges, domain_of, sources, ids, _ = bc.registry_ingredients(self.registry())
        entry = bc.build(mastery, edges, domain_of, sources, ids)["concepts"][0]
        for key in ("related", "open_questions", "wikipedia"):
            self.assertNotIn(key, entry)

    def test_note_mode_still_puts_the_verified_column_in_note(self):
        """원장에는 note 칸이 없어 검증 칸이 note로 간다 — 옛 동작이 그대로 남아야 한다."""
        entry = bc.build({"개념": {"state": "암기", "verified": "2026-08-01"}}, [], {}, {})
        self.assertEqual(entry["concepts"][0]["note"], "2026-08-01")

    def test_anchor_pulls_source_text_verbatim(self):
        _m, _e, _d, sources, _i, problems = bc.registry_ingredients(self.registry())
        match = sources["행렬-벡터 곱 = 선형변환"][0]["match"]
        self.assertIn("선형변환에 통과시키는", match)
        self.assertEqual(problems, [])

    def test_broken_prereq_is_reported_not_silently_dropped(self):
        """끊긴 화살표는 그래프에서 조용히 사라진다 — 지우지 말고 말한다."""
        _m, edges, _d, _s, _i, problems = bc.registry_ingredients(
            self.registry(prereq=["does-not-exist"])
        )
        self.assertEqual(edges, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("does-not-exist", problems[0])

    def test_missing_source_file_is_reported(self):
        _m, _e, _d, _s, _i, problems = bc.registry_ingredients(
            self.registry(sources=[{"file": "no/such.md", "match": "x"}])
        )
        self.assertTrue(any("소스 파일 없음" in p for p in problems))

    def test_failed_anchor_is_reported_and_concept_survives(self):
        """근거를 못 찾아도 개념은 남는다 — 기록이 먼저다."""
        mastery, edges, domain_of, sources, ids, problems = bc.registry_ingredients(
            self.registry(sources=[{"file": self.note, "match": "여기 없는 문장"}])
        )
        self.assertTrue(any("앵커 실패" in p for p in problems))
        labels = [c["label"] for c in bc.build(mastery, edges, domain_of, sources, ids)["concepts"]]
        self.assertIn("행렬-벡터 곱 = 선형변환", labels)

    def test_state_and_domain_come_across(self):
        mastery, edges, domain_of, sources, ids, _ = bc.registry_ingredients(self.registry())
        data = bc.build(mastery, edges, domain_of, sources, ids)
        entry = data["concepts"][0]
        self.assertEqual(entry["state"], "설명가능")
        self.assertEqual(entry["domain"], "linear-algebra")
        self.assertEqual(entry["importance"], "H")

    def test_entry_without_id_is_reported_not_crashed(self):
        _m, _e, _d, _s, _i, problems = bc.registry_ingredients([{"label": "id 없음"}])
        self.assertTrue(any("id 없는 항목" in p for p in problems))


class TestEmptyRegistryStaysNoteMode(unittest.TestCase):
    """빈 견본이 노트 모드를 끄면, 아무것도 안 한 사용자의 그래프가 이유 없이 비어 버린다."""

    def test_empty_registry_file_loads_as_falsy(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML 없음")
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("concepts: []\n")
            path = f.name
        try:
            self.assertFalse(bc.load_registry(path))
        finally:
            os.unlink(path)

    def test_absent_registry_loads_as_falsy(self):
        self.assertFalse(bc.load_registry("does-not-exist.yaml"))


class TestRegistryPlusNotes(unittest.TestCase):
    """레지스트리가 이기되, 거기 없는 것은 노트에서 받는다.

    이게 없으면 세션이나 앱이 새로 만든 `## 개념 지도`가 그래프에 **영영 안 들어간다** —
    자료를 올려 증류까지 됐는데 노드가 안 늘면 사람은 같은 자료를 다시 올린다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.makedirs("daily")
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(os.chdir, self.cwd)

    def write(self, rel, text):
        os.makedirs(os.path.dirname(rel) or ".", exist_ok=True)
        with open(rel, "w", encoding="utf-8") as f:
            f.write(text)

    def registry_side(self):
        """레지스트리에서 온 재료 — 개념 하나(푸리에 변환)."""
        mastery = {"푸리에 변환": {"state": "설명가능", "importance": "H", "note": "",
                                "verified": "2026-08-01", "evidence": ""}}
        sources = {"푸리에 변환": [{"file": "x.md", "kind": "지식", "match": "앵커에서 꺼낸 원문"}]}
        return mastery, [], {"푸리에 변환": "신호처리"}, sources, {"푸리에 변환": "fourier"}

    def test_note_edges_outside_the_registry_are_taken(self):
        self.write("materials/lec08/distilled.md",
                   "## 개념 지도\n### 딥러닝\n- 어텐션 ← 내적\n")
        mastery, edges, domain_of, sources, ids = self.registry_side()
        n_c, n_e = bc.merge_note_ingredients(mastery, edges, domain_of, sources, ids)
        self.assertEqual((n_c, n_e), (2, 1))
        self.assertIn(("어텐션", "내적"), edges)
        self.assertEqual(domain_of["어텐션"], "딥러닝")

    def test_registry_concept_keeps_its_domain_and_curated_id(self):
        """노트가 같은 개념을 다른 분야로 적어도 레지스트리가 이긴다."""
        self.write("daily/2026-08-09-x.md", "## 개념 지도\n### 잡동사니\n- 푸리에 변환\n")
        mastery, edges, domain_of, sources, ids = self.registry_side()
        bc.merge_note_ingredients(mastery, edges, domain_of, sources, ids)
        self.assertEqual(domain_of["푸리에 변환"], "신호처리")
        data = bc.build(mastery, edges, domain_of, sources, ids)
        entry = next(c for c in data["concepts"] if c["label"] == "푸리에 변환")
        self.assertEqual(entry["id"], "fourier")

    def test_registry_sources_are_not_augmented_from_notes(self):
        """큐레이션된 앵커가 근거의 전부다 — 노트에서 더 긁으면 근거 수가 조용히 부푼다."""
        self.write("daily/2026-08-09-x.md",
                   "## 오늘 직접 학습한 지식\n- 푸리에 변환은 회전이다\n")
        mastery, edges, domain_of, sources, ids = self.registry_side()
        bc.merge_note_ingredients(mastery, edges, domain_of, sources, ids)
        self.assertEqual(len(sources["푸리에 변환"]), 1)
        self.assertEqual(sources["푸리에 변환"][0]["match"], "앵커에서 꺼낸 원문")

    def test_new_concepts_take_their_state_from_the_ledger(self):
        """판정은 원장이 SSOT다 — 레지스트리 밖이라고 다르지 않다."""
        self.write("mastery.md", "| 개념 | 상태 | 중요도 |\n| --- | --- |\n| 어텐션 | 암기 | H |\n")
        self.write("daily/2026-08-09-x.md", "## 개념 지도\n- 어텐션 ← 내적\n")
        mastery, edges, domain_of, sources, ids = self.registry_side()
        bc.merge_note_ingredients(mastery, edges, domain_of, sources, ids)
        self.assertEqual(mastery["어텐션"]["state"], "암기")
        self.assertEqual(mastery["내적"], {})   # 원장에 없으면 빈 칸 → build()가 미학습으로

    def test_an_edge_the_registry_already_has_is_not_duplicated(self):
        self.write("daily/2026-08-09-x.md", "## 개념 지도\n- 푸리에 변환 ← 복소지수\n")
        mastery, edges, domain_of, sources, ids = self.registry_side()
        edges.append(("푸리에 변환", "복소지수"))
        _n_c, n_e = bc.merge_note_ingredients(mastery, edges, domain_of, sources, ids)
        self.assertEqual(n_e, 0)
        self.assertEqual(edges.count(("푸리에 변환", "복소지수")), 1)

    def test_a_papers_concept_map_reaches_the_graph(self):
        """논문 폴더의 개념 지도도 그래프로 간다 — 아니면 증류가 갈 곳이 없다."""
        self.write("papers/attention/distilled.md", "## 개념 지도\n### 딥러닝\n- 어텐션 ← 내적\n")
        mastery, edges, domain_of, sources, ids = self.registry_side()
        _n_c, n_e = bc.merge_note_ingredients(mastery, edges, domain_of, sources, ids)
        self.assertEqual(n_e, 1)
        self.assertIn(("어텐션", "내적"), edges)

    def test_no_notes_changes_nothing(self):
        mastery, edges, domain_of, sources, ids = self.registry_side()
        before = (dict(mastery), list(edges), dict(domain_of))
        self.assertEqual(bc.merge_note_ingredients(mastery, edges, domain_of, sources, ids), (0, 0))
        self.assertEqual((mastery, edges, domain_of), before)


class TestRenameKeysUnderOverrides(unittest.TestCase):
    """이름을 합칠 때 큐레이션된 id와 앵커 근거가 따라가야 한다."""

    def test_surviving_name_keeps_its_curated_id(self):
        ids = {"Fréchet 평균": "frechet-mean-ko", "Fréchet mean": "frechet-mean"}
        renamed = {bc._fold("Fréchet 평균"): "Fréchet mean"}
        self.assertEqual(bc._rename_keys(ids, renamed), {"Fréchet mean": "frechet-mean"})

    def test_sources_of_both_names_are_merged(self):
        sources = {"옛 이름": [{"match": "a"}], "새 이름": [{"match": "b"}]}
        renamed = {bc._fold("옛 이름"): "새 이름"}
        merged = bc._rename_keys(sources, renamed, merge=True)
        self.assertEqual([s["match"] for s in merged["새 이름"]], ["b", "a"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
