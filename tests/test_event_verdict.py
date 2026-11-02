import json
import pytest

URLS = ["https://a.com", "https://b.com", "https://c.com"]

@pytest.fixture
def contract(direct_deploy):
    return direct_deploy("contracts/event_verdict.py")

@pytest.fixture
def query(contract, direct_vm, direct_alice):
    with direct_vm.prank(direct_alice):
        return contract.create_query("Did X happen?", "2026-12-31", "FINANCE", URLS)

def mock(vm, resolution="YES", confidence=98, readable=3, raw=None, summary=None):
    vm.clear_mocks()
    for i, url in enumerate(URLS):
        vm.mock_web(url, {"status": 200, "body":
            "Official dated evidence explicitly confirms the event outcome after the deadline."
            if i < readable else ""})
    data = {"resolution": resolution, "confidence": confidence,
            "reasoning": "Dated official evidence confirms the outcome.",
            "sources_readable": readable,
            "evidence_summary": summary if summary is not None else [
                {"url": u, "readable": i < readable, "relevant": i < readable,
                 "key_finding": "Explicit event evidence"} for i, u in enumerate(URLS)]}
    vm.mock_llm(r".*event resolution oracle.*", raw if raw is not None else json.dumps(data))

def resolve(contract, query, vm, **kwargs):
    mock(vm, **kwargs)
    contract.resolve_query(query)
    return json.loads(contract.get_resolution(query))

def test_yes_resolution(contract, query, direct_vm):
    r = resolve(contract, query, direct_vm)
    assert query == "1" and contract.get_count() == 1
    assert (r["resolution"], r["confidence"], r["sources_readable"], r["status"]) == ("YES", 98, 3, "RESOLVED")
    assert len(json.loads(r["evidence_summary"])) == 3
    assert direct_vm.run_validator() is True

def test_no_resolution(contract, query, direct_vm):
    r = resolve(contract, query, direct_vm, resolution="NO", confidence=92)
    assert (r["resolution"], r["status"]) == ("NO", "RESOLVED")

def test_too_early_resolution(contract, query, direct_vm):
    for _ in range(2):
        r = resolve(contract, query, direct_vm, resolution="TOO_EARLY")
        assert (r["status"], r["resolution"]) == ("PENDING", "TOO_EARLY")

def test_too_early_then_resolved(contract, query, direct_vm):
    resolve(contract, query, direct_vm, resolution="TOO_EARLY")
    assert resolve(contract, query, direct_vm)["status"] == "RESOLVED"

def test_inconclusive_insufficient_sources(contract, query, direct_vm):
    r = resolve(contract, query, direct_vm, readable=0)
    assert (r["resolution"], r["status"]) == ("INCONCLUSIVE", "UNRESOLVABLE")

def test_inconclusive_one_source(contract, query, direct_vm):
    assert resolve(contract, query, direct_vm, readable=1)["resolution"] == "INCONCLUSIVE"

def test_exactly_two_sources_allows_yes(contract, query, direct_vm):
    r = resolve(contract, query, direct_vm, readable=2)
    assert (r["resolution"], r["status"]) == ("YES", "RESOLVED")

def test_contradictory_sources_inconclusive(contract, query, direct_vm):
    mock(direct_vm, resolution="INCONCLUSIVE")
    direct_vm._web_mocks.clear()
    for url, body in zip(URLS, [
        "Bitcoin closed above $100,000 on October 31, 2026, according to the exchange.",
        "Bitcoin closed at $98,500 on October 31, 2026, according to the same exchange.",
        "Reports disagree about the Bitcoin closing price on October 31, 2026."]):
        direct_vm.mock_web(url, {"status": 200, "body": body})
    contract.resolve_query(query)
    assert json.loads(contract.get_resolution(query))["resolution"] == "INCONCLUSIVE"

def test_yes_requires_readable_source_both_sides(contract, query, direct_vm):
    resolve(contract, query, direct_vm)
    mock(direct_vm, readable=0)
    assert direct_vm.run_validator() is False

