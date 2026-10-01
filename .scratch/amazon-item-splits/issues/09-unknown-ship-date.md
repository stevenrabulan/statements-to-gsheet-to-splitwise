# 09: Unknown ship date

**What to build:** A shipped shipment with no ship date no longer stops the import. The Order Date stands in for the cutoff comparison, and Steven can see where that happened. See spec addendum decisions 2 and 3.

**Blocked by:** 08

**Status:** resolved

- [x] A shipped shipment may have `ship_date: null`. The cutoff then compares the Order Date.
- [x] Order Date on or after the Cutoff Date: the Items are imported. Each row's Notes end with ` (ship date unknown, Order Date used for cutoff)` after the key, and a warning names the Order.
- [x] Order Date before the Cutoff Date: the Items in that shipment are skipped under "unknown ship date", each with a warning naming the Order and the Item.
- [x] Deduplication by key still matches a row that carries the Notes suffix.
- [x] A Refund on an Item with no ship date uses the same fallback for its cutoff check.
- [x] Adapter-seam tests cover both sides of the cutoff and the Refund case. A CLI-seam test checks the Notes cell and that a re-scrape writes nothing.

## Comments

- 2026-10-01 Open question: Order with several shipments where only some lack a ship date. Went with: the fallback applies per shipment, so each Item is judged by its own shipment's date (or the Order Date when that is null); only Items that used the fallback get the Notes suffix or the "unknown ship date" skip. Why: matches how the cutoff is already per shipment.
- 2026-10-01 Open question: how many warnings for the fallback. Went with: one per Item for imported rows (names the Order and position), one per Order for the skip case. Why: spec asks for "a warning that names the Order" for each; per-Item on import tells Steven which rows carry the suffix.
- 2026-10-01 Review follow-up: the skip is per Item, not per Order. Criterion 3 and spec decision 3 reworded to match, and the skip warning now names the Item (`#n ... Item skipped`), one per dropped Item, replacing the one-per-Order "Order skipped" text. Why: Amazon charges per shipment, so an Order's other shipments can still import, and "Order skipped" was false for them.
- 2026-10-01 Open question: a Refund that used the Order Date fallback and is imported. Went with: no extra warning and no Notes suffix on the Refund row; a skipped Refund warns and says the Order Date was used. Why: the ticket only asks for the same cutoff fallback; a Refund row's own date is the refund date, so the suffix would not describe it.
- 2026-10-01 Open question: how to carry the Notes suffix without breaking dedup. Went with: a new `Transaction.note_suffix` appended after `key` in the column K note; `key` itself stays pure. Why: dedup and Refund classification match on the key as a whole word, which a trailing suffix does not disturb.
- 2026-10-01 Review follow-up: a shipment with no `ship_date` field at all was treated like `ship_date: null`. The importer now fails loudly, naming the Order, as it already does for a missing `tax`. Why: `null` means Amazon shows no ship date; a missing field means the scrape dropped it, and the Order Date fallback would hide that.
