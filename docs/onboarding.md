# Going live at a fund: onboarding playbook

A covenant monitor is only as good as its register. This is how I would onboard a private-credit fund in two weeks.

## Day 1-3: collect and map
- For each borrower: sanction letters / facility agreements, the latest compliance certificate, last 8 quarters of
  financials, and the stock-statement submission log.
- Agree the definitions that differ by lender: what counts as "debt" (leases? guarantees?), "tangible net worth",
  "EBITDA" adjustments. Store the definition next to each covenant. *(The filings I used never define them.)*

## Day 4-6: extract and confirm the register
- Run extraction. Every covenant arrives with its page and a verified quote; unverifiable ones are dropped and listed.
- An analyst reviews each borrower's register in the dashboard and confirms it (`POST /register/{doc}/confirm`).
  **Nothing is monitored as a covenant until a person has confirmed it.**
- Gaps go on a list for the relationship manager: e.g. "financial covenants exist but numbers not in our documents".

## Day 7-10: backfill and tune
- Backfill 8 quarters: every red/amber in history should match what the fund already knew. Differences are either
  missed breaches (valuable) or wrong definitions (fix before go-live).
- Tune thresholds for early warning with the credit team (default: amber within 15% of a limit or trending to it).

## Day 11-14: go live
- Daily job (`python -m covenantwatch.jobs`), Slack channel per portfolio, weekly digest to the partner.
- Every alert gets an analyst verdict (confirmed / false positive / resolved). The feedback table is reviewed weekly:
  false-positive patterns become rule changes; misses become new gold-set cases.

## Success metrics
| Metric | Target |
|---|---|
| Breaches found by CovenantWatch before the borrower reports them | as many as possible; count each |
| False-positive rate on alerts (analyst verdicts) | < 20% after tuning |
| Reporting deadlines missed without an alert | 0 |
| Analyst hours per quarter on covenant testing | measured before and after |
