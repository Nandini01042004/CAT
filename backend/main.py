#!/usr/bin/env python3
"""Smart Rental Tracking — FastAPI Backend (all 6 modules + extension workflow)"""
from datetime import datetime, date, timedelta
import os
import random
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import query, execute

app = FastAPI(title="CAT Smart Rental Tracking")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@app.on_event("startup")
def startup():
    """Force DB connection at boot — pays the 19s Neon cold start once."""
    try:
        query("SELECT 1")
        print("✓ DB connected at startup (cold start paid)")
    except Exception as e:
        print(f"⚠ DB startup connection failed: {e}")

# ─── Helpers ──────────────────────────────────────────────────────────────

def fmt_val(d, key, default=0):
    return d[key] if d and d.get(key) is not None else default

# ─── Dashboard / Stats ──────────────────────────────────────────────────

@app.get("/api/dashboard/stats")
def dashboard():
    total = query("SELECT COUNT(*) FROM equipment")
    in_use = query("SELECT COUNT(*) FROM equipment WHERE status='checked_in'")
    free = query("SELECT COUNT(*) FROM equipment WHERE status='checked_out'")
    overdue = query("SELECT COUNT(*) FROM equipment WHERE status='overdue'")
    total_eng = query("SELECT COALESCE(SUM(engine_hours), 0) FROM equipment")
    total_idle = query("SELECT COALESCE(SUM(idle_hours), 0) FROM equipment")
    total_fuel = query("SELECT COALESCE(SUM(fuel_used), 0) FROM equipment")
    total_cost = query("SELECT COALESCE(SUM(rental_cost), 0) FROM equipment")
    by_type = query("SELECT equipment_type, COUNT(*) as cnt FROM equipment GROUP BY equipment_type")
    by_site = query("SELECT site_id, COUNT(*) as cnt FROM equipment WHERE site_id IS NOT NULL GROUP BY site_id")

    # Last known locations (in-use)
    locs = query("""
        SELECT equipment_id, equipment_type, site_id, operator_id,
               check_in_time, check_out_time
        FROM equipment WHERE status='checked_in'
        ORDER BY check_in_time DESC LIMIT 20
    """)

    return {
        "total": total[0]["count"] if total else 0,
        "in_use": in_use[0]["count"] if in_use else 0,
        "free": free[0]["count"] if free else 0,
        "overdue": overdue[0]["count"] if overdue else 0,
        "total_engine_hours": round(total_eng[0]["coalesce"], 1),
        "total_idle_hours": round(total_idle[0]["coalesce"], 1),
        "total_fuel": round(total_fuel[0]["coalesce"], 1),
        "total_cost": round(total_cost[0]["coalesce"], 2),
        "by_type": by_type,
        "by_site": by_site,
        "last_locations": locs,
    }

# ─── Dashboard — all equipment list (live status) ─────────────────────────

@app.get("/api/equipment")
def list_equipment(site: str = "", type: str = "", status: str = "", page: int = 1, per_page: int = 50):
    conditions = []
    params = []
    if site:
        conditions.append("site_id=%s")
        params.append(site)
    if type:
        conditions.append("equipment_type=%s")
        params.append(type)
    # status: 'in_use' = check_in present, check_out null. 'free' = both present
    if status == "in_use":
        conditions.append("status='checked_in'")
    elif status == "free":
        conditions.append("status='checked_out'")
    elif status == "overdue":
        conditions.append("status='overdue'")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * per_page
    rows = query(f"SELECT * FROM equipment {where} ORDER BY id LIMIT %s OFFSET %s", params + [per_page, offset])
    total = query(f"SELECT COUNT(*) FROM equipment {where}", params)
    return {"data": rows, "total": total[0]["count"] if total else 0}

@app.get("/api/equipment/{eid}")
def get_equip(eid: str):
    r = query("SELECT * FROM equipment WHERE equipment_id=%s", [eid])
    if not r: raise HTTPException(404)
    return r[0]

# ─── Check-in (like library borrow) ──────────────────────────────────────

class CheckInReq(BaseModel):
    customer_id: str
    site_id: str
    operator_id: str
    daily_rate: float = 500
    rental_days: int = 30

@app.post("/api/equipment/{eid}/checkin")
def check_in(eid: str, req: CheckInReq):
    now = datetime.now()
    execute("""
        UPDATE equipment SET check_in_time=%s, site_id=%s, operator_id=%s,
            daily_rental_rate=%s, status='checked_in', customer_id=%s
        WHERE equipment_id=%s
    """, [now, req.site_id, req.operator_id, req.daily_rate, req.customer_id, eid])
    # Log in rental history
    execute("""
        INSERT INTO rental_history (equipment_id, customer_id, operator_id, site_id,
            check_out_date, expected_return_date, engine_hours, idle_hours, fuel_used,
            rental_cost, status)
        VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 0, %s, 'active')
    """, [eid, req.customer_id, req.operator_id, req.site_id, now,
          now + timedelta(days=req.rental_days), req.daily_rate * req.rental_days * 0])
    return {"message": f"{eid} checked in — assigned to {req.customer_id}"}

