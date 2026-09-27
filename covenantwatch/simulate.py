"""SIMULATED FY2027 monitoring feed on top of the borrowers' REAL FY2024-26 financials and covenant terms.

Real companies' future quarters do not exist yet, so the feed is simulated, with problems planted on purpose so the
monitor can be checked against known answers (evals/expected_alerts.json):

  P1  Madhur: debt-to-equity climbs 1.80 -> 2.55 -> 3.48 (limit 3.33) -> 3.10: early warning in Q2, breach in Q3
  P2  Madhur: security cover 1.62 -> 1.45 -> 1.30 (minimum 1.33) -> 1.38
  P3  Madhur: stock statements: August sent on 22 Sep (Bajaj's 20th deadline missed, RBL's 25th met),
      November sent on 27 Dec (both missed), February not sent
  P4  Madhur: Q2 compliance certificate reports D/E 2.05; recomputed from the same quarter's balance sheet it is 2.55
  P5  Madhur: new HDFC supply-chain finance line without intimation to existing lenders; ICRA downgrade in January
  P6  Atomberg: equity investment in the Bangladesh subsidiary without lender consent
  P7  Anchor: CFO resignation (management change needs lender consent / intimation)
  plus events that must NOT alert: consented actions and routine news.

    python -m covenantwatch.simulate
"""

import json

from covenantwatch.config import BORROWERS, DATA

QUARTERS = [("FY2027-Q1", "2026-06-30"), ("FY2027-Q2", "2026-09-30"), ("FY2027-Q3", "2026-12-31"), ("FY2027-Q4", "2027-03-31")]


def financials() -> list[dict]:
    rows = []
    for doc, b in BORROWERS.items():  # real annual baselines
        for period, f in b["financials"].items():
            rows.append({"doc": doc, "period": period, "period_end": f"{period[2:]}-03-31".replace("FY", "20"), "source": "DRHP (real)", **f})
    # simulated quarters: (equity, D/E, PBT, finance costs, charged current assets / WC outstanding)
    plan = {
        "madhur_steel": [(12000, 1.80, 800, 470, 1.62), (12300, 2.55, 760, 520, 1.45), (12500, 3.48, 420, 610, 1.30), (12900, 3.10, 700, 580, 1.38)],
        "atomberg": [(1800, 1.40, -300, 110, None), (1760, 1.45, -250, 112, None), (1730, 1.52, -210, 115, None), (1700, 1.48, -150, 118, None)],
        "anchor_offshore": [(1330, 0.16, 32, 6, None), (1350, 0.15, 30, 6, None), (1365, 0.14, 35, 6, None), (1390, 0.15, 38, 6, None)],
    }
    for doc, qs in plan.items():
        for (period, end), (eq, de, pbt, fc, cover) in zip(QUARTERS, qs):
            debt = de * eq
            wc = 0.9 * debt if cover else None
            rows.append({"doc": doc, "period": period, "period_end": end, "source": "SIMULATED", "current_borrowings": round(debt * 0.95, 2),
                         "noncurrent_borrowings": round(debt * 0.05, 2), "total_equity": eq, "pbt": pbt, "finance_costs": fc,
                         "current_assets_charged": round(cover * wc, 2) if cover else None, "wc_outstanding": round(wc, 2) if wc else None,
                         "collateral_value": 760.0 if doc == "madhur_steel" else None, "facility_amount": 1700.0 if doc == "madhur_steel" else None})
    return rows


def stock_statements() -> list[dict]:
    months = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]
    late = {"2026-08": "2026-09-22", "2026-11": "2026-12-27", "2027-02": None}
    out = []
    for m in months:
        y, mo = map(int, m.split("-"))
        ny, nm = (y + 1, 1) if mo == 12 else (y, mo + 1)
        out.append({"doc": "madhur_steel", "month": m, "submitted_on": late.get(m, f"{ny}-{nm:02d}-18")})
    return out


def certificates() -> list[dict]:
    reported = {"FY2027-Q1": 1.80, "FY2027-Q2": 2.05, "FY2027-Q3": 3.48, "FY2027-Q4": 3.10}  # Q2 misstated (actual 2.55)
    submitted = {"FY2027-Q1": "2026-07-28", "FY2027-Q2": "2026-10-29", "FY2027-Q3": "2027-01-29", "FY2027-Q4": "2027-04-28"}
    return [{"doc": "madhur_steel", "period": p, "metric": "debt_to_equity", "reported": v, "submitted_on": submitted[p]} for p, v in reported.items()]


EVENTS = [
    ("EV01", "madhur_steel", "2026-08-02", "The vehicle loan EMI for July was paid on the due date.", None),
    ("EV02", "madhur_steel", "2026-10-14", "The company availed a Rs 12 crore supply-chain finance line from HDFC Bank to fund higher steel inventory.", False),
    ("EV03", "madhur_steel", "2026-11-05", "Tata Capital enhanced the channel finance limit by Rs 3 crore; NOC was obtained from PNB, RBL Bank and Bajaj Finance beforehand.", True),
    ("EV04", "madhur_steel", "2027-01-20", "ICRA revised the long-term rating of the company to [ICRA]BBB- (Negative) from [ICRA]BBB (Stable).", None),
    ("EV05", "atomberg", "2026-09-15", "The company launched a new range of smart ceiling fans with voice control.", None),
    ("EV06", "atomberg", "2026-12-10", "The company invested Rs 50 million as equity in its Bangladesh subsidiary to fund local distribution.", False),
    ("EV07", "anchor_offshore", "2026-10-20", "Members approved alteration of the Articles of Association; prior written consent of the lenders was obtained.", True),
    ("EV08", "anchor_offshore", "2026-12-01", "The company opened a new service base at Kakinada port.", None),
    ("EV09", "anchor_offshore", "2027-01-05", "The Chief Financial Officer has resigned with effect from 31 January.", False),
]


def build() -> dict:
    feed = {"financials": financials(), "stock_statements": stock_statements(), "certificates": certificates(),
            "events": [{"id": i, "doc": d, "date": dt, "text": t, "consent_obtained": c} for i, d, dt, t, c in EVENTS]}
    (DATA / "feed_fy27_simulated.json").write_text(json.dumps(feed, indent=2), encoding="utf-8")
    return feed


if __name__ == "__main__":
    f = build()
    print({k: len(v) for k, v in f.items()})
