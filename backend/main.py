#!/usr/bin/env python3
"""Smart Rental Tracking — FastAPI Backend (all 6 modules)"""
from datetime import datetime, timedelta
import os
import random
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from db import query, execute

app = FastAPI(title="CAT Smart Rental Tracking")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# ─── AI Chatbot State ────────────────────────────────────────────────

@app.get("/api/chat")
def chat(q: str = ""):
    """Simple AI agent: natural language queries about equipment data"""
    ql = q.lower()
    if "overdue" in ql or "over due" in ql or "alerts" in ql:
        rows = query("SELECT equipment_id, equipment_type, site_id, rental_cost FROM equipment WHERE status='overdue'")
        if not rows:
            return {"answer": "No overdue equipment currently.", "data": []}
        return {"answer": f"Found {len(rows)} overdue equipment.", "data": rows}
    elif "idle" in ql or "waste" in ql:
        rows = query("SELECT equipment_id, equipment_type, idle_hours, engine_hours FROM equipment ORDER BY idle_hours DESC LIMIT 10")
        total_idle = sum(r["idle_hours"] for r in rows)
        return {"answer": f"Top 10 highest idle equipment. Total idle: {total_idle:.1f}h", "data": rows}
    elif "engine" in ql or "running" in ql or "runtime" in ql:
        rows = query("SELECT equipment_id, equipment_type, engine_hours FROM equipment ORDER BY engine_hours DESC LIMIT 10")
        return {"answer": "Top 10 by engine hours (most working time).", "data": rows}
    elif "fuel" in ql:
        rows = query("SELECT equipment_id, equipment_type, fuel_used FROM equipment ORDER BY fuel_used DESC LIMIT 10")
        return {"answer": "Top 10 by fuel consumption.", "data": rows}
    elif "all" in ql or "summary" in ql or "stats" in ql or "dashboard" in ql:
        return get_dashboard_stats()
    elif "site" in ql:
        rows = query("SELECT site_id, COUNT(*) as count FROM equipment WHERE site_id IS NOT NULL GROUP BY site_id")
        return {"answer": f"Equipment distribution across {len(rows)} sites.", "data": rows}
    elif "cost" in ql or "rental" in ql or "expensive" in ql:
        rows = query("SELECT equipment_id, equipment_type, rental_cost, daily_rental_rate FROM equipment ORDER BY rental_cost DESC LIMIT 10")
        return {"answer": "Top 10 by rental cost so far.", "data": rows}
    else:
        return {"answer": "Try: 'overdue', 'idle usage', 'engine hours', 'fuel', 'sites', 'rental cost', 'all stats'", "data": []}


# ─── Dashboard ───────────────────────────────────────────────────────

@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    total = query("SELECT COUNT(*) FROM equipment")
    checked_in = query("SELECT COUNT(*) FROM equipment WHERE status='checked_in'")
    overdue = query("SELECT COUNT(*) FROM equipment WHERE status='overdue'")
    total_engine = query("SELECT COALESCE(SUM(engine_hours), 0) FROM equipment")
    total_idle = query("SELECT COALESCE(SUM(idle_hours), 0) FROM equipment")
    total_fuel = query("SELECT COALESCE(SUM(fuel_used), 0) FROM equipment")
    total_cost = query("SELECT COALESCE(SUM(rental_cost), 0) FROM equipment")
    by_type = query("SELECT equipment_type, COUNT(*) FROM equipment GROUP BY equipment_type ORDER BY COUNT(*) DESC")
    by_site = query("SELECT site_id, COUNT(*) FROM equipment WHERE site_id IS NOT NULL GROUP BY site_id ORDER BY COUNT(*) DESC")

    return {
        "answer": "Dashboard stats retrieved.",
        "data": {
            "total": total[0]["count"] if total else 0,
            "checked_in": checked_in[0]["count"] if checked_in else 0,
            "overdue": overdue[0]["count"] if overdue else 0,
            "total_engine_hours": round(total_engine[0]["coalesce"] if total_engine else 0, 1),
            "total_idle_hours": round(total_idle[0]["coalesce"] if total_idle else 0, 1),
            "total_fuel_used": round(total_fuel[0]["coalesce"] if total_fuel else 0, 1),
            "total_rental_cost": round(total_cost[0]["coalesce"] if total_cost else 0, 2),
            "by_type": by_type,
            "by_site": by_site,
        }
    }


# ─── Equipment / Check-in / Check-out ────────────────────────────────

@app.get("/api/equipment")
def list_equipment(site: str = "", status: str = "", type: str = "", page: int = 1, per_page: int = 50):
    conditions = []
    params = []
    if site:
        conditions.append("site_id=%s")
        params.append(site)
    if status:
        conditions.append("status=%s")
        params.append(status)
    if type:
        conditions.append("equipment_type=%s")
        params.append(type)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * per_page
    rows = query(f"SELECT * FROM equipment {where} ORDER BY id LIMIT %s OFFSET %s", params + [per_page, offset])
    total = query(f"SELECT COUNT(*) FROM equipment {where}", params)
    return {"data": rows, "total": total[0]["count"] if total else 0, "page": page}


