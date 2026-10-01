# 09: Unknown ship date

**What to build:** A shipped shipment with no ship date no longer stops the import. The Order Date stands in for the cutoff comparison, and Steven can see where that happened. See spec addendum decisions 2 and 3.

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] A shipped shipment may have `ship_date: null`. The cutoff then compares the Order Date.
- [ ] Order Date on or after the Cutoff Date: the Items are imported. Each row's Notes end with ` (ship date unknown, Order Date used for cutoff)` after the key, and a warning names the Order.
- [ ] Order Date before the Cutoff Date: the Order is skipped under "unknown ship date" with a warning naming the Order.
- [ ] Deduplication by key still matches a row that carries the Notes suffix.
- [ ] A Refund on an Item with no ship date uses the same fallback for its cutoff check.
- [ ] Adapter-seam tests cover both sides of the cutoff and the Refund case. A CLI-seam test checks the Notes cell and that a re-scrape writes nothing.
