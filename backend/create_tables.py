"""Schema creation — exact format per problem statement"""
import psycopg2

CONN = "postgresql://neondb_owner:npg_5mxl1ASwDVvb@ep-wispy-cake-ax2q5ud6-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

def main():
    conn = psycopg2.connect(CONN)
    cur = conn.cursor()

    # Drop in correct order (foreign keys)
    cur.execute("DROP TABLE IF EXISTS extension_requests CASCADE")
    cur.execute("DROP TABLE IF EXISTS rental_history CASCADE")
    cur.execute("DROP TABLE IF EXISTS usage_logs CASCADE")
    cur.execute("DROP TABLE IF EXISTS equipment CASCADE")
    cur.execute("DROP TABLE IF EXISTS customers CASCADE")

    # ─── Equipment (exact format from problem statement) ───
    cur.execute("""
        CREATE TABLE equipment (
            id SERIAL PRIMARY KEY,
            equipment_id VARCHAR(32) UNIQUE NOT NULL,
            equipment_type VARCHAR(64) NOT NULL,
            site_id VARCHAR(32),
            check_in_date DATE,
            check_out_date DATE,
            engine_hours_per_day NUMERIC(6,2) DEFAULT 0,
            idle_hours_per_day NUMERIC(6,2) DEFAULT 0,
            rental_days INT DEFAULT 0,
            last_operator_id VARCHAR(32),
            current_location_lat NUMERIC(10,6),
            current_location_lng NUMERIC(10,6),
            fuel_used NUMERIC(10,2) DEFAULT 0,
            total_engine_hours NUMERIC(10,2) DEFAULT 0,
            total_idle_hours NUMERIC(10,2) DEFAULT 0,
            rental_cost NUMERIC(12,2) DEFAULT 0,
            daily_rental_rate NUMERIC(8,2) DEFAULT 500.00,
            customer_id VARCHAR(32),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ─── Customers (for repeat-renter forecasting) ───
    cur.execute("""
        CREATE TABLE customers (
            customer_id VARCHAR(32) PRIMARY KEY,
            customer_name VARCHAR(128),
            company VARCHAR(128),
            contact_email VARCHAR(128),
            contact_phone VARCHAR(32),
            total_rentals INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ─── Rental history (full lifecycle per rental) ───
    cur.execute("""
        CREATE TABLE rental_history (
            id SERIAL PRIMARY KEY,
            equipment_id VARCHAR(32) NOT NULL,
            customer_id VARCHAR(32),
            operator_id VARCHAR(32),
            site_id VARCHAR(32),
            check_out_date DATE,
            expected_return_date DATE,
            actual_return_date DATE,
            engine_hours NUMERIC(10,2) DEFAULT 0,
            idle_hours NUMERIC(10,2) DEFAULT 0,
            fuel_used NUMERIC(10,2) DEFAULT 0,
            rental_cost NUMERIC(12,2) DEFAULT 0,
            location_lat NUMERIC(10,6),
            location_lng NUMERIC(10,6),
            status VARCHAR(32) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ─── Usage logs (daily detail) ───
    cur.execute("""
        CREATE TABLE usage_logs (
            id SERIAL PRIMARY KEY,
            equipment_id VARCHAR(32) NOT NULL,
            log_date DATE NOT NULL,
            engine_hours NUMERIC(6,2) DEFAULT 0,
            idle_hours NUMERIC(6,2) DEFAULT 0,
            fuel_used NUMERIC(8,2) DEFAULT 0,
            location_lat NUMERIC(10,6),
            location_lng NUMERIC(10,6),
            operator_id VARCHAR(32),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ─── Extension requests (customer → owner approval) ───
    cur.execute("""
        CREATE TABLE extension_requests (
            id SERIAL PRIMARY KEY,
            equipment_id VARCHAR(32) NOT NULL,
            customer_id VARCHAR(32),
            original_return_date DATE,
            requested_new_return_date DATE,
            reason TEXT,
            status VARCHAR(32) DEFAULT 'pending',
            owner_response TEXT,
            responded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("CREATE INDEX idx_equipment_id ON equipment(equipment_id)")
    cur.execute("CREATE INDEX idx_usage_equipment ON usage_logs(equipment_id)")
    cur.execute("CREATE INDEX idx_usage_date ON usage_logs(log_date)")
    cur.execute("CREATE INDEX idx_rental_history_equip ON rental_history(equipment_id)")
    cur.execute("CREATE INDEX idx_rental_history_customer ON rental_history(customer_id)")
    cur.execute("CREATE INDEX idx_ext_status ON extension_requests(status)")

    conn.commit()
    print("✓ Schema created (6 tables):")
    print("  - equipment (exact format)")
    print("  - customers")
    print("  - rental_history")
    print("  - usage_logs")
    print("  - extension_requests")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
