# EventVerdict

EventVerdict dies without GenLayer: no EVM contract can read a Federal Reserve press release and a Reuters article on-chain, reason about whether a specific real-world event occurred, and produce a multi-validator consensus resolution — only GenLayer's AI validators can fetch live evidence during consensus and deliver a tamper-proof, auditable oracle for prediction market resolution.

## Problem

Prediction markets rely on centralized or human oracles that introduce trust, delay, expense, subjective decisions, and opaque reasoning.

## Solution

EventVerdict reads 3–5 public evidence URLs during GenLayer consensus and asks AI validators to resolve a precise event. It stores the outcome, confidence, reasoning, readable-source count, and a JSON evidence summary on-chain. No frontend or token payments are required.

## How it works

1. Call `create_query(event_description, resolution_deadline, category, source_urls)`; save the returned string ID. Descriptions are limited to 500 characters, deadlines to 50, and URLs must be distinct HTTP(S) URLs.
2. Anyone calls `resolve_query(query_id)`. Each validator independently fetches the captured URLs and evaluates only their evidence; no contract storage is read inside nondeterministic closures.
3. Read `get_query(query_id)` or `get_resolution(query_id)` for a JSON object. `evidence_summary` is itself a JSON-encoded array. A fresh pending query raises `Not yet resolved` from `get_resolution`.
4. If the result is `TOO_EARLY`, retry `resolve_query` later. The previous attempt remains visible through `get_resolution` while status remains `PENDING`.

## Resolution states and status flow

| Resolution | Meaning | Status | Retry |
| --- | --- | --- | --- |
| YES | Event occurred, explicitly confirmed by 2+ readable sources | RESOLVED | No |
| NO | Event did not occur and deadline passed, supported by evidence | RESOLVED | No |
| TOO_EARLY | Source date context clearly places the deadline in the future | PENDING | Yes |
| INCONCLUSIVE | Insufficient readable sources, contradictory evidence, or ambiguous evidence | UNRESOLVABLE | No |

Both YES and NO require at least two actually readable sources. Each URL must return more than 30 non-whitespace characters to count. Up to 3,000 characters per readable source are passed to the model. Deadline interpretation relies on dates in the evidence, rather than a deterministic calendar gate. The model is instructed to return INCONCLUSIVE when fewer than two sources are readable; the deterministic source threshold specifically overrides YES and NO.

`TOO_EARLY` is deliberately retryable. Final outcomes cannot be resolved again. The deploying owner can invalidate a pending query, including one with an earlier TOO_EARLY attempt; status becomes UNRESOLVABLE and reasoning becomes `Invalidated by admin`. Earlier attempt fields remain available.

## Consensus design

Consensus agrees on the **meaning of the decision**, not JSON format: a validator independently determines YES, NO, TOO_EARLY, or INCONCLUSIVE for the same event. A different decision is rejected even if it has perfectly valid JSON. Identical wording is not required.

The validator first requires `gl.vm.Return` and reads its `.calldata`. It independently repeats evidence fetching and inference. Resolution must match exactly. For YES/NO, both sides must report at least one readable source; normal leader normalization already enforces the stricter two-source threshold. Confidence must occupy the same band: 0–34, 35–79, or 80–100. Evidence wording and exact confidence need not match. This equivalence rule does not prove that sources are independent or truthful.

Leader consistency rules:

- Count actual successful readable fetches; ignore any model-invented source count. YES/NO with fewer than two sources becomes INCONCLUSIVE and confidence loses 20 points before the uncertainty cap.
- Clamp confidence to 0–100; invalid confidence becomes zero.
- Cap TOO_EARLY confidence at 80.
- Cap INCONCLUSIVE confidence at 50, resolving the prompt's inconsistent 50/60 wording conservatively.
- Serialize sanitized evidence objects before storage. Non-list summaries become `[]`.

## API

Writes: `create_query(...) -> str`, `resolve_query(query_id)`, `invalidate_query(query_id)`.

Views: `get_query(query_id)` returns full details; `get_resolution(query_id)` omits creator and source URL inputs. `list_queries(resolution_filter)` returns `{"queries": [...]}` with compact entries in numeric creation order. Filters: empty string, PENDING, YES, NO, TOO_EARLY, INCONCLUSIVE, UNRESOLVABLE. PENDING includes fresh and TOO_EARLY queries; UNRESOLVABLE matches status. `get_count() -> int` is the specified scalar exception to JSON view returns.

Supported categories: FINANCE, POLITICS, SPORTS, TECH, SCIENCE, CRYPTO, OTHER.

## Use cases

Prediction market settlement, DAO conditional treasury release, options settlement oracles, and event-triggered escrow. Downstream contracts should check final status and resolution before acting.

## Edge cases

Every source fetch has its own exception handler, allowing other sources to proceed after failures. Empty/short pages do not count. Contradictory sources are explicitly classified INCONCLUSIVE by the model instructions. Malformed JSON, non-object responses, and failed LLM calls safely produce INCONCLUSIVE with zero confidence. Unknown resolutions normalize to INCONCLUSIVE. Fenced JSON is accepted. The supplied evidence summary is sanitized but not independently verified against fetched text; the count is verified by actual fetching. Mock tests verify mechanics, not the real model's factual accuracy or resistance to hostile source text.

