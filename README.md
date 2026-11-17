# Credit Card Analyzer

Privacy-first local Python tool that works out where your money goes and **which credit card fits your spending best**. Type in your monthly expenses (or point it at your statements) and it ranks Canadian credit cards by yearly rewards minus annual fee.

It reads CSV statements, can extract tables from PDF statements on a best-effort basis, classifies transactions with deterministic rules plus a local Ollama model, and writes Excel and Markdown reports with card recommendations.

## Quick start: which card should I get?

No statements or Ollama needed:

```bash
pip install -r requirements.txt
python -m src.main recommend --spend "groceries=650,restaurants=300,gas=180,phone=120,shopping=250"
```

Or keep your spending in a file (see [`examples/monthly_spend.csv`](examples/monthly_spend.csv)):

```bash
python -m src.main recommend --spend-file examples/monthly_spend.csv
```

Example output:

```text
Based on about $1,835/month of card-eligible spending ($22,020/year).

| Rank | Card | Rewards/yr | Fee/yr | Net/yr |
| --- | --- | --- | --- | --- |
| 1 | Scotiabank Gold American Express Card | $773.40 | $120.00 | $653.40 |
| 2 | American Express Cobalt Card | $739.80 | $191.88 | $547.92 |
| 3 | American Express SimplyCash Preferred Card | $639.60 | $119.88 | $519.72 |
...
**Best two-card setup: Scotiabank Gold American Express Card + Tangerine Money-Back Credit Card**
```

Run `recommend` with no spending flags to estimate monthly spending from the statement CSVs in `input/` instead.

### How cards are scored

- Card data lives in [`data/cards.json`](data/cards.json): annual fee, base rate, bonus-category tiers with yearly caps, pick-your-categories cards, and minimum-spend rules. Rates are percent cash-equivalent (points valued at 1 cent).
- Spending over a tier's cap earns the base rate. Rent, transfers/payments and financial fees are excluded.
- Cards are ranked by net yearly value. The tool also tries every two-card pair, putting each category on whichever card earns more.
- **Earn rates are approximate and change often. Check the issuer's site before applying. This is an estimate, not financial advice.** Edit `data/cards.json` (or point `cards_file` in the config at your own copy) to add cards or update rates.

Statements stay on your machine. The app does not require OpenAI API keys and does not upload files anywhere. Unknown merchant classification is sent only to your local Ollama API at `http://localhost:11434`.

## Setup

1. Install Ollama from <https://ollama.com/>.
2. Pull the default local model:

   ```bash
   ollama pull qwen3:30b-a3b
   ```

   Optional fallback model:

   ```bash
   ollama pull qwen3:14b
   ```

3. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Put statement CSV and optional PDF files in `input/`. For monthly uploads, use folders:

   ```text
   input/
     2026-01/
       chase.csv
       amex.pdf
     2026-02/
       chase.csv
       amex.pdf
   ```

## Commands

Analyze CSV files in `input/`:

```bash
python -m src.main analyze-csv
```

Extract PDF tables into `output/extracted_csv/`:

```bash
python -m src.main extract-pdf
```

Extract PDFs, then analyze input CSVs plus extracted CSVs:

```bash
python -m src.main analyze-all
```

Analyze monthly uploads and create one report per transaction month:

```bash
python -m src.main analyze-months
```

Extract PDFs recursively from monthly folders:

```bash
python -m src.main extract-pdf-months
```

Extract PDFs recursively, then create one report per transaction month:

```bash
python -m src.main analyze-all-months
```

PDF extraction uses `pdfplumber` and is best-effort. Always manually review files in `output/extracted_csv/` before relying on results because statement PDFs vary widely.

## Outputs

- `output/credit_card_report.xlsx`
  - `Transactions`
  - `Category Summary`
  - `Monthly Summary`
  - `Merchant Summary`
  - `Review Needed`
  - `Recurring Candidates`
  - `Card Recommendations`
- `output/written_report.md` (includes a credit card recommendations section)
- `output/classification_cache.json`

Monthly commands write reports like:

```text
output/
  2026-01/
    credit_card_report.xlsx
    written_report.md
  2026-02/
    credit_card_report.xlsx
    written_report.md
```

Monthly reports are grouped by the transaction date in the CSV, not only by the folder name. This handles statement files that contain transactions from adjacent months.

## Configuration

Edit `config.example.yaml` or pass another config file with `--config`.

```yaml
input_dir: input
output_dir: output
ollama_url: http://localhost:11434
ollama_model: qwen3:30b-a3b
ollama_fallback_model: qwen3:14b
request_timeout_seconds: 60
classification_cache: output/classification_cache.json
low_confidence_threshold: 0.65
cards_file: data/cards.json   # optional
```

The config parser intentionally supports simple top-level `key: value` pairs.

## CSV Support

The loader automatically detects common columns:

- Date columns such as `Date`, `Transaction Date`, `Posted Date`
- Description columns such as `Description`, `Merchant`, `Transaction Details`
- Amount columns such as `Amount`, `Transaction Amount`
- Split amount columns such as `Debit` and `Credit`

Normalized transactions use this schema:

```text
date, description, amount, source_file
```

When separate debit and credit columns exist, debits are treated as positive purchases and credits/payments are treated as negative amounts. Single amount columns are preserved as provided by the statement export.

## Classification

Classification runs in this order:

1. Deterministic merchant keyword rules from `src/rules.py`
2. Cached result from `output/classification_cache.json`
3. Local Ollama API for unknown merchants
4. `Other` if Ollama is unavailable or returns invalid JSON

Ollama is prompted to return JSON only:

```json
{"category":"Groceries","confidence":0.85,"reason":"Merchant is a supermarket."}
```

Results include `category`, `confidence`, `reason`, and `review_needed`.

## Tests

Run:

```bash
python -m unittest discover -s tests
```

## License

MIT
