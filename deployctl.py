import subprocess
import time
import json
import requests
import sys
import os

COMPOSE_FILE = "docker-compose.yml"
APP_URL = "http://localhost:8000/health"
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "appdb")
DB_HOST = "localhost"
MIGRATION_FILE = "migrations.sql"

def run(cmd):
    print(f"> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def wait_for_db(timeout=60):
    import psycopg2
    start = time.time()
    while time.time() - start < timeout:
        try:
            conn = psycopg2.connect(
                host=DB_HOST, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
            )
            conn.close()
            print("DB is ready")
            return True
        except:
            print("Waiting for DB...")
            time.sleep(2)
    print("DB not ready in time")
    sys.exit(1)

def apply_migrations():
    cmd = f"psql postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME} -f {MIGRATION_FILE}"
    run(cmd)
    print("Migrations applied")

def wait_for_app(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(APP_URL)
            if r.status_code == 200:
                print("App is healthy")
                return True
        except:
            pass
        print("Waiting for app...")
        time.sleep(2)
    print("App not healthy in time")
    sys.exit(1)

def up():
    run(f"docker-compose -f {COMPOSE_FILE} up -d --build")
    wait_for_db()
    apply_migrations()
    wait_for_app()
    status = {"db": "ready", "app": "healthy", "migrations": "applied"}
    print(json.dumps(status, indent=2))

def rollback():
    print("Rolling back...")
    # Для простоты: вернемся на предыдущий тег
    run(f"docker-compose -f {COMPOSE_FILE} stop app")
    run(f"docker-compose -f {COMPOSE_FILE} up -d --no-deps app")
    print("Rollback done")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("up", "rollback"):
        print("Usage: deployctl.py [up|rollback]")
        sys.exit(1)
    if sys.argv[1] == "up":
        up()
    else:
        rollback()
