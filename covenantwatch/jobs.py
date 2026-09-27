"""Scheduled entry point. Run daily from cron / Windows Task Scheduler / a GitHub Actions schedule:

    python -m covenantwatch.jobs            # today
    python -m covenantwatch.jobs 2027-03-31 # a given date (backfill)

Idempotent: alerts are keyed, so a job that runs twice (or is retried after a crash) never double-notifies.
"""

import sys
import time
from datetime import date

from covenantwatch.monitor import run


def main() -> None:
    as_of = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    for attempt in range(3):
        try:
            new = run(as_of)
            print(f"{as_of}: {len(new)} new alert(s)")
            return
        except Exception as e:  # transient DB lock or network error: retry, then fail loudly for the scheduler
            print(f"attempt {attempt + 1} failed: {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    sys.exit(1)


if __name__ == "__main__":
    main()