# ─── Check-out (return) with QR simulation ───────────────────────────────

@app.post("/api/equipment/{eid}/checkout")
def check_out(eid: str):
    now = datetime.now()
    eq = query("SELECT * FROM equipment WHERE equipment_id=%s", [eid])
    if not eq or eq[0].get("status") == 'checked_out':
        raise HTTPException(400, "Already checked out or never checked in")
    execute("UPDATE equipment SET check_out_time=%s, status='checked_out' WHERE equipment_id=%s", [now, eid])
    # Update the active rental history
    execute("""
        UPDATE rental_history SET actual_return_date=%s, status='completed'
        WHERE equipment_id=%s AND status='active'
    """, [now, eid])
    return {"message": f"{eid} checked out (returned)"}

# ─── Extension Request (rental → owner approve) ──────────────────────────

class ExtensionReq(BaseModel):
    customer_id: str
    new_return_date: str
    reason: str = ""

@app.post("/api/equipment/{eid}/extend")
def request_extension(eid: str, req: ExtensionReq):
    eq = query("SELECT * FROM equipment WHERE equipment_id=%s", [eid])
    if not eq: raise HTTPException(404)
    expected = eq[0].get("check_out_time")
    new_date = datetime.strptime(req.new_return_date, "%Y-%m-%d")
    execute("""
        INSERT INTO extension_requests (equipment_id, customer_id, original_return_date,
            requested_new_return_date, reason, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
    """, [eid, req.customer_id, expected, new_date, req.reason])
    return {"message": "Extension submitted — awaiting owner approval"}

@app.post("/api/extensions/{ext_id}/respond")
def respond_extension(ext_id: int, approve: bool = False):
    if approve:
        ext = query("SELECT * FROM extension_requests WHERE id=%s", [ext_id])
        if not ext: raise HTTPException(404)
        execute("UPDATE extension_requests SET status='approved', owner_response='Approved' WHERE id=%s", [ext_id])
        # Update equipment return date
        execute("UPDATE equipment SET check_out_time=%s WHERE id=%s",
                [ext[0]["requested_new_return_date"], ext[0]["equipment_id"]])
        return {"message": "Extension approved"}
    execute("UPDATE extension_requests SET status='rejected', owner_response='Rejected' WHERE id=%s", [ext_id])
    return {"message": "Extension rejected"}

@app.get("/api/extensions")
def list_extensions(status: str = "pending"):
    rows = query("SELECT * FROM extension_requests WHERE status=%s", [status])
    return {"data": rows}

# ─── Usage Logs ─────────────────────────────────────────────────────────

@app.get("/api/equipment/{eid}/usage")
def get_usage(eid: str):
    rows = query("SELECT * FROM usage_logs WHERE equipment_id=%s ORDER BY date DESC LIMIT 60", [eid])
    return {"data": rows}

@app.get("/api/usage/summary")
def usage_summary(days: int = 30):
    rows = query("""
        SELECT equipment_id, equipment_type,
               SUM(engine_hours) as total_engine, SUM(idle_hours) as total_idle,
               SUM(fuel_used) as total_fuel
        FROM usage_logs u JOIN equipment e USING (equipment_id)
        WHERE date >= NOW() - INTERVAL '%s days'::INTERVAL
        GROUP BY equipment_id, equipment_type
        ORDER BY total_engine DESC
    """, [days])
    return {"data": rows}

# ─── Overdue Alerts ──────────────────────────────────────────────────────

@app.get("/api/alerts")
def alerts():
    overdue = query("SELECT * FROM equipment WHERE status='overdue' ORDER BY check_out_time ASC")
    upcoming = query("SELECT * FROM equipment WHERE check_out_time IS NOT NULL AND check_out_time BETWEEN NOW() AND NOW() + INTERVAL '3 days' ORDER BY check_out_time ASC")
    in_use = query("SELECT * FROM equipment WHERE status='checked_in' ORDER BY check_in_time DESC LIMIT 10")
    return {
        "overdue": overdue,
        "upcoming_return": upcoming,
        "in_use": in_use,
        "overdue_count": len(overdue),
    }

# ─── Customer-based Demand Forecast ──────────────────────────────────────

@app.get("/api/forecast")
def forecast():
    try:
        from forecast import generate_forecast
        preds = generate_forecast(days_ahead=14)
        return {"predictions": preds, "model": "xgboost"}
    except Exception as e:
        print(f"Forecast error: {e}")
        return {"predictions": [], "model": "xgboost", "error": str(e)}

