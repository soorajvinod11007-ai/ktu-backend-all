import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def create_dbs():
    conn = psycopg2.connect(user="postgres", password="87654321", host="localhost", port="5432")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_database;")
    dbs = [row[0] for row in cur.fetchall()]
    if "college_results" not in dbs:
        cur.execute("CREATE DATABASE college_results;")
        print("Created college_results")
    if "college_results_test" not in dbs:
        cur.execute("CREATE DATABASE college_results_test;")
        print("Created college_results_test")
    cur.close()
    conn.close()

if __name__ == "__main__":
    create_dbs()
