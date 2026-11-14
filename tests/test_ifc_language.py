"""ifc cross-language check (W1 c5): decision table of IfcSolver._cross_language with the LLM and the rules stubbed."""
import pytest

from stoa import llm
from stoa.contract import Answer
from stoa.solvers.ifc.parse import Intent
from stoa.solvers.ifc.solver import IfcSolver


def _ans(v, unit="count", conf=0.95):
    return Answer(value=v, unit=unit, confidence=conf, solver="ifc", trace=[])


def _it(kind):
    it = Intent("count", kind)
    it.kinds = [kind] if kind else []
    return it


@pytest.fixture
def run(monkeypatch):
    import stoa.router.prior as prior

    monkeypatch.setattr(prior, "known_template", lambda q: False)

    def go(question, raw, eng, translated=True):
        calls = []

        def fake_tr(q, force=False, **kw):
            calls.append(q)
            return llm.Translation(eng[2] if translated else q, "pl", translated, translated, q,
                                   "question translated from Polish" if translated else "translation failed")

        monkeypatch.setattr(llm, "to_english", fake_tr)
        S = IfcSolver()
        monkeypatch.setattr(S, "_core", lambda path, model, idx, q: (eng[0], eng[1], {"question": q}))
        ans, it, ctx = S._cross_language("x.ifc", "x.ifc", None, question, raw[0], raw[1], {"question": question})
        return ans, calls

    return go


def test_english_is_not_translated(run):
    ans, calls = run("How many doors are on 'Level 1'?", (_ans(6), _it("door")), (_ans(6), _it("door"), "-"))
    assert calls == [] and ans.value == 6 and ans.confidence == 0.95


def test_agreement_keeps_raw(run):
    ans, _ = run("Ile drzwi jest na 'Level 1'?", (_ans(6), _it("door")),
                 (_ans(6), _it("door"), "How many doors are on 'Level 1'?"))
    assert ans.value == 6 and ans.confidence == 0.95 and any("same answer" in t for t in ans.trace)


def test_same_kind_disagreement_uses_english(run):
    # "w stopach" (in feet) unread by the raw parse: metres at 0.95 vs feet from the English reading
    ans, _ = run("Jaka jest całkowita długość ścian na 'Level 1' w stopach?", (_ans(105.36, "m"), _it("wall")),
                 (_ans(345.66, "ft"), _it("wall"), "What is the total wall length on 'Level 1' in feet?"))
    assert ans.value == 345.66 and ans.confidence <= 0.75


def test_raw_without_element_kind_uses_english(run):
    ans, _ = run("Kummal korrusel on rohkem uksi, 'Level 1' või 'Level 2'?", (_ans(8), _it("storey")),
                 (_ans("Level 2", None, 0.89), _it("door"), "Which floor has more doors, 'Level 1' or 'Level 2'?"))
    assert ans.value == "Level 2" and ans.confidence <= 0.75


def test_translation_slip_keeps_parser_language_reading(run):
    # 'vloeren' (slabs) translated as 'floors' (storeys): the parser's own Dutch reading wins, less sure
    ans, _ = run("Wat is het totale netto volume van alle vloeren op 'Basement', in m³?", (_ans(151.1, "m3"), _it("slab")),
                 (_ans(0.8, "m3", 0.85), _it("storey"), "What is the total net volume of all floors on 'Basement'?"))
    assert ans.value == 151.1 and ans.confidence <= 0.75


def test_untranslated_unseen_wording_is_capped(run):
    ans, _ = run("Ile okien ma cały model?", (_ans(24), _it("window")), (None, None, ""), translated=False)
    assert ans.value == 24 and ans.confidence <= 0.75 and ans.missing
