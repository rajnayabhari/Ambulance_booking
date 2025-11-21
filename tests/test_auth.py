# tests/test_auth.py
import re

def test_admin_seed_login(client):
    # seeded in initialize_db -> admin: raj@gmail.com / raj123
    resp = client.post("/signin", data={"email": "raj@gmail.com", "password": "raj123"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Signed in." in resp.data

def test_signup_and_login_user(client, make_user):
    make_user("u1", "u1@example.com", "passu1", "user")
    resp = client.post("/signin", data={"email": "u1@example.com", "password": "passu1"}, follow_redirects=True)
    assert b"Signed in." in resp.data

def test_invalid_login(client):
    resp = client.post("/signin", data={"email": "nope@example.com", "password": "x"}, follow_redirects=True)
    assert b"Invalid credentials." in resp.data
