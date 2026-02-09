import argparse
import json
import os
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import http.client
import psycopg2


class DeployCtl:
    COMPOSE_FILE = "docker-compose.yml"
    VERSION_FILE = ".version"
    DB_HOST = "localhost"
    DB_PORT = 5432
    DB_USER = "postgres"
    DB_PASSWORD = "postgres"
    DB_NAME = "postgres"
    APP_SERVICE = "app"
    APP_HEALTH_URL = "http://localhost:8000/health"
    MIGRATIONS_FILE = "migrations.sql"
    TIMEOUT = 60

    def __init__(self):
        self.status = {
            "version": None,
            "compose": False,
            "db": False,
            "migrations": False,
            "health": False,
            "result": "failed",
            "errors": []
        }

    def run_compose(self, args, tag):
        env_file = ".deployctl_env"
        try:
            with open(env_file, "w") as f:
                f.write(f"DB_TAG={tag}\n")
            cmd = ["docker", "compose", "-f", self.COMPOSE_FILE, "--env-file", env_file] + args
            subprocess.run(cmd, check=True)
            return True, None
        except subprocess.CalledProcessError as e:
            return False, f"compose failed: {e}"
        finally:
            if os.path.exists(env_file):
                os.remove(env_file)

    def wait_tcp(self, host, port, timeout):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                time.sleep(2)
        return False

    def wait_http(self, url, timeout):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with urlopen(url, timeout=3) as r:
                    if r.status == 200:
                        return True
            except (URLError, HTTPError, socket.timeout, ConnectionError, http.client.HTTPException, OSError):
                pass
            time.sleep(2)
        return False

    def apply_migrations(self, retries=5, delay=2):
        conn = None
        for _ in range(retries):
            try:
                conn = psycopg2.connect(
                    host=self.DB_HOST,
                    port=self.DB_PORT,
                    user=self.DB_USER,
                    password=self.DB_PASSWORD,
                    database=self.DB_NAME
                )
                break
            except psycopg2.OperationalError:
                time.sleep(delay)
        else:
            return False, "DB not reachable for migrations"
        try:
            with conn.cursor() as cur, open(self.MIGRATIONS_FILE) as f:
                cur.execute(f.read())
            conn.commit()
            return True, None
        except Exception as e:
            return False, f"migrations failed: {e}"
        finally:
            if conn:
                conn.close()

    def read_version(self):
        if not os.path.exists(self.VERSION_FILE):
            return True, "15", None
        try:
            lines = [l.strip() for l in open(self.VERSION_FILE) if l.strip()]
            if not lines:
                return True, "15", None
            last = lines[-1]
            if "=" in last:
                return True, last.split("=", 1)[1], None
            return False, None, "invalid line in .version"
        except Exception as e:
            return False, None, f"read_version failed: {e}"

    def write_version(self, tag):
        ok, current, err = self.read_version()
        if current == tag:
            return True, None
        try:
            with open(self.VERSION_FILE, "a") as f:
                f.write(f"DB_TAG={tag}\n")
            return True, None
        except Exception as e:
            return False, f"write_version failed: {e}"

    def cleanup(self):
        self.run_compose(["down", "--remove-orphans"], "cleanup")

    def rollback_docker(self, failed_version):
        ok, prev, err = self.read_version()
        if not ok:
            return
        if prev != failed_version:
            self.run_compose(["up", "-d", "--no-deps", "--force-recreate", self.APP_SERVICE], prev)
        else:
            self.run_compose(["down", "--remove-orphans"], "rollback")

    def cmd_up(self, version):
        self.status["version"] = version
        try:
            ok, err = self.run_compose(["up", "-d"], version)
            self.status["compose"] = ok
            if not ok:
                self.status["errors"].append(err)
                self.cleanup()
                raise RuntimeError("compose failed")

            db_ok = self.wait_tcp(self.DB_HOST, self.DB_PORT, self.TIMEOUT)
            self.status["db"] = db_ok
            if not db_ok:
                self.status["errors"].append("database not reachable")
                self.cleanup()
                raise RuntimeError("db not reachable")

            mig_ok, mig_err = self.apply_migrations()
            self.status["migrations"] = mig_ok
            if not mig_ok:
                self.status["errors"].append(mig_err)
                self.cleanup()
                raise RuntimeError("migrations failed")

            health_ok = self.wait_http(self.APP_HEALTH_URL, self.TIMEOUT)
            self.status["health"] = health_ok
            if not health_ok:
                self.status["errors"].append("health check failed")
                self.cleanup()
                raise RuntimeError("health check failed")

            ok, err = self.write_version(version)
            if not ok:
                self.status["errors"].append(err)

            self.status["result"] = "success"
        except Exception:
            self.rollback_docker(version)
        finally:
            print(json.dumps(self.status, indent=2))
            sys.exit(0 if self.status["result"] == "success" else 1)

    def cmd_rollback(self):
        ok, current, err = self.read_version()
        if not ok:
            self.status["errors"].append(err or "cannot read version")
            print(json.dumps(self.status, indent=2))
            sys.exit(1)
    
        lines = [l.strip() for l in open(self.VERSION_FILE) if l.strip()]
        if len(lines) < 2:
            self.status["errors"].append("no previous version available")
            print(json.dumps(self.status, indent=2))
            sys.exit(1)
    
        prev_line = lines[-2]
        prev = prev_line.split("=", 1)[1]
        self.status["from"] = current
        self.status["to"] = prev
    
        w_ok = False
        w_err = None
    
        try:
            env_file = ".deployctl_env"
            with open(env_file, "w") as f:
                f.write(f"DB_TAG={prev}\n")
    
            ok, err = self.run_compose(
                ["up", "-d", "db", "--force-recreate"], prev
            )
            self.status["compose"] = ok
            if not ok:
                self.status["errors"].append(err)
                self.rollback_docker(prev)
            else:
                try:
                    with open(self.VERSION_FILE, "w") as f:
                        for line in lines[:-1]:
                            f.write(line + "\n")
                    w_ok = True
                except Exception as e:
                    w_ok = False
                    w_err = f"failed to remove last version: {e}"
    
                self.status["version_written"] = w_ok
                if not w_ok:
                    self.status["errors"].append(w_err)
    
            if ok and w_ok and not self.status["errors"]:
                self.status["result"] = "success"
    
        finally:
            if os.path.exists(".deployctl_env"):
                os.remove(".deployctl_env")
            print(json.dumps(self.status, indent=2))
            sys.exit(0 if self.status["result"] == "success" else 1)




def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    up_p = sub.add_parser("up")
    up_p.add_argument("-v", "--version", type=str, required=False, help="Version tag (e.g., 15, 15.3)")

    sub.add_parser("rollback")

    args = parser.parse_args()
    ctl = DeployCtl()

    if args.cmd == "up":
        if args.version:
            version = args.version
        else:
            ok, version, err = ctl.read_version()
            if not ok or version is None:
                print(json.dumps({"result": "failed", "errors": [err or "cannot read version"]}, indent=2))
                sys.exit(1)
        ctl.cmd_up(version)
    elif args.cmd == "rollback":
        ctl.cmd_rollback()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
