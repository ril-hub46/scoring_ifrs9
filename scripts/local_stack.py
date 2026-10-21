"""Pile locale sans Docker ni droits administrateur : PostgreSQL portable, API et Streamlit.

    uv run python scripts/local_stack.py setup    # 1re fois : installe Postgres, crée les bases, alimente les données
    uv run python scripts/local_stack.py start    # démarre Postgres, l'API (:8000) et le Streamlit (:8501)
    uv run python scripts/local_stack.py stop     # arrête tout
    uv run python scripts/local_stack.py status

Utilisateur, mot de passe, port et base sont lus dans SCORING_DATABASE_URL (.env), la même
configuration que l'ETL et l'API. Postgres (binaires officiels EDB) et les logs vivent dans
%LOCALAPPDATA%\\scoring-postgres (modifiable via SCORING_LOCAL_PG_ROOT).
Windows uniquement pour l'installation de Postgres ; ailleurs, utiliser docker compose.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from sqlalchemy import create_engine, make_url, text

from src.config import Settings

PG_VERSION = "17.11-1"
PG_URL = f"https://get.enterprisedb.com/postgresql/postgresql-{PG_VERSION}-windows-x64-binaries.zip"
SKIPPED_ZIP_DIRS = ("pgsql/pgAdmin 4/", "pgsql/doc/", "pgsql/StackBuilder/", "pgsql/symbols/")

REPO = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("SCORING_LOCAL_PG_ROOT", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "scoring-postgres"))
BIN = ROOT / "pgsql" / "bin"
DATA = ROOT / "data"
LOGS = ROOT / "logs"
PIDS = ROOT / "services.json"

# Processus sans fenêtre, qui survivent à la fin de ce script
DETACHED = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

SERVICES = {
    "api": (8000, [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"]),
    "web": (8501, [sys.executable, "-m", "streamlit", "run", "web/streamlit_app.py",
                   "--server.port", "8501", "--server.headless", "true"]),
}


def db_url():
    return make_url(Settings().database_url)


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("localhost", port)) == 0


def wait_port(port: int, name: str, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return
        time.sleep(1)
    raise SystemExit(f"{name} ne répond pas sur le port {port} (voir {LOGS})")


def pg(tool: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    # stdin/stdout hérités ou DEVNULL, jamais de pipe : le serveur hériterait du pipe et bloquerait
    return subprocess.run([str(BIN / f"{tool}.exe"), *args], stdin=subprocess.DEVNULL, **kwargs)


def postgres_running() -> bool:
    return pg("pg_ctl", "-D", str(DATA), "status", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def start_postgres() -> None:
    if postgres_running():
        print("PostgreSQL déjà démarré")
        return
    result = pg("pg_ctl", "-D", str(DATA), "-l", str(ROOT / "postgres.log"), "-w", "start",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=DETACHED)
    if result.returncode != 0:
        raise SystemExit(f"Démarrage de PostgreSQL impossible, voir {ROOT / 'postgres.log'}")
    print(f"PostgreSQL démarré (port {db_url().port})")


def install_postgres() -> None:
    if (BIN / "pg_ctl.exe").exists():
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / f"postgresql-{PG_VERSION}.zip"
    if not archive.exists():
        print(f"Téléchargement de {PG_URL} (~325 Mo) ...")
        urllib.request.urlretrieve(PG_URL, archive)
    print("Extraction (sans pgAdmin ni documentation) ...")
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.namelist() if not m.startswith(SKIPPED_ZIP_DIRS)]
        zf.extractall(ROOT, members)
    archive.unlink()


def init_cluster() -> None:
    if (DATA / "PG_VERSION").exists():
        return
    url = db_url()
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pw") as pw_file:
        pw_file.write(url.password)
    try:
        pg("initdb", "-D", str(DATA), "-U", url.username, f"--pwfile={pw_file.name}",
           "-A", "scram-sha-256", "-E", "UTF8", "--locale=C", check=True)
    finally:
        os.unlink(pw_file.name)
    with open(DATA / "postgresql.conf", "a", encoding="utf-8") as conf:
        conf.write(f"\nport = {url.port}\nlisten_addresses = 'localhost'\n")


def create_databases() -> None:
    url = db_url()
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for name in (url.database, f"{url.database}_test"):
            if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).scalar():
                conn.execute(text(f'CREATE DATABASE "{name}"'))
                print(f"Base {name} créée")
    admin.dispose()


def load_data() -> None:
    """Migrations, puis pipeline complet si le portefeuille n'a pas encore été scoré."""
    run = lambda *args: subprocess.run([sys.executable, "-m", *args], cwd=REPO, check=True)
    run("alembic", "upgrade", "head")

    engine = create_engine(db_url())
    with engine.connect() as conn:
        scored = conn.execute(text("SELECT count(*) FROM mart.ecl_results")).scalar()
    engine.dispose()
    if scored:
        print(f"Données déjà présentes ({scored:,} prêts scorés)".replace(",", " "))
        return

    if not Settings().raw_data_path.exists():
        run("src.cli", "rebuild-source")
    print("Pipeline complet (ingest, staging, train, score) : 3 à 5 minutes ...")
    run("src.cli", "run-all")


def start_services() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    pids = json.loads(PIDS.read_text()) if PIDS.exists() else {}
    for name, (port, command) in SERVICES.items():
        if port_open(port):
            print(f"{name} déjà démarré (port {port})")
            continue
        log = open(LOGS / f"{name}.log", "ab")
        process = subprocess.Popen(command, cwd=REPO, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, creationflags=DETACHED)
        pids[name] = process.pid
        wait_port(port, name)
        print(f"{name} démarré (port {port}, logs : {LOGS / f'{name}.log'})")
    PIDS.write_text(json.dumps(pids))


def stop_services() -> None:
    pids = json.loads(PIDS.read_text()) if PIDS.exists() else {}
    for name, pid in pids.items():
        if os.name == "nt":
            killed = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        else:
            try:
                os.kill(pid, 15)
                killed = True
            except ProcessLookupError:
                killed = False
        if killed:
            print(f"{name} arrêté")
    PIDS.unlink(missing_ok=True)


def cmd_setup() -> None:
    install_postgres()
    init_cluster()
    start_postgres()
    create_databases()
    load_data()
    print("\nInstallation terminée. Lancer : uv run python scripts/local_stack.py start")


def cmd_start() -> None:
    if not (BIN / "pg_ctl.exe").exists():
        raise SystemExit("PostgreSQL absent : lancer d'abord `uv run python scripts/local_stack.py setup`")
    start_postgres()
    start_services()
    print("\nDashboard : http://localhost:8501\nAPI       : http://localhost:8000/docs")


def cmd_stop() -> None:
    stop_services()
    if (BIN / "pg_ctl.exe").exists() and postgres_running():
        pg("pg_ctl", "-D", str(DATA), "-m", "fast", "stop", stdout=subprocess.DEVNULL, check=True)
        print("PostgreSQL arrêté")


def cmd_status() -> None:
    print(f"PostgreSQL : {'démarré' if (BIN / 'pg_ctl.exe').exists() and postgres_running() else 'arrêté'}")
    for name, (port, _) in SERVICES.items():
        print(f"{name:10} : {'démarré' if port_open(port) else 'arrêté'} (port {port})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["setup", "start", "stop", "status"])
    command = parser.parse_args().command
    os.chdir(REPO)  # .env et data/ sont lus depuis la racine du projet
    {"setup": cmd_setup, "start": cmd_start, "stop": cmd_stop, "status": cmd_status}[command]()


if __name__ == "__main__":
    main()
