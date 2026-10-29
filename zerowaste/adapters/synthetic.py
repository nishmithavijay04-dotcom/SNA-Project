"""Synthetic demand generator for a generic institutional kitchen (mess / hostel / hospital / canteen).
Patterns: weekday/weekend, monsoon dip, holidays, exam weeks, events, special-dish days, trend, noise.
`demand` is the hidden ground truth; the log a real kitchen would have is prepared / consumed / ran_out.
Run:  python -m adapters.synthetic   (writes data/demand_log.csv)"""
import math
import os
from datetime import date, timedelta
import numpy as np
import pandas as pd
import config as C

SHARE = {"Breakfast": 0.72, "Lunch": 0.90, "Dinner": 0.82}      # share of registered strength that eats
DOW = [1.0, 1.0, 1.0, 1.0, 1.0, 0.90, 0.82]                      # Mon..Sun
MONSOON = {6, 7, 8, 9}

def _calendar(days, start, rng):
    idx = pd.date_range(start, periods=days)
    n = len(idx)
    hol = np.zeros(n, bool); exam = np.zeros(n, bool); event = np.zeros(n, bool)
    wd = [i for i, d in enumerate(idx) if d.dayofweek < 5]
    hol[rng.choice(wd, size=max(1, round(14 * days / 365)), replace=False)] = True
    for yr_start in range(0, n, 365):
        for month in (3, 11):                                    # two exam blocks a year
            cands = [i for i in range(yr_start, min(yr_start + 365, n)) if idx[i].month == month and idx[i].day <= 18]
            if cands:
                s = int(rng.choice(cands)); exam[s:s + 10] = True
    ev = [i for i in range(n) if not hol[i]]
    event[rng.choice(ev, size=max(1, round(10 * days / 365)), replace=False)] = True
    return idx, hol, exam & ~hol, event & ~hol

def generate_demand(strength=C.DEFAULT_STRENGTH, days=C.SYNTH_DAYS, seed=C.SYNTH_SEED, end=None,
                    buffer=C.STATUS_QUO_BUFFER):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end) if end is not None else pd.Timestamp(date.today() - timedelta(days=1))
    start = end - pd.Timedelta(days=days - 1)
    idx, hol, exam, event = _calendar(days, start, rng)
    rows = []
    for meal in C.MEALS:
        consumed_hist = {}
        for i, d in enumerate(idx):
            special = int(d.dayofweek == 6 and meal == "Lunch")
            f = SHARE[meal] * DOW[d.dayofweek] * (0.94 if d.month in MONSOON else 1.0) * (1 + 0.05 * i / days)
            if hol[i]: f *= 0.65
            if exam[i]: f *= 0.85 if meal == "Breakfast" else 0.92
            if event[i]: f *= 1.18
            if special: f *= 1.12
            demand = int(round(strength * f * rng.lognormal(0, 0.045)))
            prev = consumed_hist.get(d - pd.Timedelta(days=7))
            prepared = math.ceil(prev * (1 + buffer)) if prev is not None else math.ceil(strength * SHARE[meal] * (1 + buffer))
            consumed = min(demand, prepared)
            consumed_hist[d] = consumed
            rows.append({"date": d.date().isoformat(), "meal": meal, "prepared": prepared, "consumed": consumed,
                         "ran_out": int(demand > prepared), "is_holiday": int(hol[i]), "is_exam": int(exam[i]),
                         "is_event": int(event[i]), "is_special": special, "demand": demand})
    return pd.DataFrame(rows).sort_values(["date", "meal"]).reset_index(drop=True)

def save_default(path=None, **kw):
    path = path or C.DEMAND_LOG
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df = generate_demand(**kw); df.to_csv(path, index=False); return df

if __name__ == "__main__":
    d = save_default(); print(d.shape, d.date.min(), "->", d.date.max())
