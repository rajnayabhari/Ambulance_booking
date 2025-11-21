# tests/test_notifications_api.py
def test_notifications_badge(client, db_conn, make_user):
    make_user("NUser", "n@example.com", "npw", "user")
    client.post("/signin", data={"email":"n@example.com","password":"npw"}, follow_redirects=True)

    uid = None
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email=%s", ("n@example.com",))
        uid = cur.fetchone()[0]
        cur.execute("INSERT INTO notifications (user_id, title, body) VALUES (%s,%s,%s)", (uid, "Hello", "World"))
        db_conn.commit()

    r = client.get("/api/notifications/unread_count")
    assert r.get_json()["count"] >= 1

    client.post("/api/notifications/mark_read")
    r2 = client.get("/api/notifications/unread_count")
    assert r2.get_json()["count"] == 0
