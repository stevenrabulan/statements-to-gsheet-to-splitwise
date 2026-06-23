# transactions/

Drop your **real account exports** (CSV or PDF statements) here to organize and import them. Everything in this folder is **gitignored** except this README — real financial records are never committed to version control.

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

## Command Line Arguments & Options

| Flag / Option | Description | Example |
| :--- | :--- | :--- |
| `--dry-run` | Preview the import in the console. Does not write to Google Sheets or log files. | `--dry-run` |
| `--force` | Force reprocessing of files that have already been imported (overrides the import log check). | `--force` |
| `--from YYYY-MM-DD` | Only import transactions dated on or after the specified date. | `--from 2026-06-01` |
| `--to YYYY-MM-DD` | Only import transactions dated on or before the specified date. | `--to 2026-06-30` |
| `--account "NAME"` | Manually set/override the sheet's account label (Column G). Use with single files. | `--account "Chase Checking"` |
| `--source ADAPTER` | Force the use of a specific parser adapter (`fakecoin`, `discover`, `chase_checking`, `chase_credit`, `pdf`). | `--source fakecoin` |
| `--year YYYY` | Specify the calendar year for PDF statements (as credit card PDFs often omit the year on transaction lines). | `--year 2026` |

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
