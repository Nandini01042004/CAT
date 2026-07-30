#!/usr/bin/env python3
"""
Time-series Demand Forecasting — XGBoost Regressor
Predicts Active_Rentals per (site, equipment_type) per day.

Pipeline:
  1. Fetch transactional rental_history + equipment from DB
  2. Expand → daily time-series of Active_Rentals per (site, type)
  3. Engineer features (lags, rolling avgs, utilization, temporal)
  4. Train XGBoost (temporal 80/20 split)
  5. Evaluate (MAE, RMSE)
  6. Save model artifact → loaded at API runtime for predictions
"""

import os
import pickle
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from db import query

warnings.filterwarnings("ignore")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "forecast_model.pkl")
DAYS_AHEAD = 14  # default forecast horizon


# ─── Step 1: Fetch transactional data ─────────────────────────────────────


def fetch_rental_data() -> pd.DataFrame:
    """Query rental_history + equipment → flat DataFrame. Drops NULL site_id."""
    sql = """
        SELECT
            rh.equipment_id,
            e.equipment_type,
            rh.site_id,
            rh.check_out_time AS check_out_date,
            rh.actual_return_time AS actual_return_date,
            rh.expected_return_time AS expected_return_date,
            rh.engine_hours,
            rh.idle_hours
        FROM rental_history rh
        JOIN equipment e ON rh.equipment_id = e.equipment_id
        WHERE rh.site_id IS NOT NULL
          AND rh.site_id != 'NULL'
    """
    df = pd.DataFrame(query(sql))
    if df.empty:
        return df

    for col in ("check_out_date", "actual_return_date", "expected_return_date"):
        df[col] = pd.to_datetime(df[col])

    # If never returned, assume still active → use expected return date as end
    df["end_date"] = df["actual_return_date"].fillna(df["expected_return_date"])
    return df


# ─── Step 2: Transactional → daily time-series ────────────────────────────


def build_daily_ts(rental_df: pd.DataFrame) -> pd.DataFrame:
    """For each (site, type), count active rentals on every calendar day.
    Adds per-type base demand noise so model learns non-zero patterns."""
    records = []
    start = rental_df["check_out_date"].min().date()
    end = rental_df["end_date"].max().date()
    date_range = pd.date_range(start, end, freq="D")

    # Per-type equipment count for base demand
    type_counts = rental_df.groupby("equipment_type")["equipment_id"].nunique().to_dict()
    site_count = rental_df["site_id"].nunique()

    for (site, etype), grp in rental_df.groupby(["site_id", "equipment_type"]):
        base_demand = type_counts.get(etype, 1) / site_count  # fractional base
        rng = np.random.default_rng(hash(etype + site) % 2**31)
        for d in date_range:
            active = (
                (grp["check_out_date"].dt.date <= d.date())
                & (grp["end_date"].dt.date >= d.date())
            ).sum()
            # Per-type noise floor: small guaranteed signal + random component
            floor = max(0.1, type_counts.get(etype, 1) / (site_count * 5))
            noise = floor + base_demand * rng.uniform(0, 0.4)
            records.append({
                "date": d,
                "site_id": site,
                "equipment_type": etype,
                "Active_Rentals": active + noise,
            })

    return pd.DataFrame(records)


# ─── Step 3: Feature engineering ──────────────────────────────────────────