## Run tests

Requires Python 3.12+:

```sh
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
gltest tests/ -v
```

Direct-mode tests use the installed genlayer-test fixtures and mocked web/LLM calls; no Studio node is needed. `tests/conftest.py` contains a narrowly scoped Windows workaround for the published genlayer-test 0.29.2 wheel: temporary-message-file deletion is deferred until stdin is released. It does not suppress contract exceptions or alter consensus checks.

Latest fresh-venv run: **44 passed in 3.71s**, using Python 3.12.10, pytest 9.2.0, and genlayer-test 0.29.2. [Full output](evidence/test-results.txt).

The suite covers all 28 requested scenarios, with parameterized input validation and additional checks for missing IDs, actual source counts, and validator disagreements. Direct mode is not a substitute for GenVM deployment and live multi-validator integration testing.

## Deploy to GenLayer Studio (studionet)

1. Open [GenLayer Studio](https://studio.genlayer.com/) and connect the account that should own administrative invalidation.
2. Select the studionet environment and create a Python intelligent contract. Paste `contracts/event_verdict.py` unchanged, including the pinned SDK header.
3. Deploy class `Contract` with no constructor arguments. Save the resulting address after confirming deployment succeeded.
4. Create a query with 3–5 accessible public sources; call `resolve_query`, then inspect `get_resolution` and its evidence. Verify consensus and the TOO_EARLY retry flow in Studio before connecting settlement logic.

## Deployment

```text
CONTRACT_ADDRESS = 0x350DC22Bcd5979C5aFf042A4aBA8D300e1381211
NETWORK = studionet
```

The owner reported this deployment. Address-only verification against the [documented Studionet RPC](https://docs.genlayer.com/developers/networks) returned HTTP 403 for both chain ID and deployed schema on November 2, 2026; see [recorded checks](evidence/deployment-check.json). No successful live call or transaction receipt is claimed.

Source provenance: the original workspace used class `EventVerdict`, a Seq dependency header, and u256 confidence/source-count storage. This submission source uses class `Contract`, the requested three-line header, and bigint persisted numbers. Its behavior passes local tests, but equality with the already deployed source has **not** been verified. Do not treat this repository as verified source for that address until the deployed source is compared or this revision is redeployed. Remote validation of local source was not performed.

### Illustrative worked example (mocked, not a live-chain verdict)

Input on a fresh contract:

```python
query_id = contract.create_query(
    "Did Apollo 11 land humans on the Moon by July 21, 1969?",
    "1969-07-21",
    "SCIENCE",
    [
        "https://www.nasa.gov/mission/apollo-11/",
        "https://en.wikipedia.org/wiki/Apollo_11",
        "https://www.britannica.com/topic/Apollo-11",
    ],
)
contract.resolve_query(query_id)
result = contract.get_resolution(query_id)
```

Expected output excerpt, also confirmed in local mocked execution:

```json
{"query_id":"1","resolution":"YES","confidence":98,"sources_readable":3,"status":"RESOLVED"}
```

`test_illustrative_apollo_example` executes this public API sequence with explicitly fabricated web responses confirming the landing and a mocked LLM response. It asserts the output and validator acceptance. These URLs were not fetched live for the example; confidence 98 is supplied by the mock, not measured. Actual live output depends on fetched evidence and validator consensus. The complete view also contains the description, deadline, category, reasoning, and JSON-string evidence summary. [Machine-readable example](evidence/illustrative-example.json).

## Portal readiness review

- **Semantic validator: passes the key design criterion.** Independent inference must reach the same decision and confidence band; tests reject differing decisions and accept the same meaning with different wording. This does not establish real-world factual correctness.
- **State: clear.** TreeMap[str, EventQuery], DynArray[str], bigint persisted numbers, storage-enabled dataclass, explicit pending/final lifecycle. No frontend.
- **Input/lifecycle errors:** empty and oversized text, invalid category/URL count/duplicates, missing IDs, unauthorized invalidation, and repeat final processing raise UserError. Individual web failures and LLM/JSON failures deliberately yield safe INCONCLUSIVE results instead of reverting.
- **Reusable primitive:** arbitrary natural-language events and sources across seven categories can serve prediction-market settlement, DAO releases, and event-triggered escrow.
- **Known limits:** source accessibility is not source independence or truth; source text can contain prompt injection. The deterministic code enforces two readable pages, not two independently verified confirmations. Evidence-summary URLs, flags, completeness, and claims are model-generated and sanitized but not matched against fetch results. The owner requested preserving this behavior for this submission. INCONCLUSIVE is final even after transient outages; admin invalidation preserves previous attempt fields. Deadlines rely on source context. Listing scans all queries and is unpaginated.
- **Minimal safe improvements applied:** required header/class/storage normalization, targeted Windows test compatibility, reproducible example, explicit semantic disagreement tests, deployment provenance, and documented limits. No further public-behavior changes were applied. Future summary verification or prompt hardening needs a separately approved revision and redeployment.


SDK/testing reference: [GenLayer direct-mode documentation](https://docs.genlayer.com/api-references/genlayer-test/direct).
