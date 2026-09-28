# 01: Drop Amazon order Charges from card imports

**What to build:** When Steven imports any card CSV (including the Amazon card), Charges for Amazon physical Orders are dropped, so the same money is never counted twice once Amazon Items come from Order data (ADR 0001). Other Charges on the same card, such as Whole Foods, Prime membership, Prime Video, Kindle, and Audible, import exactly as they do today. See the spec's "Card import filter" section.

**Blocked by:** None, can start immediately.

**Status:** ready-for-agent

- [ ] Charges whose description starts with `Amazon.com*`, `AMAZON MKTPL*`, or `AMZN Mktp*` (case-insensitive) are dropped for every Account.
- [ ] Refund credits with those descriptors are dropped too.
- [ ] Whole Foods, Prime membership, Prime Video, Kindle, and Audible Charges still import.
- [ ] The per-file summary counts dropped Charges under a clear skipped reason (e.g. "amazon order charge").
- [ ] Tested through the CLI run with the sheet faked: a Chase CSV that has Amazon order Charges and a Whole Foods Charge writes only the Whole Foods row.
- [ ] Existing tests still pass.