def test_all_sources_fail_no_crash(contract, query, direct_vm, monkeypatch):
    mock(direct_vm)
    def fail(*args, **kwargs):
        raise RuntimeError("Fetch unavailable")
    monkeypatch.setattr(direct_vm, "_match_web_mock", fail)
    contract.resolve_query(query)
    r = json.loads(contract.get_resolution(query))
    assert r["sources_readable"] == 0 and r["status"] == "UNRESOLVABLE"

def test_malformed_llm_json(contract, query, direct_vm):
    r = resolve(contract, query, direct_vm, raw="definitely happened yes!")
    assert r["resolution"] == "INCONCLUSIVE" and r["confidence"] == 0

def test_invalid_resolution_normalized(contract, query, direct_vm):
    assert resolve(contract, query, direct_vm, resolution="MAYBE")["resolution"] == "INCONCLUSIVE"

def test_too_early_confidence_capped(contract, query, direct_vm):
    assert resolve(contract, query, direct_vm, resolution="TOO_EARLY", confidence=95)["confidence"] == 80

def test_inconclusive_confidence_reduced(contract, query, direct_vm):
    assert resolve(contract, query, direct_vm, resolution="INCONCLUSIVE", confidence=90)["confidence"] == 50

def test_evidence_summary_non_list(contract, query, direct_vm):
    assert resolve(contract, query, direct_vm, summary="some string")["evidence_summary"] == "[]"

@pytest.mark.parametrize("description,deadline,category,urls,error", [
    ("", "2026", "FINANCE", URLS, "event_description cannot be empty"),
    ("X", "2026", "WEATHER", URLS, "Invalid category"),
    ("X", "2026", "FINANCE", URLS[:2], "At least 3 source URLs required"),
    ("X", "2026", "FINANCE", URLS + ["https://d.com", "https://e.com", "https://f.com"], "Maximum 5 source URLs"),
    ("X", "2026", "FINANCE", [URLS[0], URLS[0], URLS[2]], "Duplicate"),
    ("X", "2026", "FINANCE", ["not-a-url", URLS[1], URLS[2]], "Invalid URL"),
    ("X" * 501, "2026", "FINANCE", URLS, "exceeds 500"),
    ("X", "", "FINANCE", URLS, "resolution_deadline cannot be empty"),
    ("X", "D" * 51, "FINANCE", URLS, "exceeds 50"),
])
def test_create_validation(contract, direct_vm, description, deadline, category, urls, error):
    with direct_vm.expect_revert(error):
        contract.create_query(description, deadline, category, urls)
    assert contract.get_count() == 0

def test_resolve_already_resolved(contract, query, direct_vm):
    resolve(contract, query, direct_vm)
    mock(direct_vm)
    with direct_vm.expect_revert("not PENDING"):
        contract.resolve_query(query)

def test_resolve_unresolvable(contract, query, direct_vm):
    resolve(contract, query, direct_vm, resolution="INCONCLUSIVE")
    mock(direct_vm)
    with direct_vm.expect_revert("not PENDING"):
        contract.resolve_query(query)

def test_get_resolution_fresh_pending(contract, query, direct_vm):
    with direct_vm.expect_revert("Not yet resolved"):
        contract.get_resolution(query)

def test_get_resolution_after_too_early(contract, query, direct_vm):
    resolve(contract, query, direct_vm, resolution="TOO_EARLY")
    assert json.loads(contract.get_resolution(query))["resolution"] == "TOO_EARLY"

def test_list_queries_filter(contract, direct_vm, direct_alice, direct_bob):
    for sender, result in [(direct_alice, "YES"), (direct_bob, "NO"), (direct_alice, "TOO_EARLY"), (direct_bob, "")]:
        with direct_vm.prank(sender):
            q = contract.create_query("Did X happen?", "2026", "OTHER", URLS)
        if result:
            resolve(contract, q, direct_vm, resolution=result)
    for filt, count in [("YES", 1), ("NO", 1), ("TOO_EARLY", 1), ("PENDING", 2), ("", 4)]:
        assert len(json.loads(contract.list_queries(filt))["queries"]) == count

