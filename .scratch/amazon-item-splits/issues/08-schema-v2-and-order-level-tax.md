# 08: Schema version 2 and Order-level tax

**What to build:** A scraped file in schema version 2 imports, and a multi-shipment Order whose tax Amazon shows only once for the whole Order gets that tax spread across all its Items. This is the tracer for version 2: every Order carries `kind`, and `physical` Orders behave as today. See spec addendum decisions 1, 5, and 12 and "Schema version 2".

**Blocked by:** none

**Status:** resolved

- [ ] The importer accepts only `schema_version` 2. A version 1 file fails with the existing version error.
- [ ] Every Order needs `kind`. An unknown or missing `kind` is an error naming the Order.
- [ ] When a shipment's `tax` is `null`, the Order's `tax` is spread across all the Order's non-cancelled Items (every shipment) in proportion to price after Promos, leftover cent to the largest part.
- [ ] Per-Item tax and per-shipment tax still win when shown. Both `null` means tax 0, and the total check decides.
- [ ] The sample fixture and existing tests move to version 2.
- [ ] Adapter-seam tests: Order-level tax across two shipments, the rounding remainder, a mix of per-Item tax and Order-level tax, and the version 1 rejection.
