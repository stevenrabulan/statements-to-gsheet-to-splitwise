# transactions/

Drop your **real account exports** (CSV or PDF statements, plus scraped Amazon Orders as JSON) here to organize and import them. Everything in this folder is **gitignored** except this README. Real financial records are never committed to version control.

(Synthetic test data lives separately under `tests/fixtures/` and is safe to commit.)

---

## Layout: One Folder per Month

To keep files organized, create a subfolder for each month:

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
| `name`          | Yes      | The account label written to Column G — identical to the plain-string form.                      |
| `ignore_before` | No       | `YYYY-MM-DD`. Transactions dated **before** this day are dropped. The cutoff day itself is kept. |

Dropped rows are reported in the per-file summary (e.g. `skipped={'before 2026-06-01': 25}`), so you can always see how many were filtered. The cutoff is applied before deduplication, and `--account` overrides the label only — it does not disable a matched account's cutoff.

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
| `ignore_before` | The **Cutoff Date**. Items whose shipment **ship date** is before it are ignored (Orders before it were recorded as Charge rows). Compared with the ship date, not the Order Date. |

Payment Method is set from the card on the Order: its last four digits are matched against `accounts.json` keys that contain them (e.g. key `Chase1111` for a card ending 1111). Gift card only gives "Amazon Gift Card", points only gives "Points", gift card plus card gives the card.

### 2. Scrape, then import (once per billing cycle)

1. Open Chrome, logged in to Amazon, with the Claude in Chrome extension.
2. Paste the prompt from `scrape-amazon-orders.md`. It reads the last 90 days of Orders and saves `amazon-orders-<run date>.json` into the current month's folder, e.g. `transactions/2026-09/`. It records raw facts only and calculates nothing.
3. Preview, then import (same commands as cards; the folder import picks up `.json` alongside CSVs and PDFs):

```bash
.venv/bin/python main.py transactions/2026-09/ --dry-run
.venv/bin/python main.py transactions/2026-09/
```

The importer calculates each Item's Loaded Cost (price, minus Promos, plus tax, plus shipping and whole-Order discount shares) and writes it as a formula in Amount, e.g. `=2*12.99-3+1.81+0.42`. `--dry-run`, `--from`/`--to`, `--force`, and the import log work as for cards.

The dry-run summary counts Items left out:
- `not ready`: an Order with a non-cancelled Item not shipped yet. It is picked up on a later scrape.
- `total mismatch`: calculated costs did not equal Amazon's Order total. The Order is skipped with a warning naming the expected and calculated totals.
- cutoff: Items shipped before the Cutoff Date.

Rows are deduplicated by a key in Notes (Column K): `split-transactions automation amazon <order number> #<position>`. Re-scraping never duplicates rows.

Returns and partial refunds arrive on a later scrape as **negative rows** dated on the refund date. They copy "Send to Splitwise" and "For who" from the original Item row. A Refund on an Order shipped before the Cutoff Date is skipped with a warning (enter it by hand).

### 3. The card filter

When importing any card or bank CSV or PDF, Charges (and refund credits) starting with `Amazon.com*`, `AMAZON MKTPL*`, or `AMZN Mktp*` are dropped so Amazon Orders are counted once. The per-file summary shows them as `amazon order charge`. Whole Foods, Prime, Prime Video, Kindle, and Audible Charges still import from the card CSV.

### 4. Classify Items in the sheet

New Item rows default to **Shared** (Column E "Send to Splitwise" ticked, "For who" as card rows get). After importing:
- **Personal** Item: untick "Send to Splitwise" (E). The row stays recorded so you can reclassify later.
- **Partner's** Item: set "For who" (H) to Partner.

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