def test_invalidate_owner_only(contract, query, direct_vm, direct_bob):
    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("Only owner"):
            contract.invalidate_query(query)
    contract.invalidate_query(query)
    r = json.loads(contract.get_query(query))
    assert (r["status"], r["reasoning"]) == ("UNRESOLVABLE", "Invalidated by admin")
    with direct_vm.expect_revert("not PENDING"):
        contract.invalidate_query(query)

def test_all_categories_valid(contract):
    for i, cat in enumerate(["FINANCE", "POLITICS", "SPORTS", "TECH", "SCIENCE", "CRYPTO", "OTHER"]):
        assert contract.create_query("X", "2026", cat, URLS) == str(i + 1)

@pytest.mark.parametrize("method", ["get_query", "get_resolution", "resolve_query", "invalidate_query"])
def test_missing_query(contract, direct_vm, method):
    with direct_vm.expect_revert("Query not found"):
        getattr(contract, method)("999")

@pytest.mark.parametrize("resolution,confidence", [("NO", 98), ("YES", 60)])
def test_validator_disagrees(contract, query, direct_vm, resolution, confidence):
    resolve(contract, query, direct_vm)
    mock(direct_vm, resolution=resolution, confidence=confidence)
    assert direct_vm.run_validator() is False

def test_fabricated_source_count_rejected(contract, query, direct_vm):
    raw = json.dumps({"resolution": "YES", "confidence": 99, "sources_readable": 3})
    assert resolve(contract, query, direct_vm, readable=0, raw=raw)["resolution"] == "INCONCLUSIVE"


def test_illustrative_apollo_example(contract, direct_vm):
    from pathlib import Path
    example = json.loads(Path("evidence/illustrative-example.json").read_text())
    call = example["create_query"]
    qid = contract.create_query(**call)
    direct_vm.clear_mocks()
    for url in call["source_urls"]:
        direct_vm.mock_web(url, {"status": 200, "body":
            "Apollo 11 landed humans on the Moon on July 20, 1969. "
            "Armstrong and Aldrin reached the lunar surface before July 21, 1969."})
    direct_vm.mock_llm(r".*event resolution oracle.*", json.dumps({
        "resolution": "YES", "confidence": 98, "sources_readable": 3,
        "reasoning": "All three supplied mock sources explicitly confirm the July 20, 1969 landing.",
        "evidence_summary": [{"url": u, "readable": True, "relevant": True,
            "key_finding": "July 20, 1969 landing confirmed by supplied mock text"}
            for u in call["source_urls"]]}))
    contract.resolve_query(qid)
    result = json.loads(contract.get_resolution(qid))
    assert qid == "1"
    for key, value in example["expected_verdict"].items():
        assert result[key] == value
    assert direct_vm.run_validator() is True


def test_llm_failure_safe_fallback(contract, query, direct_vm, monkeypatch):
    mock(direct_vm)
    def fail(*args, **kwargs):
        raise RuntimeError("LLM unavailable")
    monkeypatch.setattr(direct_vm, "_match_llm_mock", fail)
    contract.resolve_query(query)
    result = json.loads(contract.get_resolution(query))
    assert (result["resolution"], result["confidence"], result["status"]) == ("INCONCLUSIVE", 0, "UNRESOLVABLE")


@pytest.mark.parametrize("resolution", ["NO", "TOO_EARLY", "INCONCLUSIVE"])
def test_each_different_decision_rejected(contract, query, direct_vm, resolution):
    resolve(contract, query, direct_vm)
    mock(direct_vm, resolution=resolution)
    assert direct_vm.run_validator() is False


def test_same_meaning_different_words_accepted(contract, query, direct_vm):
    resolve(contract, query, direct_vm)
    mock(direct_vm, raw=json.dumps({"resolution": "YES", "confidence": 92,
        "reasoning": "Different wording for the same confirmed event.",
        "sources_readable": 3, "evidence_summary": []}))
    assert direct_vm.run_validator() is True
