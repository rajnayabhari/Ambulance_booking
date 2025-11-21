# tests/conftest.py
import os
import sys
import importlib
import random
import string
import psycopg2
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database as dbmod  # DO NOT import app here!

def _rand_db_name(prefix="ambulance_db_test_"):
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}{suffix}"

@pytest.fixture(scope="session")
def pg_admin_conn():
    """Admin connection to 'postgres' DB to create/drop test DBs."""
    cfg = dbmod.DB_CFG
    conn = psycopg2.connect(
        database="postgres",
        user=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
    )
    conn.autocommit = True
    yield conn
    conn.close()

@pytest.fixture(scope="session")
def test_db_name(pg_admin_conn):
    """Create a brand new test database, drop when session ends."""
    name = _rand_db_name()
    with pg_admin_conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    yield name
    # terminate connections then drop
    with pg_admin_conn.cursor() as cur:
        cur.execute("""
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid();
        """, (name,))
        cur.execute(f'DROP DATABASE IF EXISTS "{name}"')

@pytest.fixture(scope="function")
def app(test_db_name, monkeypatch):
    """
    Patch DB_CFG to the test DB, run initialize_db() there,
    then import app.py fresh so it uses the patched database module.
    """
    # 1) Patch DB config
    new_cfg = dict(dbmod.DB_CFG)
    new_cfg["database"] = test_db_name
    monkeypatch.setattr(dbmod, "DB_CFG", new_cfg, raising=True)

    def patched_conn():
        return psycopg2.connect(**dbmod.DB_CFG)
    monkeypatch.setattr(dbmod, "get_db_connection", patched_conn, raising=True)

    # 2) Initialize schema + seed admin in the test DB
    dbmod.initialize_db()

    # 3) Import app AFTER patching database module
    if "app" in sys.modules:
        del sys.modules["app"]
    appmod = importlib.import_module("app")
    app = appmod.app
    app.config["TESTING"] = True
    return app

@pytest.fixture(scope="function")
def client(app):
    return app.test_client()

@pytest.fixture(scope="function")
def db_conn():
    """Direct connection to the test DB for setup inside tests."""
    conn = psycopg2.connect(**dbmod.DB_CFG)
    yield conn
    conn.close()

# Convenience helpers for tests
def login(client, email, password):
    return client.post("/signin", data={"email": email, "password": password}, follow_redirects=True)

def signup(client, username, email, password, role="user"):
    return client.post("/signup", data={
        "username": username,
        "email": email,
        "password": password,
        "role": role
    }, follow_redirects=True)

@pytest.fixture(scope="function")
def make_user(client):
    def _mk(username, email, password, role="user"):
        r = signup(client, username, email, password, role)
        assert r.status_code in (200, 302)
        return (username, email, password, role)
    return _mk
