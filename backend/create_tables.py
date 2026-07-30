#!/usr/bin/python
"""Create tables — matching your psycopg2 pattern"""
import psycopg2

CONN_STRING = "postgresql://neondb_owner:npg_5mxl1ASwDVvb@ep-wispy-cake-ax2q5ud6-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment (
    id SERIAL PRIMARY KEY,
    equipment_id VARCHAR(20) UNIQUE NOT NULL,
    equipment_type VARCHAR(50) NOT NULL,
    site_id VARCHAR(20),
    operator_id VARCHAR(20),
    check_in_time TIMESTAMP,
    check_out_time TIMESTAMP,
    engine_hours FLOAT DEFAULT 0,
    idle_hours FLOAT DEFAULT 0,
    fuel_used FLOAT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'checked_out',
    rental_cost FLOAT DEFAULT 0,
    daily_rental_rate FLOAT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS usage_logs (
    id SERIAL PRIMARY KEY,
    equipment_id VARCHAR(20) NOT NULL,
    date TIMESTAMP NOT NULL,
    engine_hours FLOAT DEFAULT 0,
    idle_hours FLOAT DEFAULT 0,
    fuel_used FLOAT DEFAULT 0,
    location_lat FLOAT,
    location_lng FLOAT
);

CREATE INDEX IF NOT EXISTS idx_equipment_id ON equipment(equipment_id);
CREATE INDEX IF NOT EXISTS idx_usage_equipment_id ON usage_logs(equipment_id);
"""

def main():
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor()
    # Drop existing tables if re-running
    cur.execute("DROP TABLE IF EXISTS usage_logs CASCADE;")
    cur.execute("DROP TABLE IF EXISTS equipment CASCADE;")
    cur.execute(SCHEMA)
    conn.commit()
    print("✅ Tables created: equipment, usage_logs")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
