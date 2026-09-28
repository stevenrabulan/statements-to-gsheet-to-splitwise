# 06: Scrape prompt and docs

**What to build:** Steven has one Claude in Chrome prompt in this repo that he runs manually once per billing cycle. It reads the last 90 days of Amazon Orders and saves raw facts in the scraped-file contract into the month's transactions folder, ready to import. It replaces the old order-total prompt. The README explains the whole Amazon workflow. See the spec's "Scrape prompt" and "Configuration" sections and ADR 0002.

**Blocked by:** 02 (Tracer bullet: one simple Amazon Order becomes one Item row)

**Status:** ready-for-agent

- [ ] The prompt covers Orders from the last 90 days and opens each Order's details or invoice page.
- [ ] It records exactly the fields in the scraped-file contract (including the schema version) and states plainly that it must not total, allocate, or round anything.
- [ ] It records the full title and a short name for every Item: the brand plus a plain description, in normal case, with no made-up abbreviations.
- [ ] It writes one file per run to the current month's transactions folder, with a filename containing the Amazon accounts-config key (e.g. `amazon-orders-<run date>.json`).
- [ ] The old order-total prompt is removed.
- [ ] The README documents the Amazon config entry and Cutoff Date, the scrape-then-import workflow, the card filter, and how to classify Items in the sheet.
