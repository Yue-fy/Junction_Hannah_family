def test_review_markdown_no_gold():
    """stoa.eval.review renders gold-less rows (Stoa's example questions) without crashing."""
    from stoa.eval.review import review
    rows = [{"path": "data/cubicasa5k/x.png", "question": "How many doors?", "value": 3, "unit": "count",
             "confidence": 0.42, "solver": "pipeline/vlm_lora", "tier": "vlm", "correct": None,
             "evidence": [{"file": "data/cubicasa5k/x.png", "page": None, "bbox": [0, 0, 1, 1], "note": "door"}],
             "assumptions": ["a"], "missing": ["scale"], "cost": {"usd": 0.0001, "llm_calls": 1}, "latency_s": 1.0,
             "trace": ["t1", "t2"]},
            {"path": "data/x.pdf", "question": "What?", "value": None, "confidence": 0.1, "correct": None}]
    md = review(rows)
    assert "# Review: 2 questions" in md and "**3**" in md and "no answer" in md and "missing: scale" in md
    assert "scored against gold" not in md
