# CovenantWatch

Covenant monitoring for a private-credit portfolio. It reads a borrower's loan terms, builds a covenant register
with page citations, and then every day tests the numbers, tracks reporting deadlines, checks the borrower's own
compliance certificates, and triages news and lender notices. Alerts go to Slack or the log, once.

**Data:** three real borrowers. Covenants and FY2024-26 financials come from their Draft Red Herring Prospectuses
filed with SEBI (Madhur Iron & Steel, Atomberg Technologies, Anchor Offshore Services). **FY2027 quarters are
simulated** (the future has not happened), with problems planted on purpose so detection can be measured.

## Results

| Step | How it was measured | Result |
|---|---|---|
| **Covenant extraction** (LLM + quote verification) | Against a register I labelled by hand from the filings | Madhur: precision 96%, recall 96%, **all 3 financial limits exact** (D/E ≤ 3.33, security cover ≥ 1.33x, FACR ≥ 0.3x). Atomberg 93% / 93%. Anchor 86% / 100% |
| Page-number fix | Same | Madhur recall **33% → 96%**: the model cited printed page numbers (e.g. "436") instead of PDF pages (441) |
| **Event triage** (news → covenant topic) | 36 labelled events incl. 8 routine-news decoys | LLM 92% accurate, 89% recall, **0 false alerts**; keyword rules 67%, 61% recall |
| **Monitoring** | Week-by-week replay of FY2027 on a fresh database | **15/15 planted problems caught**, each within 6 days; a re-run raises 0 duplicates; 2 extra early warnings, both correct on inspection (one on real Atomberg FY2025 data) |

What it caught in the replay:
- Madhur's debt-to-equity trending to its 3.33 limit: early warning at Q2 (2.55, trend projects 3.30), breach at Q3 (3.48)
- Security cover below 1.33x in Q3, with a Q2 warning
- Stock statements late for **one lender but not the other** (Bajaj wants them by the 20th, RBL by the 25th), and one never sent
- A compliance certificate reporting D/E 2.05 when the same quarter's balance sheet gives 2.55
- A new HDFC credit line taken without telling existing lenders; an ICRA downgrade (event of default)
- Atomberg investing in its Bangladesh subsidiary without consent; Anchor's CFO resigning
- From **real** data: Atomberg's loss-making FY2024-26 results breach the fund's interest-cover trigger
- And it stayed quiet on consented actions and routine news

## How it works

```
DRHP loan pages ─> extract (LLM) ─> verify quote on page ─> register ─> analyst confirms
                                                                  │
quarterly financials ─┐                                           ▼
compliance certificates ┼─> daily monitor ─> tests (green/amber/red, headroom, trend) ─> alerts (keyed, once) ─> Slack
stock-statement dates ─┤                   reporting deadlines per lender                   │
news / lender notices ─┘                   certificate vs recomputed ratio                  ▼
                                           event -> covenant topic (LLM, keyword fallback)  analyst feedback
```

- **SQLite** with SQL views: latest status per borrower (`ROW_NUMBER()`), trend vs previous period (`LAG()`), open alerts.
- **Idempotent**: alerts are keyed, so retries and re-runs never double-notify. Every action is written to an audit table.
- **Degrades gracefully**: if the LLM is unavailable, event triage falls back to keyword rules instead of stopping.
- **API** (FastAPI): portfolio, alerts, analyst feedback, register and confirmation, new events, run. **Dashboard** (Streamlit).
- **Docker** image and GitHub Actions CI (tests, then build the image and call the running API).

## Run

```bash
pip install -r requirements.txt
python -m covenantwatch.extract          # build the register from the filings (needs GEMINI_API_KEY)
python -m covenantwatch.simulate         # FY2027 simulated feed
python -m covenantwatch.monitor --as-of 2027-03-31
python -m evals.monitor_eval             # replay + score
python -m covenantwatch.classify         # event triage: LLM vs keywords
uvicorn covenantwatch.api:app --port 8901
streamlit run app/dashboard.py
pytest                                   # 9 offline tests
```

## Honest limits
- FY2027 is simulated; the detection numbers show the logic works on known problems, not how often real borrowers breach.
- Two of three filings say numeric covenants exist but do not disclose them; for those borrowers the fund's own
  policy triggers stand in until the lender shares the sanction letters.
- Security cover and FACR need data the filings do not give (value of charged assets); the simulated feed supplies it.
- The event test set is small (36) and written by me; real news is messier.

See [docs/onboarding.md](docs/onboarding.md) for how a fund would go live with it.
