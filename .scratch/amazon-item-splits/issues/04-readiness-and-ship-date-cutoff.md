# 04: Readiness and the ship-date cutoff

**What to build:** Only finished, relevant Items reach the sheet. Orders still waiting to ship are held for a later scrape, cancelled Items never appear, and Items that shipped before the Amazon Cutoff Date (2026-07-29, already recorded as Charge rows) are ignored. The cutoff compares the shipment's ship date, so an Order placed before the cutoff but shipped after it is still imported. See the spec's "Readiness" and "Cutoff" bullets.

**Blocked by:** 02 (Tracer bullet: one simple Amazon Order becomes one Item row)

**Status:** done

- [x] An Order is processed only when every non-cancelled Item's shipment has shipped. Otherwise it is skipped with the reason "not ready" and shown in the summary.
- [x] Cancelled Items are dropped and play no part in the tax spread or the total check.
- [x] Items whose shipment ship date is before the Amazon entry's Cutoff Date are skipped and counted in the summary.
- [x] An Order placed before the Cutoff Date but shipped on or after it is imported.
- [x] The CLI's generic cutoff (which compares the row date) is not applied a second time to Amazon rows.
- [x] Tested at the adapter seam (readiness, cancelled Items, the ship-date boundary) and at the CLI seam (no double cutoff).
