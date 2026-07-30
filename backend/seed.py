#!/usr/bin/python
"""Seed 200 synthetic equipment records + usage logs (direct psycopg2)"""
import random
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta

CONN_STRING = "postgresql://neondb_owner:npg_5mxl1ASwDVvb@ep-wispy-cake-ax2q5ud6-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

SITES = [f"S00{i}" for i in range(1, 10)] + ["S010"]
EQUIPMENT_TYPES = ["Excavator", "Crane", "Bulldozer", "Grader", "Wheel Loader", "Backhoe", "Dump Truck"]
OPERATORS = [f"OP{i:03d}" for i in range(100, 151)]

TYPE_BEHAVIOR = {
    "Excavator":    {"base_engine": 8, "base_idle": 2, "fuel_rate": 18},
    "Crane":        {"base_engine": 9, "base_idle": 3.5, "fuel_rate": 12},
    "Bulldozer":    {"base_engine": 10, "base_idle": 1.5, "fuel_rate": 22},
    "Grader":       {"base_engine": 6, "base_idle": 2, "fuel_rate": 14},
    "Wheel Loader": {"base_engine": 7, "base_idle": 2.5, "fuel_rate": 16},
    "Backhoe":      {"base_engine": 6, "base_idle": 3, "fuel_rate": 13},
    "Dump Truck":   {"base_engine": 8, "base_idle": 4, "fuel_rate": 20},
}


def main():
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor()

    for i in range(1, 201):
        eid = f"CAT-EQ-{i:04d}"
        etype = random.choice(EQUIPMENT_TYPES)
        bhv = TYPE_BEHAVIOR[etype]
        site = random.choice(SITES)
        operator = random.choice(OPERATORS)
        check_in = datetime.now() - timedelta(days=random.randint(1, 180), hours=random.randint(0, 23))
        days_active = random.randint(5, 90)
        daily_engine = round(random.uniform(bhv["base_engine"] - 2, bhv["base_engine"] + 3), 1)
        daily_idle = round(random.uniform(bhv["base_idle"] - 1, bhv["base_idle"] + 2), 1)

        # Inject anomalies: ~5% NULL operator or NULL site
        null_operator = random.random() < 0.05
        null_site = random.random() < 0.05

        total_engine = round(daily_engine * days_active, 1)
        total_idle = round(daily_idle * days_active, 1)
        total_fuel = round(total_engine * bhv["fuel_rate"], 1)
        daily_rate = round(random.uniform(200, 1200), 2)

        overdue = random.random() < 0.1
        status = "overdue" if overdue else "checked_in"

        cur.execute("""
            INSERT INTO equipment (equipment_id, equipment_type, site_id, operator_id,
                check_in_time, engine_hours, idle_hours, fuel_used, status, rental_cost, daily_rental_rate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (eid, etype,
              None if null_site else site,
              None if null_operator else operator,
              check_in, total_engine, total_idle, total_fuel,
              status, round(daily_rate * days_active, 2), daily_rate))

        # Generate 30 days of usage logs per equipment
        for d in range(min(days_active, 30)):
            date = check_in + timedelta(days=d)
            cur.execute("""
                INSERT INTO usage_logs (equipment_id, date, engine_hours, idle_hours, fuel_used, location_lat, location_lng)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (eid, date,
                  round(random.uniform(bhv["base_engine"] - 2, bhv["base_engine"] + 3), 1),
                  round(random.uniform(bhv["base_idle"] - 1, bhv["base_idle"] + 2), 1),
                  round(random.uniform(8, 25), 1),
                  round(random.uniform(12.8, 13.2), 4),
                  round(random.uniform(77.4, 77.8), 4)))

        if i % 50 == 0:
            print(f"  Seeded {i}/200...")
            conn.commit()

    conn.commit()
    print("✅ Seeded 200 equipment + usage logs to Neon PostgreSQL")

    # Verify
    cur.execute("SELECT COUNT(*) FROM equipment")
    eq_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM usage_logs")
    log_count = cur.fetchone()[0]
    print(f"   Equipment: {eq_count}, Usage Logs: {log_count}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