@app.get("/api/equipment/{eid}")
def get_equipment(eid: str):
    rows = query("SELECT * FROM equipment WHERE equipment_id=%s", [eid])
    if not rows:
        raise HTTPException(404, "Not found")
    return rows[0]


class CheckInRequest(BaseModel):
    site_id: str
    operator_id: str
    daily_rental_rate: float = 500.0


@app.post("/api/equipment/{eid}/checkin")
def check_in(eid: str, req: CheckInRequest):
    now = datetime.now()
    execute("UPDATE equipment SET site_id=%s, operator_id=%s, status='checked_in', check_in_time=%s, daily_rental_rate=%s WHERE equipment_id=%s",
            [req.site_id, req.operator_id, now, req.daily_rental_rate, eid])
    return {"message": f"{eid} checked in", "site": req.site_id, "operator": req.operator_id}


@app.post("/api/equipment/{eid}/checkout")
def check_out(eid: str):
    execute("UPDATE equipment SET status='checked_out', check_out_time=%s WHERE equipment_id=%s",
            [datetime.now(), eid])
    return {"message": f"{eid} checked out"}


@app.get("/api/equipment/{eid}/usage")
def get_usage(eid: str):
    rows = query("SELECT * FROM usage_logs WHERE equipment_id=%s ORDER BY date DESC LIMIT 60", [eid])
    return {"data": rows}


# ─── Usage Summary ───────────────────────────────────────────────────

@app.get("/api/usage/summary")
def usage_summary(days: int = 30):
    rows = query("""
        SELECT equipment_id, equipment_type,
               SUM(engine_hours) as total_engine, SUM(idle_hours) as total_idle,
               SUM(fuel_used) as total_fuel
        FROM usage_logs u JOIN equipment e USING (equipment_id)
        WHERE date >= NOW() - INTERVAL '%s days'
        GROUP BY equipment_id, equipment_type
        ORDER BY total_engine DESC
    """, [days])
    return {"data": rows}


# ─── Overdue Alerts ──────────────────────────────────────────────────

@app.get("/api/alerts")
def get_alerts():
    overdue = query("SELECT * FROM equipment WHERE status='overdue' ORDER BY rental_cost DESC")
    active = query("SELECT * FROM equipment WHERE status='checked_in' ORDER BY check_in_time ASC LIMIT 5")
    return {
        "overdue": overdue,
        "latest_checkins": active,
        "overdue_count": len(overdue),
        "message": f"{len(overdue)} equipment overdue",
    }


# ─── Demand Forecast (mock time-series) ──────────────────────────────

@app.get("/api/forecast")
def forecast():
    """Simple mock forecast: which types likely needed where based on past usage"""
    by_type_site = query("""
        SELECT equipment_type, site_id, COUNT(*) as cnt
        FROM equipment
        WHERE site_id IS NOT NULL
        GROUP BY equipment_type, site_id
        ORDER BY cnt DESC
        LIMIT 20
    """)
    today = datetime.now()
    predictions = []
    for row in by_type_site:
        pred = row.copy()
        pred["forecast_needed"] = max(1, int(row["cnt"] * (0.8 + 0.4 * random.random())))
        pred["next_week_demand"] = f"{pred['forecast_needed']}+ units"
        predictions.append(pred)

    # Site-level demand
    site_demand = query("""
        SELECT site_id, COUNT(*) as current, SUM(engine_hours) as total_engine
        FROM equipment WHERE site_id IS NOT NULL
        GROUP BY site_id
    """)
    return {"predictions": predictions, "site_demand": site_demand}


# ─── Anomaly Detection ───────────────────────────────────────────────

@app.get("/api/anomalies")
def get_anomalies():
    # Inline anomaly detection (replaces anomaly.py import)
    anomalies = []
    rows = query("SELECT * FROM equipment")

    for eq in rows:
        reasons = []

        if eq.get("operator_id") is None and eq["status"] == "checked_in":
            reasons.append("No operator assigned")

        if eq.get("site_id") is None and eq["status"] == "checked_in":
            reasons.append("Not assigned to any site")

        engine = eq.get("engine_hours", 0) or 0
        idle = eq.get("idle_hours", 0) or 0
        if engine > 0 and idle > engine * 2:
            reasons.append(f"Excessive idle ({idle}h vs {engine}h engine)")

        if eq["status"] == "overdue":
            reasons.append("Overdue — past return date")

        if engine == 0 and idle == 0 and eq["status"] == "checked_in":
            reasons.append("Checked in but zero usage recorded")

        if reasons:
            eq["anomalies"] = reasons
            eq["severity"] = "high" if any(r in reasons for r in ["Overdue", "Excessive idle"]) else "medium"
            anomalies.append(eq)

    return {"count": len(anomalies), "data": anomalies}


# ─── Serve frontend (after all API routes) ───────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ─── Run ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