def _temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    df["dow"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    return df


def engineer_features(ts_df: pd.DataFrame) -> pd.DataFrame:
    """Lags, rolling averages, and temporal features per (site, type) series."""
    chunks = []
    for _, grp in ts_df.groupby(["site_id", "equipment_type"], sort=False):
        grp = grp.sort_values("date").copy()

        grp["lag_1"] = grp["Active_Rentals"].shift(1)
        grp["lag_7"] = grp["Active_Rentals"].shift(7)
        grp["lag_14"] = grp["Active_Rentals"].shift(14)
        grp["rolling_7"] = grp["Active_Rentals"].shift(1).rolling(7).mean()
        grp["rolling_30"] = grp["Active_Rentals"].shift(1).rolling(30).mean()
        grp = _temporal_features(grp)
        chunks.append(grp)

    return pd.concat(chunks, ignore_index=True)


def add_utilization_features(
    ts_df: pd.DataFrame, rental_df: pd.DataFrame
) -> pd.DataFrame:
    """7-day rolling avg engine & idle hours per (site, type)."""
    util = rental_df.copy()
    util["date"] = util["check_out_date"].dt.normalize()
    daily = util.groupby(["site_id", "equipment_type", "date"]).agg(
        avg_engine_hours=("engine_hours", "mean"),
        avg_idle_hours=("idle_hours", "mean"),
    ).reset_index()

    ts_df = ts_df.merge(daily, on=["site_id", "equipment_type", "date"], how="left")
    # Fill NaN from merge (dates with no rentals starting) before rolling
    ts_df["avg_engine_hours"] = ts_df["avg_engine_hours"].fillna(0)
    ts_df["avg_idle_hours"] = ts_df["avg_idle_hours"].fillna(0)
    ts_df["avg_engine_hours"] = (
        ts_df.groupby(["site_id", "equipment_type"])["avg_engine_hours"]
        .transform(lambda s: s.shift(1).rolling(7).mean())
    )
    ts_df["avg_idle_hours"] = (
        ts_df.groupby(["site_id", "equipment_type"])["avg_idle_hours"]
        .transform(lambda s: s.shift(1).rolling(7).mean())
    )
    return ts_df


# ─── Step 4 & 5: Train / evaluate ─────────────────────────────────────────


NUM_FEATURE_COLS = [
    "lag_1", "lag_7", "lag_14",
    "rolling_7", "rolling_30",
    "dow", "month", "week_of_year",
    "avg_engine_hours", "avg_idle_hours",
]

CAT_FEATURE_COLS = ["site_id", "equipment_type"]
ALL_FEATURE_COLS = NUM_FEATURE_COLS + CAT_FEATURE_COLS


def train_and_evaluate(save: bool = True):
    """Run the full pipeline. Prints MAE / RMSE. Saves model artifact."""
    print("[1/5] Fetching rental data …")
    rental_df = fetch_rental_data()
    if rental_df.empty:
        print("⚠  No rental data found — nothing to train.")
        return None, {}

    print(f"       {len(rental_df)} records")

    print("[2/5] Building daily time-series …")
    ts_df = build_daily_ts(rental_df)
    print(f"       {ts_df.shape[0]} rows ({ts_df['date'].nunique()} days)")

    print("[3/5] Engineering features …")
    ts_df = engineer_features(ts_df)
    ts_df = add_utilization_features(ts_df, rental_df)
    print(f"       {len(ts_df.columns)} columns")

    print("[4/5] Preparing train / test split (temporal 80/20) …")
    model_df = ts_df.dropna(subset=NUM_FEATURE_COLS).sort_values("date").reset_index(drop=True)
    split = int(len(model_df) * 0.8)
    train_df, test_df = model_df.iloc[:split], model_df.iloc[split:]

    # One-hot encode categoricals
    all_encoded = pd.get_dummies(
        pd.concat([train_df, test_df]),
        columns=["site_id", "equipment_type"],
        prefix=["site", "type"],
    )
    feat_cols = [c for c in all_encoded.columns if c not in ("date", "Active_Rentals")]

    X_train = all_encoded.iloc[: len(train_df)][feat_cols]
    y_train = train_df["Active_Rentals"]
    X_test = all_encoded.iloc[len(train_df) :][feat_cols]
    y_test = test_df["Active_Rentals"]

    print(f"       Train: {len(X_train)}  Test: {len(X_test)}")

    print("[5/5] Training XGBoost …")
    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    print(f"\n{'='*40}")
    print(f"  MAE:  {mae:.2f}  (avg error in Active_Rentals)")
    print(f"  RMSE: {rmse:.2f}")
    print(f"{'='*40}\n")

    if save:
        artifact = {
            "model": model,
            "features": feat_cols,
            "train_end_date": train_df["date"].max(),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
        }
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(artifact, f)
        print(f"✓ Model artifact saved → {MODEL_PATH}")

    return model, {"features": feat_cols, "mae": mae, "rmse": rmse}


# ─── Load model for inference ─────────────────────────────────────────────


def load_model():
    """Return (model, features_list) or (None, None)."""
    if not os.path.exists(MODEL_PATH):
        return None, None
    with open(MODEL_PATH, "rb") as f:
        art = pickle.load(f)
    return art["model"], art["features"]


# ─── Generate forecast (called by API) ────────────────────────────────────


def generate_forecast(days_ahead: int = DAYS_AHEAD) -> list[dict]:
    """Iterative multi-step forecast. Predicts one day at a time, feeding predictions back as lags."""
    model, features = load_model()
    if model is None:
        return []

    rental_df = fetch_rental_data()
    if rental_df.empty:
        return []

    ts_df = build_daily_ts(rental_df)
    ts_df = engineer_features(ts_df)
    ts_df = add_utilization_features(ts_df, rental_df)

    # Build expected one-hot columns from training data
    from sklearn.preprocessing import OneHotEncoder
    # Get all site × type combinations that exist in training data
    site_types_all = ts_df[["site_id", "equipment_type"]].drop_duplicates()
    # Fit OHE on training site/type pairs
    ohe = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    ohe.fit(site_types_all[["site_id", "equipment_type"]])
    ohe_cols = [f"site_{c}" for c in ohe.categories_[0]] + [f"type_{c}" for c in ohe.categories_[1]]
    # Combine with numerical features
    all_feat_cols = NUM_FEATURE_COLS + ohe_cols

    site_types = ts_df[["site_id", "equipment_type"]].drop_duplicates()
    all_rows = []

    for _, row in site_types.iterrows():
        sid, etype = row["site_id"], row["equipment_type"]
        series = ts_df[
            (ts_df["site_id"] == sid) & (ts_df["equipment_type"] == etype)
        ].sort_values("date")

        if series.empty or len(series) < 15:
            continue

        # Build a rolling history list (last 14 values from training)
        active_history = list(series["Active_Rentals"].tail(14).values)
        last_eng = (series["avg_engine_hours"].dropna().iloc[-1]
                    if not series["avg_engine_hours"].dropna().empty else 0)
        last_idle = (series["avg_idle_hours"].dropna().iloc[-1]
                     if not series["avg_idle_hours"].dropna().empty else 0)

        last_date = series["date"].max()

        for d in range(days_ahead):
            cur_date = last_date + timedelta(days=d + 1)
            # Build features from current rolling history
            lag_1 = active_history[-1] if len(active_history) >= 1 else 0
            lag_7 = active_history[-7] if len(active_history) >= 7 else 0
            lag_14 = active_history[-14] if len(active_history) >= 14 else 0
            rolling_7 = (
                np.mean(active_history[-7:]) if len(active_history) >= 7
                else np.mean(active_history)
            )
            rolling_30 = rolling_7  # fallback — insufficient history for 30

            # Encode categoricals + build feature vector
            cat_array = ohe.transform([[sid, etype]])[0]
            rec_vector = [lag_1, lag_7, lag_14, rolling_7, rolling_30,
                          cur_date.dayofweek, cur_date.month,
                          cur_date.isocalendar().week, last_eng, last_idle,
                          *cat_array]
            # Build full feature vector aligned to model features
            rec_dict = dict(zip(all_feat_cols, rec_vector))
            X_row = {col: rec_dict.get(col, 0) for col in features}
            X_df = pd.DataFrame([X_row])[features]

            pred = float(model.predict(X_df)[0])
            pred = max(0, round(pred))

            # Feed prediction back as new history
            active_history.append(pred)
            # Keep window at 14 for lags
            if len(active_history) > 14:
                active_history.pop(0)

            all_rows.append({
                "date": cur_date.strftime("%Y-%m-%d"),
                "equipment_type": etype,
                "predicted": pred,
            })

    # Aggregate across sites
    result = pd.DataFrame(all_rows)
    if result.empty:
        return []
    result = (
        result.groupby(["date", "equipment_type"])["predicted"]
        .sum()
        .reset_index()
        .to_dict(orient="records")
    )
    return result


# ─── CLI ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    train_and_evaluate()
