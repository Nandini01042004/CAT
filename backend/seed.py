"""Seed — generate 200 synthetic records matching exact problem statement format"""
import psycopg2
import random
from datetime import datetime, timedelta

CONN = "postgresql://neondb_owner:npg_5mxl1ASwDVvb@ep-wispy-cake-ax2q5ud6-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"
TYPES = ["Crane", "Excavator", "Bulldozer", "Grader", "Backhoe", "Dump Truck", "Wheel Loader", "Forklift", "Compactor", "Drill"]
SITES = [f"S{str(i).zfill(3)}" for i in range(1, 21)]

def main():
    conn = psycopg2.connect(CONN)
    cur = conn.cursor()

    # ─── Equipment (200 records) ───
    for i in range(1, 201):
        eq_id = f"CAT-{i:04d}"
        eq_type = random.choice(TYPES)
        site = random.choice(SITES)
        check_in = datetime.now() - timedelta(days=random.randint(0, 90))

        # 30% chance checked out (free), 70% still in use
        if random.random() < 0.3:
            check_out = check_in + timedelta(days=random.randint(1, 30))
            engine_hours = random.uniform(4, 12)
        else:
            check_out = None
            engine_hours = random.uniform(6, 14)

        idle_hours = random.uniform(0, engine_hours * 1.2)
        rental_days = random.randint(1, 60)
        operator = f"OP-{random.choice(['A','B','C'])}{random.randint(1,30):02d}"
        lat = round(random.uniform(12.8, 13.2), 4)
        lng = round(random.uniform(77.4, 77.8), 4)
        fuel = random.uniform(50, 300)
        total_eng = engine_hours * rental_days
        total_idle = idle_hours * rental_days
        cost = random.uniform(5000, 25000)
        rate = random.choice([300, 400, 500, 650, 800])
        customer = f"CUST-{random.randint(1, 50):03d}"

        cur.execute("""
            INSERT INTO equipment (equipment_id, equipment_type, site_id, check_in_time, check_out_time,
                operator_id, engine_hours, idle_hours, fuel_used, rental_cost, daily_rental_rate, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [eq_id, eq_type, site, check_in, check_out, operator, total_eng, total_idle, fuel, cost, rate,
              'checked_in' if check_out is None else 'checked_out'])

    # ─── Customers (50) ───
    companies = ["ABC Construction", "XYZ Mining", "PQR Builders", "LMN Infra", "DEF Earthworks",
                 "GHI Developers", "JKL Contractors", "MNO Engineers", "RST Group", "UVW Industries"]
    for i in range(1, 51):
        cust_id = f"CUST-{i:03d}"
        name = f"Customer {i}"
        company = random.choice(companies)
        email = f"cust{i}@example.com"
        phone = f"+91-{random.randint(7000000000, 9999999999)}"
        rentals = random.randint(1, 15)
        cur.execute("INSERT INTO customers (customer_id, customer_name, company, contact_email, contact_phone, total_rentals) "
                     "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     [cust_id, name, company, email, phone, rentals])

    # ─── Rental history (one per equipment) ───
    for i in range(1, 201):
        eq_id = f"CAT-{i:04d}"
        cust = f"CUST-{random.randint(1, 50):03d}"
        op = f"OP-{random.choice(['A','B','C'])}{random.randint(1,30):02d}"
        site = random.choice(SITES)
        out_date = datetime.now() - timedelta(days=random.randint(30, 90))
        expected_return = out_date + timedelta(days=random.randint(10, 45))
        actual_return = expected_return if random.random() < 0.7 else expected_return + timedelta(days=random.randint(1, 7))
        eng = random.uniform(6, 14)
        idle = random.uniform(0, 5)
        fuel = random.uniform(50, 250)
        cost = random.uniform(10000, 30000)
        lat = round(random.uniform(12.8, 13.2), 4)
        lng = round(random.uniform(77.4, 77.8), 4)

        cur.execute("""
            INSERT INTO rental_history (equipment_id, customer_id, operator_id, site_id,
                check_out_time, expected_return_time, actual_return_time,
                engine_hours, idle_hours, fuel_used, rental_cost, location_lat, location_lng)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [eq_id, cust, op, site, out_date, expected_return, actual_return, eng, idle, fuel, cost, lat, lng])

    # ─── Usage logs (daily per equipment) ───
    for i in range(1, 201):
        eq_id = f"CAT-{i:04d}"
        for day in range(1, random.randint(5, 20)):
            d = datetime.now() - timedelta(days=day)
            eng = round(random.uniform(6, 14), 1)
            idle = round(random.uniform(0, 6), 1)
            fuel = round(random.uniform(40, 200), 1)
            lat = round(random.uniform(12.8, 13.2), 4)
            lng = round(random.uniform(77.4, 77.8), 4)
            op = f"OP-{random.choice(['A','B','C'])}{random.randint(1,30):02d}"

            cur.execute("""
                INSERT INTO usage_logs (equipment_id, date, engine_hours, idle_hours, fuel_used,
                    location_lat, location_lng)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, [eq_id, d, eng, idle, fuel, lat, lng])
        if i % 25 == 0:
            conn.commit()
            print(f"  Committed {i} equipment + daily logs...")

    conn.commit()
    cur.close()
    conn.close()
    print("✓ 200 equipment, 50 customers, 200 rental history, ~2000 daily logs seeded")

if __name__ == "__main__":
    main()
