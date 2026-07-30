"""Single persistent connection for Neon (20s cold start paid once at startup)"""
import psycopg2
import psycopg2.extras

CONN_STRING = "postgresql://neondb_owner:npg_5mxl1ASwDVvb@ep-wispy-cake-ax2q5ud6.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&connect_timeout=10"

_conn = None

def _get_conn():
    global _conn
    try:
        if _conn is None or _conn.closed:
            _conn = psycopg2.connect(CONN_STRING)
        return _conn
    except:
        _conn = psycopg2.connect(CONN_STRING)
        return _conn

def query(sql, params=None, fetch=True):
    conn = _get_conn()
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

def execute(sql, params=None):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount
    except Exception as e:
        conn.rollback()
        raise e
