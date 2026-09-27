"""Borrowers, paths and models."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FILINGS = DATA / "filings"
DB_PATH = Path(os.getenv("COVENANTWATCH_DB", DATA / "covenantwatch.sqlite3"))
CACHE = ROOT / ".cache"
REPORTS = ROOT / "reports"

# a local .env, or (on the author's machine) the shared one next to the sibling rootcause project.
# ROOT may be /app inside Docker, which has no grandparent, so guard the second path.
for env in [ROOT / ".env"] + ([ROOT.parents[1] / "rootcause" / ".env"] if len(ROOT.parents) > 1 else []):
    if env.exists():
        load_dotenv(env)

# Three real borrowers. Covenant text comes from the "Financial Indebtedness" chapter of each company's DRHP (SEBI);
# FY2024-26 financials from its restated summary statements. Values are in the unit the filing reports.
BORROWERS = {
    "madhur_steel": {
        "name": "Madhur Iron & Steel (India) Ltd", "unit": "lakhs", "sector": "Steel",
        "lenders": "PNB, RBL Bank, Bajaj Finance, Tata Capital, SIDBI, Bank of Baroda",
        "financials": {  # restated, standalone
            "FY2024": {"current_borrowings": 6848.70, "noncurrent_borrowings": 401.65, "total_equity": 4277.12, "pbt": 1733.90, "finance_costs": 708.16},
            "FY2025": {"current_borrowings": 11405.28, "noncurrent_borrowings": 311.36, "total_equity": 9399.47, "pbt": 2480.16, "finance_costs": 1222.48},
            "FY2026": {"current_borrowings": 18628.02, "noncurrent_borrowings": 864.53, "total_equity": 11789.73, "pbt": 3239.02, "finance_costs": 1847.29},
        },
        "source_pages": {"financials": [84, 85, 86], "covenants": list(range(424, 445))},
    },
    "atomberg": {
        "name": "Atomberg Technologies Ltd", "unit": "million", "sector": "Consumer appliances",
        "lenders": "Working capital and term-loan banks (names not itemised in the DRHP)",
        "financials": {  # restated, consolidated
            "FY2024": {"current_borrowings": 1431.57, "noncurrent_borrowings": 164.42, "total_equity": 2013.71, "pbt": -1990.80, "finance_costs": 276.16},
            "FY2025": {"current_borrowings": 1573.14, "noncurrent_borrowings": 189.99, "total_equity": 947.10, "pbt": -1174.05, "finance_costs": 476.33},
            "FY2026": {"current_borrowings": 2397.53, "noncurrent_borrowings": 177.75, "total_equity": 1861.46, "pbt": -1488.81, "finance_costs": 449.07},
        },
        "source_pages": {"financials": [81, 82, 83], "covenants": [388, 389, 390]},
    },
    "anchor_offshore": {
        "name": "Anchor Offshore Services Ltd", "unit": "million", "sector": "Marine & offshore services",
        "lenders": "Working capital, term and vehicle loan lenders (names not itemised in the DRHP)",
        "financials": {  # restated, consolidated
            "FY2024": {"current_borrowings": 197.57, "noncurrent_borrowings": 71.86, "total_equity": 785.95, "pbt": 45.60, "finance_costs": 22.77},
            "FY2025": {"current_borrowings": 238.71, "noncurrent_borrowings": 63.98, "total_equity": 914.04, "pbt": 163.15, "finance_costs": 21.69},
            "FY2026": {"current_borrowings": 153.96, "noncurrent_borrowings": 54.34, "total_equity": 1304.25, "pbt": 117.36, "finance_costs": 23.46},
        },
        "source_pages": {"financials": [78, 79, 80], "covenants": [369, 370, 371]},
    },
}

# Fund's own early-warning triggers, applied to every borrower (useful where the filing discloses no numeric covenant).
POLICY = {"debt_to_equity": ("<=", 2.0), "interest_cover": (">=", 1.5)}
EARLY_WARNING_HEADROOM = 0.15  # amber when within 15% of a limit, or when the trend projects a breach next quarter

MODELS = {
    "gemini-3.5-flash-lite": {"id": "gemini/gemini-3.5-flash-lite", "in": 0.10, "out": 0.40},
    "gemini-3.8-flash": {"id": "gemini/gemini-3.8-flash", "in": 0.30, "out": 2.50},
    "gpt-oss-120b": {"id": "groq/openai/gpt-oss-120b", "in": 0.15, "out": 0.60},  # approximate Groq list prices
    "qwen3.8-27b": {"id": "groq/qwen/qwen3.8-27b", "in": 0.29, "out": 0.59},
    "claude-sonnet": {"id": "anthropic/claude-sonnet-4-5", "in": 3.00, "out": 15.00},
    "gpt": {"id": "openai/gpt-5-mini", "in": 0.25, "out": 2.00},
}
DEFAULT_MODEL = os.getenv("COVENANTWATCH_MODEL", "gemini-3.5-flash-lite")
