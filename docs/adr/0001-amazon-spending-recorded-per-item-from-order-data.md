# Amazon spending is recorded per Item from Order data, not from card Charges

Amazon card Charges don't name what was bought, and Amazon posts one Charge per shipment, so a Charge can't be split by Item. We record Amazon spending as one sheet row per Item, built from scraped Order data, and we drop Amazon physical-order Charges (`Amazon.com*`, `AMAZON MKTPL*`, `AMZN Mktp*`) from every card import so the same money is never counted twice. Non-order Charges on the same card (Whole Foods, Prime, Kindle, Audible) still import as normal Charge rows.

## Considered Options

- **Charge rows enriched with Item details**: amounts match the statement, but mapping shipments to Orders is unreliable, and splitting part of a Charge still needs a manual formula.
- **One row per Order**: still hides which Items are Shared.

## Consequences

- Nothing reconciles Order totals against card Charges any more. Correctness depends on the scrape and on the per-Order total check in ADR 0002. Steven chose not to build a Charge reconciliation because he no longer imports the Amazon card's Amazon Charges.
- Amazon Items that shipped before the Cutoff Date (2026-07-29) were recorded as Charge rows. Refunds against those Orders can't find an Item row and are skipped with a warning.
- A card import that ever needs Amazon order Charges back would have to remove this filter.
