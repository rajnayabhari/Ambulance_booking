# tests/test_driver_status.py
def _get_id(conn, email):
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (email,))
    r = cur.fetchone(); cur.close()
    return r[0]

def test_driver_cannot_go_offline_with_active_trip(client, db_conn, make_user):
    # create user+driver
    make_user("U", "u@example.com", "upw", "user")
    make_user("D", "d@example.com", "dpw", "driver")

    did = _get_id(db_conn, "d@example.com")
    # verify + online
    cur = db_conn.cursor()
    cur.execute("UPDATE users SET is_verified=TRUE, is_online=TRUE WHERE id=%s", (did,))
    db_conn.commit(); cur.close()

    # driver login + location
    client.post("/signin", data={"email": "d@example.com", "password": "dpw"}, follow_redirects=True)
    client.post("/update_driver_location", data={"lat":"27.70","lon":"85.33"})
    client.get("/logout", follow_redirects=True)

    # user login, location, book
    client.post("/signin", data={"email":"u@example.com","password":"upw"}, follow_redirects=True)
    client.post("/book", data={"patient_name":"p", "phone_no":"98", "pickup_location":"", "destination":"H", "user_lat":"27.70", "user_lon":"85.33"}, follow_redirects=True)
    # choose the driver shown
    # get driver id and request
    resp = client.get("/choose_driver")
    assert b"D" in resp.data
    client.post("/request_driver", data={"driver_id": str(did), "patient_name":"p","phone_no":"98","destination":"H","pickup_location":"", "user_lat":"27.70","user_lon":"85.33"}, follow_redirects=True)

    # fetch booking id
    uid = _get_id(db_conn, "u@example.com")
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM bookings WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
    bid = cur.fetchone()[0]; cur.close()

    # driver accept
    client.get("/logout", follow_redirects=True)
    client.post("/signin", data={"email":"d@example.com","password":"dpw"}, follow_redirects=True)
    client.post(f"/driver/accept/{bid}", follow_redirects=True)

    # try to go offline -> should be blocked
    resp = client.post("/driver/set_status", data={"state":"offline"}, follow_redirects=True)
    assert b"active trip" in resp.data
