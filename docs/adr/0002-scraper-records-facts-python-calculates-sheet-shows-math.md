# The scraper records facts, Python calculates, and the sheet shows the math

Amazon Order data is scraped by Claude in Chrome, an LLM, which is unreliable at arithmetic. The scraper therefore records only what Amazon shows (prices, Promos, shipment tax, shipping, Order totals, Refunds) into a JSON file and computes nothing. Python calculates each Item's Loaded Cost, including rounding, and checks that an Order's Loaded Costs sum exactly to the Order total Amazon showed. An Order that fails the check is skipped with a warning, never imported with guessed numbers.

Each Item's Amount is written as a formula of rounded dollar amounts in a fixed order (quantity × price, minus Promos, plus tax, plus its share of Adjustments), for example `=2*12.99-3+1.81+0.42`, so anyone reading the sheet can see how the number was built.

## Considered Options

- **The LLM computes Loaded Cost**: one step, but silent arithmetic errors would reach Splitwise.
- **Tax as a rate in the formula** (`=24.99*1.0825`): readable, but wrong for untaxed Items (most groceries in Texas) and it drifts by a cent against Amazon's per-shipment rounding, which would break the total check.
- **A single calculated number in Amount**: simplest, but hides how shared costs were derived.