# ─── Anomaly Detection ────────────────────────────────────────────────────

@app.get("/api/anomalies")
def get_anomalies():
    anomalies = []
    rows = query("SELECT * FROM equipment")
    for eq in rows:
        reasons = []
        engine = float(fmt_val(eq, "engine_hours"))
        idle = float(fmt_val(eq, "idle_hours"))
        # 1. Idle > engine → excessive
        if engine > 0 and idle > engine * 1.5:
            reasons.append(f"Excessive idle ({idle:.1f}h vs {engine:.1f}h engine)")
        # 2. No operator
        if not eq.get("operator_id"):
            reasons.append("No operator assigned")
        # 3. No site
        if not eq.get("site_id"):
            reasons.append("No site assignment")
        # 4. In use but no usage logs
        logs = query("SELECT COUNT(*) FROM usage_logs WHERE equipment_id=%s", [eq["equipment_id"]])
        if eq["status"] == 'checked_in' and (not logs or logs[0]["count"] == 0):
            reasons.append("Checked in but zero usage recorded")
        # 5. Overdue
        if eq.get("status") == 'overdue':
            reasons.append("Overdue — past return date")
        if reasons:
            eq["anomalies"] = reasons
            eq["severity"] = "high" if any("Overdue" in r or "Excessive" in r for r in reasons) else "medium"
            anomalies.append(dict(eq))
    return {"count": len(anomalies), "data": anomalies}

# ─── Chatbot (AI agent) ────────────────────────────────────────────────────

@app.get("/api/chat")
def chat(q: str = ""):
    ql = q.lower()
    if "overdue" in ql:
        r = query("SELECT * FROM equipment WHERE check_out_time IS NOT NULL AND check_out_time < NOW()")
        return {"answer": f"Alert: {len(r)} overdue equipment. Review below.", "data": r}
    elif "idle" in ql or "waste" in ql:
        r = query("SELECT * FROM equipment ORDER BY idle_hours DESC LIMIT 10")
        return {"answer": "Top 10 by idle hours (potential waste).", "data": r}
    elif "engine" in ql or "running" in ql:
        r = query("SELECT * FROM equipment ORDER BY engine_hours DESC LIMIT 10")
        return {"answer": "Top 10 by engine hours (most utilized).", "data": r}
    elif "fuel" in ql:
        r = query("SELECT * FROM equipment ORDER BY fuel_used DESC LIMIT 10")
        return {"answer": "Top 10 by fuel consumption.", "data": r}
    elif "extend" in ql or "extension" in ql:
        r = query("SELECT * FROM extension_requests WHERE status='pending'")
        return {"answer": f"{len(r)} pending extension requests.", "data": r}
    elif "customer" in ql or "repeat" in ql:
        r = query("SELECT * FROM customers ORDER BY total_rentals DESC LIMIT 10")
        return {"answer": "Top 10 customers by rental activity.", "data": r}
    elif "anomal" in ql:
        r = get_anomalies()
        return {"answer": f"Detected {r['count']} anomalies.", "data": r['data']}
    elif "all" in ql or "stats" in ql or "summary" in ql:
        return dashboard()
    elif "site" in ql:
        r = query("SELECT site_id, COUNT(*) FROM equipment GROUP BY site_id")
        return {"answer": f"Equipment across {len(r)} sites.", "data": r}
    elif "cost" in ql or "rental" in ql:
        r = query("SELECT * FROM equipment ORDER BY rental_cost DESC LIMIT 10")
        return {"answer": "Top 10 by rental cost.", "data": r}
    elif "forecast" in ql or "demand" in ql:
        r = forecast()
        return {"answer": "Demand forecast based on site/type.", "data": r["predictions"]}
    elif "free" in ql or "available" in ql:
        r = query("SELECT * FROM equipment WHERE check_in_time IS NOT NULL AND check_out_time IS NOT NULL")
        return {"answer": f"{len(r)} equipment available for rent.", "data": r}
    elif "in use" in ql or "rented" in ql:
        r = query("SELECT * FROM equipment WHERE check_in_time IS NOT NULL AND check_out_time IS NULL")
        return {"answer": f"{len(r)} equipment currently in use.", "data": r}
    elif "location" in ql or "near" in ql or "proximity" in ql:
        r = query("SELECT * FROM equipment WHERE operator_id IS NOT NULL LIMIT 20")
        return {"answer": "Last known locations fetched.", "data": r}
    else:
        return {"answer": "Try: 'overdue', 'idle', 'engine', 'fuel', 'anomalies', 'extension', 'customer', 'in use', 'available', 'forecast', 'all stats'", "data": []}

# ─── Serve Frontend ──────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
