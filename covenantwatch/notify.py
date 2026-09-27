"""Send new alerts: Slack (SLACK_WEBHOOK_URL) if configured, otherwise the log. Marked as notified so they go once."""

import os

import httpx

ICON = {"high": ":red_circle:", "medium": ":large_orange_circle:", "low": ":white_circle:"}


def notify(con, keys: list[str]) -> int:
    rows = con.execute(f"SELECT * FROM alerts WHERE notified=0 AND key IN ({','.join('?' * len(keys))}) "
                       "ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END", keys).fetchall()
    if not rows:
        return 0
    lines = [f"{ICON.get(r['severity'], '')} *{r['doc']}* {r['title']}: {r['detail']} _({r['evidence']})_" for r in rows]
    text = f"CovenantWatch: {len(rows)} new alert(s)\n" + "\n".join(lines)
    url = os.getenv("SLACK_WEBHOOK_URL")
    if url:
        httpx.post(url, json={"text": text}, timeout=10).raise_for_status()
    else:
        print(text)
    con.executemany("UPDATE alerts SET notified=1 WHERE key=?", [(r["key"],) for r in rows])
    con.commit()
    return len(rows)
