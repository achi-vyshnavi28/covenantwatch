"""CovenantWatch dashboard for a credit analyst: portfolio heatmap, alert inbox with feedback, covenant register.

    streamlit run app/dashboard.py
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# On Streamlit Cloud, keys come from the app's Secrets settings (never from the repo). Accept keys at the top level or
# inside a [section], in any letter case.
try:
    for _k, _v in st.secrets.items():
        for _kk, _vv in (_v.items() if hasattr(_v, "items") else [(_k, _v)]):
            if isinstance(_vv, str) and _vv.strip():
                os.environ[_kk.upper()] = _vv.strip()
except Exception:
    pass

from covenantwatch.config import BORROWERS, DATA, REPORTS  # noqa: E402
from covenantwatch.db import connect  # noqa: E402

st.set_page_config(page_title="CovenantWatch", layout="wide")
st.title("CovenantWatch")
st.caption("Covenant monitoring for a private-credit portfolio. Covenants and FY2024-26 financials are REAL (from the "
           "borrowers' DRHPs filed with SEBI); FY2027 quarters are SIMULATED with planted problems, clearly marked.")

con = connect()
if not con.execute("SELECT 1 FROM alerts LIMIT 1").fetchone():
    from covenantwatch.monitor import run
    from covenantwatch.simulate import build

    build()
    run("2027-03-31", con=con, send=False)

as_of = st.select_slider("Show the portfolio as it looked on", options=["2026-06-30", "2026-09-30", "2026-12-31", "2027-03-31"], value="2027-03-31")
tab_p, tab_a, tab_r, tab_e = st.tabs(["Portfolio", "Alerts", "Covenant register", "How reliable is it?"])

with tab_p:
    tests = pd.read_sql("SELECT t.*, f.period_end, f.source FROM tests t JOIN financials f USING (doc, period) WHERE f.period_end <= ?", con, params=(as_of,))
    latest = tests.sort_values("period_end").groupby(["doc", "metric", "kind"]).tail(1)
    color = {"green": "🟢", "amber": "🟠", "red": "🔴"}
    latest["status"] = latest["status"].map(lambda s: f"{color[s]} {s}")
    st.markdown("**Latest test per borrower** (covenant = from the loan terms; policy = the fund's own trigger)")
    st.dataframe(latest[["doc", "metric", "kind", "period", "actual", "operator", "limit_value", "headroom_pct", "status", "source"]],
                 hide_index=True, use_container_width=True)
    doc = st.selectbox("Trend for", list(BORROWERS), format_func=lambda d: BORROWERS[d]["name"])
    for metric in tests[tests.doc == doc].metric.unique():
        t = tests[(tests.doc == doc) & (tests.metric == metric)].sort_values("period_end")
        st.markdown(f"**{metric.replace('_', ' ')}** (limit {t['operator'].iloc[-1]} {t['limit_value'].iloc[-1]})")
        st.line_chart(t.set_index("period")[["actual", "limit_value"]])

with tab_a:
    alerts = pd.read_sql("SELECT * FROM alerts WHERE date <= ? ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, date",
                         con, params=(as_of,))
    c1, c2, c3 = st.columns(3)
    for col, sev in zip((c1, c2, c3), ("high", "medium", "low")):
        col.metric(f"{sev} alerts", int((alerts.severity == sev).sum()))
    for _, a in alerts.iterrows():
        with st.expander(f"[{a['severity']}] {a['date']} · {BORROWERS[a['doc']]['name']} · {a['title']}"):
            st.write(a["detail"])
            st.caption(f"Evidence: {a['evidence']} · status: {a['status']}")
            v = st.radio("Analyst verdict", ["—", "confirmed", "false_positive", "resolved"], key=a["key"], horizontal=True)
            if v != "—" and st.button("Save", key="save" + a["key"]):
                from covenantwatch.api import FeedbackIn, feedback

                feedback(a["key"], FeedbackIn(verdict=v))
                st.success("Saved to the feedback log.")

with tab_r:
    doc_r = st.selectbox("Borrower", list(BORROWERS), format_func=lambda d: BORROWERS[d]["name"], key="reg")
    reg = pd.read_sql("SELECT category, topic, lender, operator, threshold, deadline, page, quote, status FROM covenants WHERE doc=? ORDER BY category, topic", con, params=(doc_r,))
    st.markdown(f"{len(reg)} covenants extracted from the DRHP, each with its page and a verified quote.")
    st.dataframe(reg, hide_index=True, use_container_width=True)

with tab_e:
    for name, label in (("extraction_gemini-3.5-flash-lite.json", "Covenant extraction vs hand-labelled register"),
                        ("event_classification.json", "Event classification (36 labelled events)"), ("monitor_eval.json", "Monitoring replay (FY2027)")):
        p = REPORTS / name
        if p.exists():
            st.markdown(f"**{label}**")
            d = json.loads(p.read_text())
            st.json({k: v for k, v in d.items() if k != "alerts"} if isinstance(d, dict) else d, expanded=False)
