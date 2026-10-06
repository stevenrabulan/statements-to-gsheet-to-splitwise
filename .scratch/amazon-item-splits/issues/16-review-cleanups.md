# 16: Review cleanups

**What to build:** Six code-quality cleanups left over from the code review of tickets 09 to 14 (2026-10-01). None changes behaviour: every test that passes before must pass after, with no test edited except for renames. Does not block ticket 15.

**Blocked by:** none

**Status:** done

All line numbers are for `adapters/amazon.py` at commit `4290d99` unless another file is named.

- [x] **Duplicated code in the three one-row parsers.** `_parse_whole_foods`, `_parse_digital`, and `_parse_whole_foods_refund` each repeat the cutoff comparison, the `_payment_method` call, and the "append the warning if there is one" tail. Extract the shared shape. The `amount <= 0` check appears at lines 279 and 336: fold it into `_refund_amount_and_date`.
- [x] **A type for the cutoff date.** The pair `(shipped_on, known)` travels together at lines 290, 396, and 482, and inside `tuple[str, date, bool]` at line 386. Give it a small type, for example `CutoffDate(date, is_ship_date)`.
- [x] **One dispatch on `kind`.** The Order parse (lines 105 to 109) and the Refund parse (lines 255 to 258) each branch on `kind`. Use one map from kind to its handlers, shared by both.
- [x] **Names that do not say what they hold.**
  - Line 45: `UNKNOWN_SHIP_DATE` is the skip reason, next to `UNKNOWN_SHIP_DATE_NOTE`. Name it as a skip reason.
  - Line 229: `_lines` returns the dollar amounts of an Order's summary lines.
  - Line 352: `row = order_key(...)` holds a key, not a row.
  - Line 56: `refund_key(item=...)` also takes a Whole Foods Order key.
- [x] **`sheets_writer.py:39` drops `note_suffix` silently when a row has no key.** `(txn.key + txn.note_suffix) if txn.key else txn.source_file`. Assert that a suffix implies a key, so a future caller cannot lose one unnoticed.
- [x] **`dedup.py` docstring of `amazon_classifications`.** It says "The first row wins if an Item appears twice", but the map also holds Whole Foods Order keys. Reword to cover both.

## Comments

- 2026-10-01: Written at the end of the review session so the list survives it. The review's other findings are already fixed in commits `869962f` to `4290d99`, each with a "Review follow-up" comment in its ticket.
- 2026-10-01: Left out on purpose: "savings" and "coupons" in `scrape-amazon-orders.md` (lines 57, 113, 199). CONTEXT.md avoids both words, but there they describe the labels Amazon's own pages show, which the scraper has to recognize.
- 2026-10-06: Done. Two deliberate deviations from "no behaviour change":
  - Folding `amount <= 0` into `_refund_amount_and_date` means a zero or negative Refund on a Digital Order, or on an Order missing from the file, now raises `ImporterError` instead of skipping with a warning. No test pins it.
  - `_payment_account` dedupes the payment warning on every path (before, only Refund paths did). Warning text includes the order number, so it only matters for a repeated order.
  - The cutoff-date type is `_ComparedDate`, not `CutoffDate`: CONTEXT.md defines Cutoff Date as the threshold (`ignore_before`), not the date compared against it.
  - Added one test (`test_build_row_refuses_a_note_suffix_without_a_key`) for the new assert.
