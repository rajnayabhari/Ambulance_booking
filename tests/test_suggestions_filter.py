# tests/test_suggestions_filter.py
import re

def get_user_id(conn, email):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (email,))
        r = cur.fetchone()
        return r[0]

def _extract_driver_ids_from_choose_page(html: str):
    """
    Find all driver_id values rendered in the Choose Driver page.
    We search for the hidden input typically used in the 'Request' form:
      <input type="hidden" name="driver_id" value="123">
    Works with single or double quotes.
    """
    ids = set()
    # value="123" or value='123'
    for m in re.finditer(r'name=["\']driver_id["\']\s+value=["\'](\d+)["\']', html):
        ids.add(int(m.group(1)))
    return ids

def test_suggestions_exclude_offline_unverified_busy(client, db_conn, make_user):
    # user
    make_user("UU", "uu@example.com", "uupw", "user")
    client.post("/signin", data={"email":"uu@example.com","password":"uupw"}, follow_redirects=True)

    # three drivers
    make_user("A", "a@example.com", "apw", "driver")  # verified + online + free (should appear)
    make_user("B", "b@example.com", "bpw", "driver")  # unverified (exclude)
    make_user("C", "c@example.com", "cpw", "driver")  # busy (accepted) (exclude)

    ida = get_user_id(db_conn, "a@example.com")
    idb = get_user_id(db_conn, "b@example.com")
    idc = get_user_id(db_conn, "c@example.com")

    # Set statuses
    with db_conn.cursor() as cur:
        # A: verified + online
        cur.execute("UPDATE users SET is_verified=TRUE, is_online=TRUE WHERE id=%s", (ida,))
        # B: unverified + online
        cur.execute("UPDATE users SET is_verified=FALSE, is_online=TRUE WHERE id=%s", (idb,))
        # C: verified + online (will be set busy)
        cur.execute("UPDATE users SET is_verified=TRUE, is_online=TRUE WHERE id=%s", (idc,))
        db_conn.commit()

    # Ping driver locations for A, B, C (to satisfy 'fresh location' filter)
    client.get("/logout", follow_redirects=True)
    for email in ("a@example.com","b@example.com","c@example.com"):
        client.post("/signin", data={"email": email, "password": email[0]+"pw"}, follow_redirects=True)
        client.post("/update_driver_location", data={"lat":"27.70","lon":"85.33"})
        client.get("/logout", follow_redirects=True)

    # Create a booking for C and set to Accepted → driver C becomes busy
    client.post("/signin", data={"email":"uu@example.com","password":"uupw"}, follow_redirects=True)
    client.post("/book", data={
        "patient_name":"p","phone_no":"98","pickup_location":"",
        "destination":"H","user_lat":"27.70","user_lon":"85.33"
    }, follow_redirects=True)
    client.get("/choose_driver")
    client.post("/request_driver", data={
        "driver_id": str(idc),
        "patient_name":"p","phone_no":"98","destination":"H","pickup_location":"",
        "user_lat":"27.70","user_lon":"85.33"
    }, follow_redirects=True)

    with db_conn.cursor() as cur:
        cur.execute("UPDATE bookings SET status='Accepted' WHERE driver_id=%s", (idc,))
        db_conn.commit()

    # Now check suggestions: only A should be listed (by driver_id)
    resp = client.get("/choose_driver")
    ids = _extract_driver_ids_from_choose_page(resp.data.decode("utf-8"))

    assert ida in ids, "Driver A should be suggested"
    assert idb not in ids, "Driver B is unverified and must not be suggested"
    assert idc not in ids, "Driver C is busy (Accepted) and must not be suggested"
