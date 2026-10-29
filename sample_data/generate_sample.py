"""Regenerate sample_data/monthly_cashflow.csv (synthetic, fixed seed).

python sample_data/generate_sample.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260101
MONTHS = 36
START = "2023-01-01"
BASE = 420_000.0  # monthly net cash flow, in currency units
TREND_PER_MONTH = 3_500.0
# Retail-style year: soft Q1, mid-year lift, strong Q4.
SEASONAL = np.array([-60, -45, -10, 15, 30, 55, 40, 20, 5, 35, 80, 130]) * 1_000.0
NOISE_SD = 18_000.0

OUT = Path(__file__).with_name("monthly_cashflow.csv")


def main() -> None:
    rng = np.random.default_rng(SEED)
    months = pd.date_range(START, periods=MONTHS, freq="MS")
    t = np.arange(MONTHS)
    amount = BASE + TREND_PER_MONTH * t + SEASONAL[months.month - 1] + rng.normal(0, NOISE_SD, MONTHS)
    frame = pd.DataFrame({"date": months.strftime("%Y-%m-%d"), "amount": amount.round(2)})
    frame.to_csv(OUT, index=False)
    print(f"Wrote {len(frame)} rows to {OUT}")


if __name__ == "__main__":
    main()
