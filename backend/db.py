"""Direct psycopg2 connection (matching the dummy code pattern)"""
import psycopg2
import psycopg2.extras

CONN_STRING = "postgresql://neondb_owner:npg_5mxl1ASwDVvb@ep-wispy-cake-ax2q5ud6-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"


def get_conn():
    return psycopg2.connect(CONN_STRING)


def query(sql, params=None, fetch=True):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        if fetch and cur.description:
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        conn.commit()
        return []
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def execute(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
