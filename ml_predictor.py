import numpy as np
from datetime import date, timedelta
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score


def _build_series(records, days=30):
    """Daily consumption vector for the last N days."""
    today = date.today()
    bucket = {}
    for r in records:
        bucket[r.date] = bucket.get(r.date, 0) + r.quantity_used
    return np.array(
        [bucket.get(today - timedelta(days=i), 0.0)
         for i in range(days - 1, -1, -1)],
        dtype=float,
    )


def _make_features(series, lags=(1, 2, 3, 7)):
    max_lag = max(lags)
    X, y = [], []
    for i in range(max_lag, len(series)):
        X.append([series[i - l] for l in lags])
        y.append(series[i])
    return np.array(X), np.array(y)


def predict_reorder(records, current_stock, minimum_stock=5):
    """
    Returns dict:
      model, mae, r2, avg_daily_usage, days_remaining,
      runout_date, reorder_date
    """
    series = _build_series(records, days=30)
    out = {
        'model': 'rule-based',
        'mae': None,
        'r2': None,
        'avg_daily_usage': 0.0,
        'days_remaining': None,
        'runout_date': None,
        'reorder_date': None,
    }

    if current_stock <= 0:
        today = date.today()
        out.update(days_remaining=0, runout_date=today, reorder_date=today)
        return out

    recent = series[-7:] if len(series) >= 7 else series
    avg = float(np.mean(recent)) if len(recent) else 0.0

    # Fallback: not enough signal
    nonzero = int((series > 0).sum())
    if nonzero < 5:
        out['avg_daily_usage'] = round(avg, 3)
        if avg > 0:
            days = int(current_stock / avg)
            out['days_remaining'] = days
            out['runout_date'] = date.today() + timedelta(days=days)
            out['reorder_date'] = date.today() + timedelta(days=max(0, days - 5))
        return out

    X, y = _make_features(series)
    if len(X) < 6:
        out['avg_daily_usage'] = round(avg, 3)
        if avg > 0:
            days = int(current_stock / avg)
            out['days_remaining'] = days
            out['runout_date'] = date.today() + timedelta(days=days)
            out['reorder_date'] = date.today() + timedelta(days=max(0, days - 5))
        return out

    split = max(1, len(X) - 3)
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]

    try:
        model = RandomForestRegressor(n_estimators=60, random_state=42)
        model.fit(X_tr, y_tr)
        preds = model.predict(X_te)
        mae = float(mean_absolute_error(y_te, preds))
        r2 = float(r2_score(y_te, preds)) if len(y_te) > 1 else None
        last = [series[-l] for l in (1, 2, 3, 7)]
        nxt = float(model.predict([last])[0])
        nxt = max(0.0, nxt)
        avg = nxt if nxt > 0 else avg
        out['model'] = 'RandomForest'
        out['mae'] = round(mae, 3)
        out['r2'] = round(r2, 3) if r2 is not None else None
    except Exception:
        out['model'] = 'moving-average'

    out['avg_daily_usage'] = round(avg, 3)
    if avg > 0:
        days = int(current_stock / avg)
        out['days_remaining'] = days
        out['runout_date'] = date.today() + timedelta(days=days)
        out['reorder_date'] = date.today() + timedelta(days=max(0, days - 5))
    return out