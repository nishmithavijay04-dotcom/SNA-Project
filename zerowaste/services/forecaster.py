"""Demand forecaster. Predicts servings for a (date, meal) using ONLY information known the day before:
calendar flags + past consumption (lag1, lag7, 7-day mean). No same-day columns (no leakage).
Evaluation: time-ordered split, compared with 'same as last week' baselines, and a waste simulation at the
SAME service level as the status-quo plan."""
import math
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import config as C

FLAGS = ["is_holiday", "is_exam", "is_event", "is_special"]
FEATURES = ["dow", "month", *FLAGS, "lag1", "lag7", "roll7", "meal_Breakfast", "meal_Lunch", "meal_Dinner"]

def load_demand(src):
    """Accepts a CSV path or DataFrame. Required: date, meal, consumed. Optional: prepared, flags, demand, ran_out."""
    df = src.copy() if isinstance(src, pd.DataFrame) else pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    miss = [c for c in ("date", "meal", "consumed") if c not in df.columns]
    if miss:
        raise ValueError(f"Demand file is missing required columns: {miss}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        raise ValueError("Some dates could not be read (use YYYY-MM-DD)")
    df["meal"] = df["meal"].astype(str).str.strip().str.title()
    bad = sorted(set(df["meal"]) - set(C.MEALS))
    if bad:
        raise ValueError(f"Unknown meal names {bad}; use {C.MEALS}")
    df["consumed"] = pd.to_numeric(df["consumed"], errors="coerce")
    if df["consumed"].isna().any() or (df["consumed"] < 0).any():
        raise ValueError("'consumed' must be non-negative numbers")
    for f in FLAGS:
        df[f] = pd.to_numeric(df[f], errors="coerce").fillna(0).astype(int) if f in df.columns else 0
    df = df.drop_duplicates(["date", "meal"], keep="last").sort_values(["meal", "date"]).reset_index(drop=True)
    if df["date"].nunique() < 28:
        raise ValueError("Need at least 28 days of history to train the forecaster")
    return df

def _series_lags(s):
    """s: consumed indexed by date for one meal. Returns lag1, lag7, roll7 aligned to s.index."""
    lag1 = s.shift(1, freq="D").reindex(s.index)
    lag7 = s.shift(7, freq="D").reindex(s.index)
    roll7 = s.rolling("7D", closed="left", min_periods=3).mean()
    return lag1, lag7, roll7

def build_features(df):
    parts = []
    for meal, g in df.groupby("meal"):
        g = g.sort_values("date").copy()
        s = g.set_index("date")["consumed"].astype(float)
        g["lag1"], g["lag7"], g["roll7"] = [x.values for x in _series_lags(s)]
        parts.append(g)
    out = pd.concat(parts).sort_values(["meal", "date"]).reset_index(drop=True)
    out["dow"], out["month"] = out["date"].dt.dayofweek, out["date"].dt.month
    for m in C.MEALS:
        out[f"meal_{m}"] = (out["meal"] == m).astype(int)
    return out

def _truth(df):
    return df["demand"] if "demand" in df.columns else df["consumed"]

def _rf():
    return RandomForestRegressor(n_estimators=300, min_samples_leaf=3, random_state=0, n_jobs=-1)

def add_actual(history, d, meal, consumed, prepared=None, flags=None):
    """Return a new history DataFrame including one logged actual (replaces an existing row for the same date+meal)."""
    flags = flags or {}
    row = {"date": pd.Timestamp(d), "meal": meal, "consumed": consumed, **{f: int(bool(flags.get(f, 0))) for f in FLAGS}}
    if prepared is not None:
        row["prepared"] = prepared
    h = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    return h.drop_duplicates(["date", "meal"], keep="last").sort_values(["meal", "date"]).reset_index(drop=True)

@dataclass
class Forecaster:
    model: RandomForestRegressor = None
    history: pd.DataFrame = None
    buffer: float = 0.1
    target_service: float = 0.95
    metrics: dict = field(default_factory=dict)
    val_rel: np.ndarray = None

    # ---------- training + evaluation ----------
    @classmethod
    def fit(cls, df):
        df = load_demand(df)
        feats = build_features(df).dropna(subset=["lag1", "lag7", "roll7"]).reset_index(drop=True)
        dates = np.sort(feats["date"].unique())
        i1, i2 = int(len(dates) * 0.70), int(len(dates) * 0.85)
        tr = feats[feats["date"] < dates[i1]]
        va = feats[(feats["date"] >= dates[i1]) & (feats["date"] < dates[i2])]
        te = feats[feats["date"] >= dates[i2]]
        m = _rf().fit(tr[FEATURES], tr["consumed"])

        pv = m.predict(va[FEATURES])
        val_rel = (_truth(va).values - pv) / np.maximum(pv, 1)
        service = C.FORECAST_SERVICE
        buffer = float(max(0.0, np.quantile(val_rel, service)))
        metrics = cls._evaluate(m, val_rel, buffer, te)
        metrics.update({"n_train_rows": len(tr), "n_val_rows": len(va), "n_test_rows": len(te),
                        "train_end": str(pd.Timestamp(dates[i1]).date()), "test_start": str(pd.Timestamp(dates[i2]).date()),
                        "buffer": buffer, "target_service": service, "features": list(FEATURES)})
        final = _rf().fit(feats[FEATURES], feats["consumed"])          # production model uses all history
        return cls(model=final, history=df, buffer=buffer, target_service=service, metrics=metrics, val_rel=val_rel)

    @staticmethod
    def _evaluate(m, val_rel, buffer, te):
        y = _truth(te).values.astype(float)
        p = m.predict(te[FEATURES])
        out = {}
        for name, pred in (("model", p), ("lag7", te["lag7"].values), ("roll7", te["roll7"].values)):
            out[f"mae_{name}"] = float(np.mean(np.abs(y - pred)))
            out[f"mape_{name}"] = float(np.mean(np.abs(y - pred) / np.maximum(y, 1)) * 100)
        kind = np.select([te["is_holiday"] == 1, te["is_exam"] == 1, te["is_event"] == 1, te["is_special"] == 1],
                         ["holiday", "exam week", "event", "special dish"], "normal")
        out["by_day_type"] = (pd.DataFrame({"day type": kind, "model": np.abs(y - p), "last-week baseline": np.abs(y - te["lag7"].values)})
                              .groupby("day type").mean().round(1).reset_index().to_dict("records"))
        if "prepared" in te.columns:
            sim = lambda pr: {"waste": float(np.maximum(pr - y, 0).sum()), "short": float(np.maximum(y - pr, 0).sum()),
                              "service": float((pr >= y).mean())}
            a = te["prepared"].values.astype(float)
            plan = np.ceil(p * (1 + buffer))
            out["sim_status_quo"], out["sim_forecast"] = sim(a), sim(plan)
            # trade-off: waste vs service for the forecaster at many buffers (test days)
            grid = np.arange(0.0, 0.401, 0.01)
            curve = pd.DataFrame([{"buffer_pct": round(g * 100), **sim(np.ceil(p * (1 + g)))} for g in grid])
            out["tradeoff"] = curve
            sq = out["sim_status_quo"]
            # forecaster waste at the SAME service level as the status quo (interpolated on the test curve)
            cs = curve.sort_values("service")
            matched = float(np.interp(sq["service"], cs["service"], cs["waste"]))
            out["matched_waste"] = matched
            out["matched_waste_reduction_pct"] = float(100 * (1 - matched / max(sq["waste"], 1e-9)))
            out["waste_reduction_pct"] = float(100 * (1 - out["sim_forecast"]["waste"] / max(sq["waste"], 1e-9)))
            wk = pd.DataFrame({"week": te["date"].dt.to_period("W").dt.start_time, "status quo": np.maximum(a - y, 0),
                               "with forecaster": np.maximum(plan - y, 0)}).groupby("week").sum()
            out["weekly_waste"] = wk
        return out

    def buffer_for(self, service):
        """Safety buffer (fraction) needed so the plan covers demand on `service` share of days (from validation errors)."""
        return float(max(0.0, np.quantile(self.val_rel, min(max(service, 0.5), 0.995)))) if self.val_rel is not None else self.buffer

    # ---------- prediction ----------
    def _hist_value(self, meal, d, lag_days):
        s = self.history[self.history["meal"] == meal].set_index("date")["consumed"].sort_index()
        want = pd.Timestamp(d) - pd.Timedelta(days=lag_days)
        if want in s.index:
            return float(s.loc[want])
        s = s[s.index < pd.Timestamp(d)]
        return float(s.iloc[-1]) if len(s) else float("nan")

    def predict(self, d, meal, flags=None, service=None):
        d = pd.Timestamp(d)
        flags = flags or {}
        s = self.history[(self.history["meal"] == meal) & (self.history["date"] < d)].set_index("date")["consumed"].sort_index()
        if len(s) < 7:
            raise ValueError("Not enough history for this meal")
        lag1, lag7 = self._hist_value(meal, d, 1), self._hist_value(meal, d, 7)
        roll7 = float(s.iloc[-7:].mean())
        row = {"dow": d.dayofweek, "month": d.month, "lag1": lag1, "lag7": lag7, "roll7": roll7,
               **{f: int(bool(flags.get(f, 0))) for f in FLAGS}, **{f"meal_{m}": int(m == meal) for m in C.MEALS}}
        yhat = float(self.model.predict(pd.DataFrame([row])[FEATURES])[0])
        buf = self.buffer if service is None else self.buffer_for(service)
        return {"forecast": round(yhat), "recommended": math.ceil(yhat * (1 + buf)),
                "last_week": round(lag7), "status_quo": math.ceil(lag7 * (1 + C.STATUS_QUO_BUFFER)),
                "buffer_pct": round(buf * 100, 1)}

    def with_actual(self, d, meal, consumed, prepared=None, flags=None):
        return add_actual(self.history, d, meal, consumed, prepared, flags)
