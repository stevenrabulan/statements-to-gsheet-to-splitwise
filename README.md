# Split Transactions

Turns spending from bank, card, and Amazon order data into rows on the "Split payments" sheet, which feeds Splitwise.

Drop your **real account exports** (CSV or PDF statements, plus scraped Amazon Orders as JSON) into `transactions/` to organize and import them. Everything in that folder is **gitignored**. Real financial records are never committed to version control.

(Synthetic test data lives separately under `tests/fixtures/` and is safe to commit.)

**The pipeline has three parts:**

1. **This importer** (Python) reads the exports and appends rows to the sheet.
2. **The Google Sheet** is where each row gets classified: who it is for, and whether it goes to Splitwise. [Make your own copy of the template sheet](https://docs.google.com/spreadsheets/d/1XgqbbwzcgJeNHiM9I2AZKugZTXbdulhn9SlL1yVoU0Y/copy). It holds sample rows imported from `tests/fixtures/`.
3. **A Make.com scenario** sends ticked rows to Splitwise. See [From the sheet to Splitwise](#from-the-sheet-to-splitwise).

---

## Layout: One Folder per Month

To keep files organized, create `transactions/` in the project root (a fresh clone does not have it) with a subfolder for each month:

```
transactions/
  2026-06/
    Chase1111_Activity20260416_20260515_20260623.CSV
    Chase8842_Activity20260416_20260515_20260623.CSV
    Discover_Activity20260416_20260515_20260623.CSV
    Fakecoin Card.csv
  2026-07/
    ...
```

---

## First-Time Setup & Prerequisites

Before running the import script for the first time, complete these setup steps in the project root:

### 1. Configure the Python Virtual Environment
Always use the virtual environment's Python binary to run the tool (the system Python version may be too old and crash on modern syntax).
```bash
# Setup the virtual environment (if not already done)
python3 -m venv .venv

# Install required dependencies
.venv/bin/pip install -r requirements.txt
```

### 2. Configure `accounts.json`
You do not need to rename your bank statement files. Instead, create an `accounts.json` file in the project root (gitignored) to map a **distinctive substring of the filename** to the account label shown in Google Sheets (Column G):

```bash
cp accounts.example.json accounts.json
```

Then edit `accounts.json`. For example:
```json
{
  "Chase1111": "Chase Sapphire Reserve",
  "Chase8842": "Chase Checking",
  "Discover":  "Discover Card",
  "Fakecoin":  "Fakecoin Card"
}
```
*Note: Longest matching key wins. In the example above, a filename containing `Chase1111` will map to `"Chase Sapphire Reserve"`.*

#### Per-account settings (optional)

Some cards (FakeMart, for example) export your **entire** transaction history on every download, not just the current statement period. To ignore everything before the date you started tracking that card, replace the plain string with an object:

```json
{
  "Chase1111": "Chase Sapphire Reserve",
  "FakeMart": {
    "name": "FakeMart Card",
    "ignore_before": "2026-06-01"
  }
}
```

| Setting         | Required | Description                                                                                      |
| :----------------| :---------| :-------------------------------------------------------------------------------------------------|
| `name`          | Yes      | The account label written to Column G, the same as the plain-string form.                      |
| `ignore_before` | No       | `YYYY-MM-DD`. Transactions dated **before** this day are dropped. The cutoff day itself is kept. |

Dropped rows are reported in the per-file summary (e.g. `skipped={'before 2026-06-01': 25}`), so you can always see how many were filtered. The cutoff is applied before deduplication, and `--account` overrides the label only. It does not disable a matched account's cutoff.

#### Which Google Sheet to write to (required)

The `_sheet` entry names the sheet and tab. It is not an account, and the importer stops with an error if it is missing:

```json
{
  "_sheet": {
    "spreadsheet_id": "YOUR_SPREADSHEET_ID",
    "gid": 0
  }
}
```

Both values are in the sheet's URL: `https://docs.google.com/spreadsheets/d/<spreadsheet_id>/edit?gid=<gid>`.

### 3. Add Google Cloud Credentials
1. Go to the [Google Cloud Console](https://console.cloud.google.com) and create a project.
2. Enable the **Google Sheets API**.
3. Go to **APIs & Services** → **Credentials** and click **Create Credentials** → **OAuth client ID** (select **Desktop app**).
4. Download the credentials as `credentials.json` and save them to the project root directory.
5. On the first run, the script will open your browser to authorize access. It will save a `token.json` file for future runs.

---

## How to Run the Import

### 1. Perform a Dry Run (Recommended)
Always preview changes before writing to the Google Sheet. A dry-run parses the files, performs duplicate checks, and outputs a summary of what *would* be appended, without writing anything to the sheet or updating the import log.

```bash
.venv/bin/python main.py transactions/2026-06/ --dry-run
```

### 2. Perform the Actual Import
Run the script without the `--dry-run` flag to import all new transactions:

```bash
.venv/bin/python main.py transactions/2026-06/
```

### 3. Import Specific Files
You can also pass individual files instead of entire directories:

```bash
.venv/bin/python main.py transactions/2026-06/Fakecoin\ Card.csv
```

---

## Amazon Orders

Amazon spending is recorded **one sheet row per Item**, not from card Charges. Amazon posts one Charge per shipment (`AMAZON MKTPL*...`), which says nothing about what was bought, so card imports drop those Charges and Item rows come from scraped Order data instead. See `docs/adr/0001-*` and `docs/adr/0002-*`.

### 1. Config entry

Add an Amazon entry to `accounts.json` (see `accounts.example.json`):

```json
"amazon-orders": {
  "name": "Amazon",
  "ignore_before": "2026-07-29"
}
```

| Setting         | Description                                                                                                                                  |
| :----------------| :---------------------------------------------------------------------------------------------------------------------------------------------|
| key             | Must be contained in the scraped filename. `amazon-orders` matches `amazon-orders-2026-09-28.json`.                                          |
| `name`          | Fallback Payment Method (Column G), used only when an Order's card last four digits match no other `accounts.json` key (a warning is shown). |
| `ignore_before` | The **Cutoff Date**. Items whose shipment **ship date** is before it are ignored (Orders before it were recorded as Charge rows). Compared with the ship date, not the Order Date (see "What gets a row"). |

Payment Method is set from the card on the Order: its last four digits are matched against `accounts.json` keys that contain them (e.g. key `Chase1111` for a card ending 1111). Gift card only gives "Amazon Gift Card", points only gives "Points", gift card plus card gives the card.

### 2. Scrape, then import (once per billing cycle)

The scrape runs from **Claude Code**, which drives your logged-in Chrome through the Claude in Chrome extension and writes the file straight into the month's folder.

1. Open Chrome, logged in to your own Amazon account, with the Claude in Chrome extension connected.
2. Start Claude Code in this repo and tell it to follow `scrape-amazon-orders.md`.
3. It walks the last 90 days of the Orders list, reads the Digital Orders tab, and saves `amazon-orders-<run date>.json` into the current month's folder, e.g. `transactions/2026-10/`. It records what Amazon shows and calculates nothing.
4. In the same session it runs the dry run, `.venv/bin/python main.py transactions/2026-10/ --dry-run`, and reports the file's path, the counts, anything it could not read, and every warning.
5. Read the dry-run report. When it looks right, import (same command without `--dry-run`; the folder import picks up `.json` alongside CSVs and PDFs):

```bash
.venv/bin/python main.py transactions/2026-10/
```

The importer calculates each Item's Loaded Cost (price, minus Promos, plus tax, plus shipping and whole-Order discount shares) and writes it as a formula in Amount, e.g. `=2*12.99-3+1.81+0.42`. `--dry-run`, `--from`/`--to`, `--force`, and the import log work as for cards.

**If the Chrome connection fails:** open the Claude in Chrome side panel in the logged-in window, paste the prompt from `scrape-amazon-orders.md` (everything under "Prompt"), and ask it to offer the file as a download named `amazon-orders-<run date>.json`. The side panel cannot write into the repo. Move the download into the month's folder with one command, then run the dry run:

```bash
mv ~/Downloads/amazon-orders-2026-10-01.json transactions/2026-10/
.venv/bin/python main.py transactions/2026-10/ --dry-run
```

#### What gets a row

| Amazon Order | Rows | Date (Column A) | Cutoff compared with |
| :--- | :--- | :--- | :--- |
| Physical Order | one per Item | Order Date | the shipment's ship date |
| Whole Foods Order | one for the whole Order, named `Whole Foods` | Order Date | Order Date |
| Digital Order (Digital Orders tab, e.g. `Grocery Subscription`) | one, named for what was bought | date charged | date charged |

- **Whole Foods:** Amount is a formula of the summary lines Amazon shows, e.g. `=106.99+7` (subtotal plus driver tip). It must equal the Order Total or the Order is skipped with a warning. It is imported once delivered. The scrape finds these by walking the Orders list, because the search box skips them.
- **Digital Orders:** Amount is the amount Amazon shows. The card comes from each Order's details page.
- **Order Total** is the total before any gift card or points, not the "Grand Total" after them. How an Order was paid never changes its cost.
- **Only your own account** is read. Orders from another account are never recorded.

#### Unknown ship date

Amazon shows no "shipped" date. The scrape uses the date of the "Package left the shipper facility" tracking event, and leaves it blank when the tracking is gone. With no ship date, the **Order Date** stands in for the cutoff check only:
- Order Date on or after the Cutoff Date: the Items import, each with a warning in the run output and ` (ship date unknown, Order Date used for cutoff)` after the key in Notes. Column A is the Order Date either way.
- Order Date before the Cutoff Date: the Items in that shipment are skipped (`unknown ship date`), each with a warning. Items in the Order's other shipments still import.

#### Reading the dry-run summary

The summary counts what the import left out:
- `not ready`: an Order with a non-cancelled Item not shipped yet (or a Whole Foods Order not delivered). It is picked up on a later scrape.
- `total mismatch`: calculated costs did not equal the Order Total. The Order is skipped with a warning naming the expected and calculated totals.
- `before <Cutoff Date>`: Items (or Whole Foods and Digital Orders) dated before the Cutoff Date.
- `unknown ship date`: see above.
- `refund before <Cutoff Date>`, `refund without item`, `refund on Digital Order`, `refund on total mismatch` (a Refund covering several Items on an Order that fails the total check, so it cannot be split): a Refund left out, with a warning naming the Order and amount. Enter it by hand.

Warnings to expect: a discount Amazon shows with no Items it applies to is spread across every Item as a discount (a warning names the Order and amount); a card that matches no `accounts.json` key falls back to the Amazon entry's name.

#### Keys and Refunds

Rows are deduplicated by a key in Notes (Column K): `split-transactions automation amazon <order number> <ASIN>` for an Item (the product code from its Amazon link; a second Item with the same ASIN in one Order ends `#2`), `split-transactions automation amazon <order number>` for a Whole Foods or Digital Order. Re-scraping never duplicates rows.

Returns and partial refunds arrive on a later scrape as **negative rows** dated on the refund date. They copy "Send to Splitwise" and "For who" from the original row. One Refund that covers several Items becomes one negative row per Item, split in proportion to their Loaded Costs. A Whole Foods Refund is one negative row, `Refund: Whole Foods`. A Refund on a Digital Order is skipped (enter it by hand).

### 3. What is not imported from Amazon

- **The Amazon card is no longer imported.** Do not import its CSV for Amazon spending: Orders, Whole Foods, and Digital Orders come from the scrape.
- **Enter by hand:** the **Prime fee** (yearly; Amazon shows no charge history for it) and **Audible** (separate sign-in).
- **Safety net:** when importing any other card or bank CSV or PDF, Charges (and refund credits) starting with `Amazon.com*`, `AMAZON MKTPL*`, or `AMZN Mktp*` are still dropped, so Orders are counted once. The per-file summary shows them as `amazon order charge`.

### 4. Classify rows in the sheet

New Amazon rows default to **Shared** (Column E "Send to Splitwise" ticked, "For who" as card rows get). After importing:
- **Personal** Item: untick "Send to Splitwise" (E). The row stays recorded so you can reclassify later.
- **Partner's** Item: set "For who" (H) to Partner 2 (the template sheet calls the two people Partner 1 and Partner 2).

---

## From the Sheet to Splitwise

The importer never talks to Splitwise. A [Make.com](https://www.make.com) scenario does, on a schedule. Its blueprint is in [`make/splitwise-sync.blueprint.json`](make/splitwise-sync.blueprint.json).

On each run the scenario:

1. Reads cell `M2`, the last row it sent.
2. Finds rows with "Send to Splitwise" (E) ticked and "Done" (F) unticked, oldest Order Date first, up to 200.
3. Skips rows with "Exclude" (D) ticked, and rows more than 30 rows before the row in `M2`. Old rows that were never sent stay unsent.
4. Creates one Splitwise expense per row in a fixed group: Item (C) as the description, Notes (K) in the details.
5. Ticks "Done" (F) on the row and writes its row number to `M2`.

**How "For who" changes the expense:**

| "For who" (H) | Cost sent to Splitwise | Module settings |
| :--- | :--- | :--- |
| Partner 2 | Amount (B) doubled | `split_equally` off, `payment` on |
| Anything else | Amount (B) | `split_equally` on, `payment` off |

Doubling is a workaround: it is how the scenario gets Splitwise to charge Partner 2 the full amount. The expense details say so, since the cost shown in Splitwise is not the real price.

### Use the blueprint

1. In Make.com, create a scenario, open the `...` menu, and choose **Import Blueprint**.
2. On each module, pick your own Google and Splitwise connections.
3. Replace `YOUR_SPREADSHEET_ID` on the four Google Sheets modules and choose your Splitwise group on the "Create an Expense" module.
4. Set a schedule. The blueprint does not carry one.

---

## Command Line Arguments & Options

| Flag / Option       | Description                                                                                                   | Example                      |
| :--------------------| :--------------------------------------------------------------------------------------------------------------| :-----------------------------|
| `--dry-run`         | Preview the import in the console. Does not write to Google Sheets or log files.                              | `--dry-run`                  |
| `--force`           | Force reprocessing of files that have already been imported (overrides the import log check).                 | `--force`                    |
| `--from YYYY-MM-DD` | Only import transactions dated on or after the specified date.                                                | `--from 2026-06-01`          |
| `--to YYYY-MM-DD`   | Only import transactions dated on or before the specified date.                                               | `--to 2026-06-30`            |
| `--account "NAME"`  | Manually set/override the sheet's account label (Column G). Use with single files.                            | `--account "Chase Checking"` |
| `--source ADAPTER`  | Force the use of a specific parser adapter (`fakecoin`, `discover`, `chase_checking`, `chase_credit`, `fakemart_credit`, `amazon`, `pdf`). | `--source fakecoin`          |
| `--year YYYY`       | Specify the calendar year for PDF statements (as credit card PDFs often omit the year on transaction lines).  | `--year 2026`                |

---

## How Safe Re-runs Work (Idempotency)

The tool uses two layers of protection to prevent duplicate transactions:

1. **File-Level Deduplication (Content Hash):**
   Every imported file is hashed (SHA-256) and recorded in `import_log.json`. If you run the import on a file that has already been processed, it is skipped entirely unless you pass the `--force` flag.
2. **Row-Level Deduplication:**
   When importing, the script reads all existing rows in the Google Sheet (Columns A to K). It performs multiset matching on `(date, amount, normalized_description, normalized_account)`. This ensures that even if you re-export a spreadsheet that contains older transactions, only the *newly added* ones are appended to your sheet. Genuine duplicate transactions of the same amount on the same day are fully preserved.

---

## Running Tests

Verify that your installation is working correctly by running the test suite:

```bash
.venv/bin/python -m pytest -q
```
