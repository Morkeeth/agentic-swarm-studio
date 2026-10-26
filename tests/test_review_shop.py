import json
import pytest

from sim import review_shop


def test_batch_covers_five_distinct_app_kinds():
    assert len(review_shop.APPS) == 5
    assert len({row["kind"] for row in review_shop.APPS}) == 5
    assert all(row["url"].startswith("https://") and row["goal"] for row in review_shop.APPS)


def test_ultra_has_a_bounded_registered_price():
    price = review_shop.hosted_cost.rates(review_shop.hosted_cost.ULTRA_MODEL)
    assert price["id_verified"] is True
    assert price["prompt_bytes"] == 30000
    assert review_shop.hosted_cost.worst_case(1, review_shop.hosted_cost.ULTRA_MODEL) < 1


def test_candidates_keep_screenshot_evidence_and_app_identity():
    rows = review_shop.candidate_rows([{
        "id": "store", "findings": [{"kind": "error_page", "title": "Missing product",
        "page": "https://shop.example/missing", "what_happened": "404", "page_text": "Not found",
        "evidence": [{"name": "Phone", "goal": "Open product", "step": 2, "said": "It is missing", "screenshot": "v-phone.png"}]}]
    }])
    assert rows == [{"id": "store-F1", "app": "store", "kind": "error_page", "title": "Missing product",
                     "page": "https://shop.example/missing", "what_happened": "404", "page_text": "Not found",
                     "screenshots": ["v-phone.png"],
                     "visitor_evidence": [{"name": "Phone", "goal": "Open product", "step": 2, "said": "It is missing"}]}]


def test_precision_is_only_computed_from_human_checked_findings():
    batch = {"models": {}, "spend": {}, "triage": {"decisions": []}, "results": [],
             "candidates": [{"id": "a-F1", "app": "a"}, {"id": "a-F2", "app": "a"}, {"id": "a-F3", "app": "a"}]}
    report = review_shop.full_report(batch, {"a-F1": {"confirmed": True}, "a-F2": {"confirmed": False}})
    assert report["precision"] == {"confirmed_real": 1, "human_reviewed": 2, "value": 0.5, "label": "1 of 2"}
    assert report["findings"][2]["human_confirmation"]["confirmed"] is None


def test_no_review_is_never_reported_as_zero_precision():
    report = review_shop.full_report({"models": {}, "spend": {}, "triage": {"decisions": []}, "results": [], "candidates": []})
    assert report["precision"]["value"] is None
    assert report["precision"]["label"] == "not measured"


def test_human_confirmation_file_is_explicit(tmp_path):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps({"findings": [{"id": "x-F1", "confirmed": True, "note": "404 visible",
                                              "reviewer": "A. Person", "method": "clicked the link in a fresh run",
                                              "reproduced_against": "the app's documented Flask server"}]}))
    assert review_shop.human_map(path)["x-F1"]["reviewer"] == "A. Person"


def test_unnamed_or_wrong_runtime_confirmation_is_rejected(tmp_path):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps({"findings": [{"id": "x-F1", "confirmed": True, "method": "looked at a screenshot"}]}))
    with pytest.raises(ValueError, match="name of the person"):
        review_shop.human_map(path)
    path.write_text(json.dumps({"findings": [{"id": "x-F1", "confirmed": True, "reviewer": "A. Person",
                                              "method": "looked at a static copy"}]}))
    with pytest.raises(ValueError, match="intended app runtime"):
        review_shop.human_map(path)


def test_review_page_hides_idle_progress_and_changes_copy_only_after_start():
    root = review_shop.Path(__file__).resolve().parents[1] / "web" / "review"
    css = (root / "review.css").read_text()
    html = (root / "index.html").read_text()
    js = (root / "review.js").read_text()
    assert "[hidden] { display: none !important; }" in css
    assert 'id="progress" class="progress" hidden' in html
    assert "No visitor has moved yet" in html
    assert js.index("The run started. Software visitors are moving") > js.index("await api('/api/studio/runs'")
    assert "The review could not start." in js and "Visit did not start" in js


def test_browser_failure_is_not_reported_as_a_completed_app_review():
    batch = {"models": {"steps": "Nano"}, "spend": {"accounted_usd": 0.1}, "triage": {"decisions": []},
             "candidates": [], "results": [{"id": "one", "baseline": [{"label": "The page loads", "status": "failed"}],
                                                "tries": [[{"name": "Visitor", "outcome": "not_finished", "steps": []}]],
                                                "spend": {"calls": [], "models": []}}]}
    report = review_shop.full_report(batch)
    assert report["status"] == "incomplete"
    assert report["coverage"] == {"apps_planned": 1, "apps_visited": 0,
                                  "reason": "Browser startup failed before Nano could visit."}
    assert report["apps"][0]["coverage"] == "browser_failed_before_model"
