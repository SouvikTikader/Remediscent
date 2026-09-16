"""Anomaly detection, adherence scoring, refill optimizer."""
from datetime import date, timedelta
from collections import defaultdict
import numpy as np


def detect_anomalies(records, window=14, threshold=2.0):
    """
    Z-score based anomaly detection on daily consumption.
    Returns list of {date, quantity, zscore} for outlier days.
    """
    if not records or len(records) < 5:
        return []

    bucket = defaultdict(int)
    for r in records:
        bucket[r.date] += r.quantity_used

    series = sorted(bucket.items())  # [(date, qty), ...]
    if len(series) < 5:
        return []

    values = np.array([v for _, v in series], dtype=float)
    mean = float(np.mean(values))
    std = float(np.std(values)) or 1.0

    anomalies = []
    for d, v in series:
        z = (v - mean) / std
        if abs(z) >= threshold:
            anomalies.append({
                'date': d,
                'quantity': v,
                'zscore': round(z, 2),
                'direction': 'high' if z > 0 else 'low',
            })
    return anomalies[-5:]  # last 5 only


def compute_adherence(medicine, records, lookback_days=30):
    """
    Adherence rate = actual doses taken / expected doses.
    Expected = daily_usage * days since first record (capped at lookback).
    """
    if not records:
        return {
            'rate': None,
            'expected': 0.0,
            'actual': 0.0,
            'days_tracked': 0,
            'label': 'No data',
        }

    cutoff = date.today() - timedelta(days=lookback_days)
    recent = [r for r in records if r.date >= cutoff]
    if not recent:
        return {'rate': None, 'expected': 0.0, 'actual': 0.0,
                'days_tracked': 0, 'label': 'No data'}

    first = min(r.date for r in recent)
    days_tracked = (date.today() - first).days + 1
    expected = float(medicine.daily_usage or 1.0) * days_tracked
    actual = float(sum(r.quantity_used for r in recent))

    rate = min(1.0, actual / expected) if expected > 0 else None

    if rate is None:
        label = 'No data'
    elif rate >= 0.9:
        label = 'Excellent'
    elif rate >= 0.75:
        label = 'Good'
    elif rate >= 0.5:
        label = 'Poor'
    else:
        label = 'Critical'

    return {
        'rate': round(rate, 3) if rate is not None else None,
        'expected': round(expected, 1),
        'actual': round(actual, 1),
        'days_tracked': days_tracked,
        'label': label,
    }


def optimize_refills(medicines, horizon_days=14):
    """
    Group medicines running out within `horizon_days` into a single
    refill plan, sorted by urgency.
    """
    today = date.today()
    urgent = []

    for m in medicines:
        if not m.daily_usage or m.daily_usage <= 0:
            continue
        days_left = int(m.quantity / m.daily_usage) if m.daily_usage else None
        if days_left is None:
            continue
        runout = today + timedelta(days=days_left)
        if days_left <= horizon_days:
            urgent.append({
                'medicine': m.name,
                'member': m.member.name,
                'days_left': days_left,
                'runout_date': runout,
                'quantity': m.quantity,
                'urgency': 'CRITICAL' if days_left <= 3 else
                           'HIGH' if days_left <= 7 else 'MEDIUM',
            })

    urgency_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2}
    urgent.sort(key=lambda x: (urgency_order[x['urgency']], x['days_left']))

    # Group by suggested trip (next 3 days vs this week vs this fortnight)
    trip_groups = {'Immediate (≤3 days)': [], 'This week (4–7 days)': [],
                   'Next week (8–14 days)': []}
    for item in urgent:
        if item['days_left'] <= 3:
            trip_groups['Immediate (≤3 days)'].append(item)
        elif item['days_left'] <= 7:
            trip_groups['This week (4–7 days)'].append(item)
        else:
            trip_groups['Next week (8–14 days)'].append(item)

    return {
        'items': urgent,
        'groups': {k: v for k, v in trip_groups.items() if v},
        'total_trips': sum(1 for v in trip_groups.values() if v),
    }