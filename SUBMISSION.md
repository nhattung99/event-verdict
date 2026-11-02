# Portal submission draft

Track: Builder

Contribution type: Intelligent Contracts

Title: EventVerdict - Multi-Source Event Resolution Oracle

Description (879 characters):

EventVerdict is a standalone event-resolution oracle: it reads 3-5 public evidence sources and records YES, NO, TOO_EARLY, or INCONCLUSIVE with reasoning and an evidence summary. TOO_EARLY remains retryable. GenLayer validators independently fetch evidence and infer an outcome; the custom validator agrees on the MEANING of the decision, not JSON format. Different decisions fail validation, with readable-source checks and confidence banding. The primitive supports prediction-market settlement, DAO conditional treasury releases, and event-triggered escrow across seven categories. It ships with API/consensus docs and 44 passing tests, including semantic disagreement and retry coverage. Reported deployment on studionet: 0x350DC22Bcd5979C5aFf042A4aBA8D300e1381211. Live verification returned HTTP 403; the repo documents source-provenance limits and a mocked worked example.

Evidence URL: https://github.com/nhattung99/event-verdict

Paste the GitHub URL in the Evidence field. Submit it yourself at https://portal.genlayer.foundation (Builder -> Intelligent Contracts), after ticking the reCAPTCHA.

Before submission, compare the deployed source with this revision or redeploy it: the reported address has not been verified as matching the updated class/header/storage types. No live verdict is claimed.
