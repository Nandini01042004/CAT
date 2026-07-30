"""Anomaly detection logic"""
from datetime import datetime, timedelta
from database import SessionLocal, Equipment


def detect_anomalies():
    session = SessionLocal()
    anomalies = []
    try:
        records = session.query(Equipment).all()
        for eq in records:
            reasons = []

            # 1. NULL operator with equipment checked in
            if eq.operator_id is None and eq.status == "checked_in":
                reasons.append("No operator assigned")

            # 2. NULL site
            if eq.site_id is None and eq.status == "checked_in":
                reasons.append("Not assigned to any site")

            # 3. Excessive idle (idle > 2x engine hours)
            if eq.engine_hours > 0 and eq.idle_hours > eq.engine_hours * 2:
                reasons.append(f"Excessive idle ({eq.idle_hours}h vs {eq.engine_hours}h engine)")

            # 4. Overdue
            if eq.status == "overdue":
                reasons.append("Overdue — past return date")

            # 5. Zero usage but checked in
            if eq.engine_hours == 0 and eq.idle_hours == 0 and eq.status == "checked_in":
                reasons.append("Checked in but zero usage recorded")

            if reasons:
                anomalies.append({
                    "id": eq.id,
                    "equipment_id": eq.equipment_id,
                    "type": eq.equipment_type,
                    "site_id": eq.site_id,
                    "operator_id": eq.operator_id,
                    "anomalies": reasons,
                    "severity": "high" if any(r in reasons for r in ["Overdue", "Excessive idle"]) else "medium",
                })
    finally:
        session.close()
    return anomalies
