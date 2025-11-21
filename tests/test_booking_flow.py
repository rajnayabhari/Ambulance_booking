# tests/test_booking_flow.py
import time

def _set_verified_online(db_conn, user_id, online=True, verified=True):
    cur = db_conn.cursor()
    cur.execute("UPDATE users SET is_verified=%s, is_online=%s WHERE id=%s", (verified, online, user_id))
    db_conn.commit()
    cur.close()

def _get_user_id(db_conn, email):
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (email,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None

def _ping_user_loc(client, lat, lon):
    return client.post("/update_user_location", data={"lat": lat, "lon": lon})

def _ping_driver_loc(client, lat, lon):
    return client.post("/update_driver_location", data={"lat": lat, "lon": lon})

def test_full_booking_flow(client, db_conn, make_user):
    # Create user & driver
    make_user("Alice", "alice@example.com", "alicepw", "user")
    make_user("Bob", "bob@example.com", "bobpw", "driver")

    # Login as driver, set location + verified + online
    client.post("/signin", data={"email": "bob@example.com", "password": "bobpw"}, follow_redirects=True)
    _set_verified_online(db_conn, _get_user_id(db_conn, "bob@example.com"), verified=True, online=True)
    r = _ping_driver_loc(client, 27.7001, 85.3333)
    assert r.status_code == 200

    # Login as user, set location
    client.get("/logout", follow_redirects=True)
    client.post("/signin", data={"email": "alice@example.com", "password": "alicepw"}, follow_redirects=True)
    _ping_user_loc(client, 27.7010, 85.3340)

    # Start booking – choose_driver should list only available (online+verified) drivers
    client.post("/book", data={
        "patient_name": "P1",
        "phone_no": "9800000000",
        "pickup_location": "",
        "destination": "Hospital A",
        "user_lat": "27.7010", "user_lon": "85.3340"
    }, follow_redirects=True)

    resp = client.get("/choose_driver")
    assert b"Choose a Driver" in resp.data
    assert b"Bob" in resp.data  # suggested

    # Request driver
    uid = _get_user_id(db_conn, "alice@example.com")
    did = _get_user_id(db_conn, "bob@example.com")
    resp = client.post("/request_driver", data={
        "driver_id": str(did),
        "patient_name": "P1",
        "phone_no": "9800000000",
        "destination": "Hospital A",
        "pickup_location": "",
        "user_lat": "27.7010", "user_lon": "85.3340"
    }, follow_redirects=True)
    assert b"Request sent." in resp.data

    # User cannot track before Accepted
    # Find booking id
    cur = db_conn.cursor()
    cur.execute("SELECT id, status FROM bookings WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
    bid, status = cur.fetchone()
    cur.close()
    assert status == "Pending"
    resp = client.get(f"/track/{bid}", follow_redirects=True)
    assert b"Trip not accepted yet" in resp.data

    # Driver accepts
    client.get("/logout", follow_redirects=True)
    client.post("/signin", data={"email": "bob@example.com", "password": "bobpw"}, follow_redirects=True)
    resp = client.post(f"/driver/accept/{bid}", follow_redirects=True)
    assert b"Accepted." in resp.data

    # Now user can track; API should return driver coords
    client.get("/logout", follow_redirects=True)
    client.post("/signin", data={"email": "alice@example.com", "password": "alicepw"}, follow_redirects=True)
    api = client.get(f"/api/booking_positions/{bid}")
    js = api.get_json()
    assert js["status"] == "Accepted"
    assert js["driver"]["lat"] is not None

    # Complete trip
    client.get("/logout", follow_redirects=True)
    client.post("/signin", data={"email": "bob@example.com", "password": "bobpw"}, follow_redirects=True)
    resp = client.post(f"/driver/complete/{bid}", follow_redirects=True)
    assert b"Marked as Completed." in resp.data

    # User can review once; second review blocked
    client.get("/logout", follow_redirects=True)
    client.post("/signin", data={"email": "alice@example.com", "password": "alicepw"}, follow_redirects=True)
    resp = client.post(f"/rate_driver/{bid}", data={"stars": "5", "comment": "Great"}, follow_redirects=True)
    assert b"Thanks for your review" in resp.data
    resp = client.post(f"/rate_driver/{bid}", data={"stars": "5", "comment": "Again"}, follow_redirects=True)
    assert b"already reviewed" in resp.data
