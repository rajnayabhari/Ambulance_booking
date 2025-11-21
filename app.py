import os
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# DB helpers
from database import initialize_db, get_db_connection

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-please-change")
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Init DB
try:
    initialize_db()
    print("✅ Database initialized/verified.")
except Exception as e:
    print("⚠️ DB init failed:", e)


# ------------------------------
# Utilities
# ------------------------------
def verify_password(input_password: str, stored_hash: str) -> bool:
    """Accept PBKDF2/Scrypt (werkzeug) and legacy SHA-256 hex."""
    if not stored_hash:
        return False
    if stored_hash.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored_hash, input_password)
    sh = stored_hash.strip().lower()
    if len(sh) == 64 and all(c in "0123456789abcdef" for c in sh):
        import hashlib
        return hashlib.sha256(input_password.encode()).hexdigest() == sh
    return False

def is_user_verified(conn, user_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT is_verified FROM users WHERE id=%s", (user_id,))
    row = cur.fetchone()
    cur.close()
    return bool(row and row[0])

def create_notification(conn, user_id: int, title: str, body: str):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notifications (user_id, title, body) VALUES (%s,%s,%s)",
        (user_id, title, body)
    )
    conn.commit()
    cur.close()

def distance_km(lat1, lon1, lat2, lon2):
    try:
        if None in (lat1, lon1, lat2, lon2): return None
        from math import radians, sin, cos, asin, sqrt
        R = 6371.0
        dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return 2 * R * asin(sqrt(a))
    except Exception:
        return None

@app.before_request
def refresh_identity_flags():
    """Cache driver verified/online flags into session for quick UI checks."""
    uid = session.get("user_id"); role = session.get("role")
    if not uid or role != "driver":
        session.pop("driver_is_online", None)
        session.pop("driver_is_verified", None)
        return
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT is_online, is_verified FROM users WHERE id=%s", (uid,))
        row = cur.fetchone()
        cur.close(); conn.close()
        session["driver_is_online"] = bool(row[0]) if row else False
        session["driver_is_verified"] = bool(row[1]) if row else False
    except Exception:
        session["driver_is_online"] = False
        session["driver_is_verified"] = False


# ------------------------------
# Auth
# ------------------------------
@app.route("/")
def root(): return redirect("/home")

@app.route("/home")
def home(): return render_template("home.html")

@app.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id, password, role, username FROM users WHERE LOWER(email)=LOWER(%s)", (email,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and verify_password(password, row[1]):
            session["user_id"] = row[0]
            session["role"] = row[2]
            session["username"] = row[3]
            flash("Signed in.")
            return redirect("/home")
        flash("Invalid credentials.")
        return redirect("/signin")
    return render_template("signin.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        role = request.form.get("role") or "user"
        if not (username and email and password and role):
            flash("Fill all fields."); return redirect("/signup")
        hashed = generate_password_hash(password)
        conn = get_db_connection(); cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, email, password, role) VALUES (%s,%s,%s,%s)",
                (username, email, hashed, role)
            )
            conn.commit()
            flash("Account created. Please sign in.")
            return redirect("/signin")
        except Exception:
            conn.rollback()
            flash("Signup failed (email may exist).")
            return redirect("/signup")
        finally:
            cur.close(); conn.close()
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Signed out.")
    return redirect("/home")


# ------------------------------
# Live location pings
# ------------------------------
@app.route("/update_user_location", methods=["POST"])
def update_user_location():
    if "user_id" not in session or session.get("role") != "user":
        return jsonify({"ok": False, "error": "user only"}), 403
    uid = session["user_id"]
    try:
        lat = float(request.form.get("lat")); lon = float(request.form.get("lon"))
    except:
        return jsonify({"ok": False, "error": "invalid coords"}), 400

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_location (user_id, latitude, longitude, updated_at)
        VALUES (%s,%s,%s,NOW())
        ON CONFLICT (user_id) DO UPDATE
          SET latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude, updated_at=NOW()
    """, (uid, lat, lon))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/update_driver_location", methods=["POST"])
def update_driver_location():
    if "user_id" not in session or session.get("role") != "driver":
        return jsonify({"ok": False, "error": "driver only"}), 403
    did = session["user_id"]
    try:
        lat = float(request.form.get("lat")); lon = float(request.form.get("lon"))
    except:
        return jsonify({"ok": False, "error": "invalid coords"}), 400

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO driver_location (driver_id, latitude, longitude, updated_at)
        VALUES (%s,%s,%s,NOW())
        ON CONFLICT (driver_id) DO UPDATE
          SET latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude, updated_at=NOW()
    """, (did, lat, lon))

    # Only verified drivers can be online. If not verified, force offline.
    if is_user_verified(conn, did):
        cur.execute("UPDATE users SET is_online=TRUE, last_online_at=NOW() WHERE id=%s", (did,))
        made_online = True
    else:
        cur.execute("UPDATE users SET is_online=FALSE WHERE id=%s", (did,))
        made_online = False

    conn.commit(); cur.close(); conn.close()
    session["driver_is_online"] = made_online
    return jsonify({"ok": True, "online": made_online, "verified": session.get("driver_is_verified", False)})

@app.route("/driver/set_status", methods=["POST"])
def driver_set_status():
    if "user_id" not in session or session.get("role") != "driver":
        flash("Sign in as driver."); return redirect("/signin")
    did = session["user_id"]
    state = (request.form.get("state") or "").lower()

    conn = get_db_connection(); cur = conn.cursor()

    # Don’t allow offline if there’s an active trip
    if state != "online":
        cur.execute("SELECT 1 FROM bookings WHERE driver_id=%s AND status='Accepted' LIMIT 1", (did,))
        if cur.fetchone():
            cur.close(); conn.close()
            flash("You have an active trip. Complete it before going offline.")
            return redirect(request.headers.get("Referer") or url_for("driver_requests"))

    # If trying to go online but not verified
    if state == "online" and not is_user_verified(conn, did):
        cur.close(); conn.close()
        session["driver_is_online"] = False
        session["driver_is_verified"] = False
        flash("Your account is not verified yet. Complete KYC and wait for admin approval.")
        return redirect(request.headers.get("Referer") or url_for("driver_requests"))

    if state == "online":
        cur.execute("UPDATE users SET is_online=TRUE, last_online_at=NOW() WHERE id=%s", (did,))
        session["driver_is_online"] = True
        flash("Status: Online")
    else:
        cur.execute("UPDATE users SET is_online=FALSE WHERE id=%s", (did,))
        session["driver_is_online"] = False
        flash("Status: Offline")
    conn.commit(); cur.close(); conn.close()

    return redirect(request.headers.get("Referer") or url_for("driver_requests"))


# ------------------------------
# Booking flow
# ------------------------------
@app.route("/book", methods=["GET", "POST"])
def book():
    if "user_id" not in session or session.get("role") != "user":
        flash("Sign in as user to book."); return redirect("/signin")
    if request.method == "POST":
        session["book_patient"] = request.form.get("patient_name") or ""
        session["book_phone"]   = request.form.get("phone_no") or ""
        session["book_pick"]    = request.form.get("pickup_location") or ""
        session["book_dest"]    = request.form.get("destination") or ""
        session["book_lat"]     = request.form.get("user_lat")
        session["book_lon"]     = request.form.get("user_lon")
        return redirect("/choose_driver")
    return render_template("book.html")

def fetch_driver_cards(conn):
    """
    Verified + Online + fresh location (<=5m) + not busy (no Accepted booking).
    Offline drivers are automatically excluded here.
    """
    cur = conn.cursor()
    cur.execute("""
        WITH busy AS (
            SELECT DISTINCT driver_id FROM bookings WHERE status='Accepted'
        )
        SELECT u.id, u.username,
               COALESCE(AVG(dr.stars), 0) AS avg_rating,
               COUNT(dr.id) AS rating_count,
               dl.latitude, dl.longitude
        FROM users u
        LEFT JOIN driver_ratings dr ON dr.driver_id = u.id
        JOIN driver_location dl ON dl.driver_id = u.id
        WHERE u.role='driver'
          AND u.is_verified=TRUE
          AND u.is_online=TRUE
          AND dl.updated_at > NOW() - INTERVAL '5 minutes'
          AND u.id NOT IN (SELECT driver_id FROM busy)
        GROUP BY u.id, u.username, dl.latitude, dl.longitude
    """)
    rows = cur.fetchall(); cur.close()
    drivers = []
    for (driver_id, name, avg_rating, count, lat, lon) in rows:
        drivers.append({
            "driver_id": driver_id,
            "name": name,
            "avg_rating": float(avg_rating or 0),
            "rating_count": int(count or 0),
            "lat": lat, "lon": lon,
            "is_verified": True,
        })
    return drivers

@app.route("/choose_driver")
def choose_driver():
    if "user_id" not in session or session.get("role") != "user":
        flash("Sign in as user to book."); return redirect("/signin")
    patient = session.get("book_patient") or ""
    phone   = session.get("book_phone") or ""
    dest    = session.get("book_dest") or ""
    pick    = session.get("book_pick") or ""
    user_lat = session.get("book_lat"); user_lon = session.get("book_lon")

    conn = get_db_connection()
    all_drivers = fetch_driver_cards(conn)

    # Recent reviews
    cur = conn.cursor()
    cur.execute("""
        SELECT dr.driver_id, u.username, dr.stars, dr.comment
        FROM driver_ratings dr
        JOIN users u ON u.id = dr.rater_user_id
        ORDER BY dr.created_at DESC
        LIMIT 100
    """)
    rev_rows = cur.fetchall(); cur.close(); conn.close()
    reviews = {}
    for (did, rater, stars, comment) in rev_rows:
        reviews.setdefault(did, []).append({"rater": rater, "stars": stars, "comment": comment})

    # score = 0.7 rating + 0.3 (1 - distance_norm)
    drivers_scored = []
    for d in all_drivers:
        dist = None
        if user_lat and user_lon and d["lat"] is not None and d["lon"] is not None:
            dist = distance_km(float(user_lat), float(user_lon), float(d["lat"]), float(d["lon"]))
        rating = d["avg_rating"] or 0.0
        r_norm = max(0.0, min(1.0, rating/5.0))
        d_norm = 1.0 if dist is None else max(0.0, min(1.0, dist/10.0))
        score  = 0.7*r_norm + 0.3*(1.0 - d_norm)
        drivers_scored.append({
            "driver_id": d["driver_id"], "name": d["name"],
            "avg_rating": rating, "rating_count": d["rating_count"],
            "is_verified": d["is_verified"],
            "dist_km": None if dist is None else round(dist, 2),
            "score": score
        })
    drivers_scored.sort(key=lambda x: x["score"], reverse=True)

    return render_template("choose_driver.html",
                           drivers=drivers_scored, reviews=reviews,
                           patient=patient, phone=phone, dest=dest, pick=pick,
                           user_lat=user_lat, user_lon=user_lon)

@app.route("/request_driver", methods=["POST"])
def request_driver():
    if "user_id" not in session or session.get("role") != "user":
        flash("Sign in as user."); return redirect("/signin")

    user_id = session["user_id"]
    driver_id = int(request.form.get("driver_id"))
    patient = request.form.get("patient_name") or ""
    phone   = request.form.get("phone_no") or ""
    dest    = request.form.get("destination") or ""
    pick    = request.form.get("pickup_location") or ""
    user_lat = request.form.get("user_lat"); user_lon = request.form.get("user_lon")
    pickup_combined = pick or (f"GPS({user_lat},{user_lon})" if user_lat and user_lon else "")

    conn = get_db_connection()
    if not is_user_verified(conn, driver_id):
        conn.close(); flash("Selected driver is not verified yet. Choose another driver.")
        return redirect("/choose_driver")

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, driver_id, patient_name, phone_no, pickup_location, destination, status, priority)
        VALUES (%s,%s,%s,%s,%s,%s,'Pending','Normal')
        RETURNING id
    """, (user_id, driver_id, patient, phone, pickup_combined, dest))
    booking_id = cur.fetchone()[0]

    create_notification(conn, driver_id, "New Booking Request",
                        f"Booking #{booking_id}. Please accept or reject.")
    conn.commit(); cur.close(); conn.close()

    for k in ["book_patient","book_phone","book_dest","book_pick","book_lat","book_lon"]:
        session.pop(k, None)

    flash(f"Request sent. Booking #{booking_id} is Pending.")
    return redirect("/mybookings")


# ------------------------------
# Driver Requests (integrated workboard) & Trips (history)
# ------------------------------
@app.route("/driver/workboard")
def driver_workboard():
    """Legacy link: redirect to unified requests page."""
    return redirect("/driver/requests")

@app.route("/driver/requests")
def driver_requests():
    """
    Unified page:
      - Active (Accepted) bookings with Complete + Track + Phone
      - Pending requests with Accept/Reject + Track + Phone
    """
    if "user_id" not in session or session.get("role") != "driver":
        flash("Sign in as driver."); return redirect("/signin")
    did = session["user_id"]

    conn = get_db_connection(); cur = conn.cursor()
    # Active (Accepted)
    cur.execute("""
        SELECT id, (SELECT username FROM users WHERE id=user_id) AS user_name,
               phone_no, pickup_location, destination, booking_time, status
        FROM bookings
        WHERE driver_id=%s AND status='Accepted'
        ORDER BY booking_time DESC
    """, (did,))
    active_rows = cur.fetchall()
    # Pending
    cur.execute("""
        SELECT id, patient_name, phone_no, pickup_location, destination, booking_time, status
        FROM bookings
        WHERE driver_id=%s AND status='Pending'
        ORDER BY booking_time DESC
    """, (did,))
    pending_rows = cur.fetchall()
    cur.close(); conn.close()

    can_accept = session.get("driver_is_verified", False)
    return render_template("driver_requests.html",
                           active_rows=active_rows,
                           pending_rows=pending_rows,
                           can_accept=can_accept)

@app.route("/driver/trips")
def driver_trips():
    """History only: COMPLETED trips with rider details."""
    if "user_id" not in session or session.get("role") != "driver":
        flash("Sign in as driver."); return redirect("/signin")
    driver_id = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT b.id,
               (SELECT username FROM users WHERE id=b.user_id) AS user_name,
               b.phone_no,
               b.pickup_location,
               b.destination,
               b.status,
               b.booking_time
        FROM bookings b
        WHERE b.driver_id=%s AND b.status='Completed'
        ORDER BY b.booking_time DESC
    """, (driver_id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return render_template("driver_trips.html", rows=rows)

@app.post("/driver/accept/<int:booking_id>")
def driver_accept(booking_id):
    if "user_id" not in session or session.get("role") != "driver":
        flash("Sign in as driver."); return redirect("/signin")
    driver_id = session["user_id"]
    conn = get_db_connection()
    if not is_user_verified(conn, driver_id):
        conn.close(); flash("Not verified yet. Complete KYC.")
        return redirect("/driver/requests")
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET status='Accepted' WHERE id=%s AND driver_id=%s AND status='Pending'",
                (booking_id, driver_id))
    cur.execute("SELECT user_id FROM bookings WHERE id=%s", (booking_id,))
    row = cur.fetchone()
    if row:
        create_notification(conn, row[0], "Booking Accepted", f"Your booking #{booking_id} was accepted.")
    conn.commit(); cur.close(); conn.close()
    flash("Accepted.")
    return redirect("/driver/requests")

@app.post("/driver/reject/<int:booking_id>")
def driver_reject(booking_id):
    if "user_id" not in session or session.get("role") != "driver":
        flash("Sign in as driver."); return redirect("/signin")
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM bookings WHERE id=%s", (booking_id,))
    row = cur.fetchone()
    if row:
        create_notification(conn, row[0], "Booking Rejected", f"Driver rejected booking #{booking_id}.")
    conn.commit(); cur.close(); conn.close()
    flash("Rejected.")
    return redirect("/driver/requests")

@app.post("/driver/complete/<int:booking_id>")
def driver_complete(booking_id):
    if "user_id" not in session or session.get("role") != "driver":
        flash("Sign in as driver."); return redirect("/signin")
    driver_id = session["user_id"]
    conn = get_db_connection()
    if not is_user_verified(conn, driver_id):
        conn.close(); flash("Not verified yet.")
        return redirect("/driver/requests")
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET status='Completed' WHERE id=%s AND driver_id=%s AND status='Accepted'",
                (booking_id, driver_id))
    cur.execute("SELECT user_id FROM bookings WHERE id=%s", (booking_id,))
    row = cur.fetchone()
    if row:
        create_notification(conn, row[0], "Trip Completed", f"Booking #{booking_id} completed. Please rate your driver.")
    conn.commit(); cur.close(); conn.close()
    flash("Marked as Completed.")
    return redirect("/driver/requests")


# ------------------------------
# User bookings + rating (one per booking)
# ------------------------------
@app.route("/mybookings")
def my_bookings():
    if "user_id" not in session or session.get("role") != "user":
        flash("Sign in as user."); return redirect("/signin")
    uid = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT b.id,
               (SELECT username FROM users WHERE id=b.driver_id) as driver_name,
               b.destination, b.status, b.booking_time
        FROM bookings b
        WHERE b.user_id=%s
        ORDER BY b.booking_time DESC
    """, (uid,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return render_template("my_bookings.html", rows=rows)

@app.route("/rate_driver/<int:booking_id>", methods=["GET", "POST"])
def rate_driver(booking_id):
    if "user_id" not in session or session.get("role") != "user":
        flash("Sign in as user."); return redirect("/signin")
    uid = session["user_id"]
    if request.method == "POST":
        stars = int(request.form.get("stars")); comment = request.form.get("comment") or ""
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT driver_id FROM bookings WHERE id=%s AND user_id=%s AND status='Completed'",
                    (booking_id, uid))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close(); flash("You can only rate completed trips.")
            return redirect("/mybookings")
        driver_id = row[0]
        cur.execute("SELECT 1 FROM driver_ratings WHERE booking_id=%s AND rater_user_id=%s", (booking_id, uid))
        if cur.fetchone():
            cur.close(); conn.close(); flash("You already reviewed this trip.")
            return redirect("/mybookings")
        cur.execute("""
            INSERT INTO driver_ratings (booking_id, rater_user_id, driver_id, stars, comment)
            VALUES (%s,%s,%s,%s,%s)
        """, (booking_id, uid, driver_id, stars, comment))
        conn.commit(); cur.close(); conn.close()
        flash("Thanks for your review!")
        return redirect("/mybookings")
    return render_template("rate_driver.html")


# ------------------------------
# Dashboards (user/driver/admin)
# ------------------------------
@app.route("/dashboard/user")
def dashboard_user():
    if "user_id" not in session or session.get("role") != "user":
        flash("Sign in as user."); return redirect("/signin")
    uid = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT b.id,
               (SELECT username FROM users WHERE id=b.driver_id) as driver_name,
               b.destination, b.status, b.booking_time
        FROM bookings b
        WHERE b.user_id=%s
        ORDER BY b.booking_time DESC
        LIMIT 10
    """, (uid,))
    trips = cur.fetchall()
    cur.execute("""
        SELECT id, title, body, is_read, created_at
        FROM notifications
        WHERE user_id=%s
        ORDER BY created_at DESC
        LIMIT 15
    """, (uid,))
    notifs = cur.fetchall()
    cur.close(); conn.close()
    return render_template("dashboard_user.html", trips=trips, notifs=notifs)

@app.route("/dashboard/driver")
def dashboard_driver():
    if "user_id" not in session or session.get("role") != "driver":
        flash("Sign in as driver."); return redirect("/signin")
    did = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT b.id, (SELECT username FROM users WHERE id=b.user_id),
               b.destination, b.status, b.booking_time
        FROM bookings b
        WHERE b.driver_id=%s
        ORDER BY b.booking_time DESC
        LIMIT 10
    """, (did,))
    trips = cur.fetchall()
    cur.execute("""
        SELECT stars, COALESCE(comment,''), (SELECT username FROM users WHERE id=rater_user_id), created_at
        FROM driver_ratings
        WHERE driver_id=%s
        ORDER BY created_at DESC
        LIMIT 10
    """, (did,))
    reviews = cur.fetchall()
    cur.execute("SELECT COALESCE(AVG(stars),0) FROM driver_ratings WHERE driver_id=%s", (did,))
    avg_star = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM driver_ratings WHERE driver_id=%s", (did,))
    total_reviews = cur.fetchone()[0]
    cur.close(); conn.close()
    return render_template("dashboard_driver.html", trips=trips, reviews=reviews, avg_star=avg_star, total_reviews=total_reviews)

@app.route("/dashboard/admin")
def dashboard_admin():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Admin only."); return redirect("/signin")
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT b.id,
               (SELECT username FROM users WHERE id=b.user_id) as user_name,
               (SELECT username FROM users WHERE id=b.driver_id) as driver_name,
               b.destination, b.status, b.booking_time
        FROM bookings b
        ORDER BY b.booking_time DESC
        LIMIT 20
    """)
    bookings = cur.fetchall()
    cur.execute("SELECT id, username, role, is_verified FROM users ORDER BY id ASC LIMIT 100")
    users = cur.fetchall()
    cur.execute("""
        SELECT u.id, u.username, COALESCE(AVG(dr.stars),0) as avg, COUNT(dr.id) as cnt
        FROM users u
        JOIN driver_ratings dr ON dr.driver_id = u.id
        WHERE u.role='driver'
        GROUP BY u.id, u.username
        ORDER BY avg DESC, cnt DESC
        LIMIT 10
    """)
    top_drivers = cur.fetchall()
    # KYC preview
    cur.execute("""
        SELECT id, username, role, is_verified, kyc_role,
               email,
               citizenship_path, license_doc_path, bluebook_doc_path, ambulance_photo_path
        FROM users
        WHERE citizenship_path IS NOT NULL
           OR license_doc_path IS NOT NULL
           OR bluebook_doc_path IS NOT NULL
           OR ambulance_photo_path IS NOT NULL
        ORDER BY id DESC
        LIMIT 60
    """)
    kycs = cur.fetchall()
    cur.close(); conn.close()
    return render_template("dashboard_admin.html",
                           bookings=bookings, users=users, top_drivers=top_drivers, kycs=kycs)

@app.route("/admin/user/<int:user_id>")
def admin_user_detail(user_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Admin only."); return redirect("/signin")
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT id, username, email, role, is_verified, kyc_role,
               citizenship_path, license_doc_path, bluebook_doc_path, ambulance_photo_path
        FROM users WHERE id=%s
    """, (user_id,))
    u = cur.fetchone(); cur.close(); conn.close()
    if not u:
        flash("User not found."); return redirect("/dashboard/admin")
    return render_template("admin_user_detail.html", u=u)

@app.post("/admin/verify_user/<int:user_id>")
def admin_verify_user(user_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Admin only."); return redirect("/signin")
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE users SET is_verified=TRUE WHERE id=%s", (user_id,))
    conn.commit(); cur.close(); conn.close()
    flash(f"User #{user_id} verified.")
    return redirect(request.headers.get("Referer") or url_for("dashboard_admin"))

@app.post("/admin/reject_user/<int:user_id>")
def admin_reject_user(user_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Admin only."); return redirect("/signin")
    reason = request.form.get("reason") or "Not approved"
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE users SET is_verified=FALSE, is_online=FALSE WHERE id=%s", (user_id,))
    create_notification(conn, user_id, "KYC Rejected", reason)
    conn.commit(); cur.close(); conn.close()
    flash(f"User #{user_id} rejected.")
    return redirect(request.headers.get("Referer") or url_for("dashboard_admin"))


# ------------------------------
# KYC uploads
# ------------------------------
def _save_upload(field_name):
    f = request.files.get(field_name)
    if not f or f.filename == "": return None
    fn = secure_filename(f.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], f"{int(datetime.utcnow().timestamp())}_{fn}")
    f.save(path); return path

@app.route("/kyc", methods=["GET", "POST"])
def kyc():
    if "user_id" not in session:
        flash("Sign in."); return redirect("/signin")
    uid = session["user_id"]; role = session.get("role")
    if request.method == "POST":
        conn = get_db_connection(); cur = conn.cursor()
        if role == "driver":
            lic = _save_upload("license_doc")
            bb  = _save_upload("bluebook_doc")
            ph  = _save_upload("ambulance_photo")
            if lic: cur.execute("UPDATE users SET license_doc_path=%s WHERE id=%s", (lic, uid))
            if bb:  cur.execute("UPDATE users SET bluebook_doc_path=%s WHERE id=%s", (bb, uid))
            if ph:  cur.execute("UPDATE users SET ambulance_photo_path=%s WHERE id=%s", (ph, uid))
        else:
            cit = _save_upload("citizenship_doc")
            if cit: cur.execute("UPDATE users SET citizenship_path=%s WHERE id=%s", (cit, uid))
        cur.execute("UPDATE users SET kyc_role=%s WHERE id=%s", (role, uid))
        conn.commit(); cur.close(); conn.close()
        flash("KYC uploaded. Admin will verify you soon.")
        return redirect("/kyc")
    return render_template("kyc.html", role=role)


# ------------------------------
# Notifications
# ------------------------------
@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        flash("Sign in."); return redirect("/signin")
    uid = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT id, title, body, is_read, created_at
        FROM notifications
        WHERE user_id=%s
        ORDER BY created_at DESC
        LIMIT 50
    """, (uid,))
    notes = cur.fetchall(); cur.close(); conn.close()
    return render_template("notifications.html", notes=notes)

@app.get("/api/notifications/unread_count")
def api_unread_count():
    if "user_id" not in session: return {"count": 0}
    uid = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,))
    count = cur.fetchone()[0]; cur.close(); conn.close()
    return {"count": int(count)}

@app.post("/api/notifications/mark_read")
def api_mark_read():
    if "user_id" not in session: return {"ok": False}, 403
    uid = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read=TRUE WHERE user_id=%s AND is_read=FALSE", (uid,))
    conn.commit(); cur.close(); conn.close()
    return {"ok": True}


# ------------------------------
# Live Trip Tracking — strict privacy after completion
# ------------------------------
def booking_visible_to_current_user_for_track(booking_row):
    """
    booking_row = (id, user_id, driver_id, status)
    Rules:
      - Completed: nobody can track.
      - Admin: allowed if not completed.
      - Driver (assigned): allowed on Pending/Accepted.
      - Rider: allowed only on Accepted.
    """
    if not booking_row: return False
    uid = session.get("user_id"); role = session.get("role"); status = booking_row[3]
    if status == "Completed": return False
    if role == "admin": return True
    if role == "driver" and uid == booking_row[2] and status in ("Pending", "Accepted"):
        return True
    if role == "user" and uid == booking_row[1] and status == "Accepted":
        return True
    return False

@app.route("/track/<int:booking_id>")
def track_booking(booking_id):
    if "user_id" not in session:
        flash("Sign in first."); return redirect("/signin")

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, user_id, driver_id, status FROM bookings WHERE id=%s", (booking_id,))
    booking = cur.fetchone(); cur.close(); conn.close()

    if not booking:
        flash("Booking not found."); return redirect("/home")
    if booking[3] == "Completed":
        flash("Trip is completed. Live tracking is no longer available.")
        return redirect("/home")
    if not booking_visible_to_current_user_for_track(booking):
        if session.get("role") == "user":
            flash("Tracking will be available after the driver accepts.")
        else:
            flash("Not authorized to view this trip.")
        return redirect("/home")

    return render_template("track.html", booking_id=booking_id)

@app.route("/api/booking_positions/<int:booking_id>")
def api_booking_positions(booking_id):
    if "user_id" not in session:
        return {"error": "auth required"}, 403

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT b.id, b.user_id, ul.latitude, ul.longitude,
               b.driver_id, dl.latitude, dl.longitude, b.status
        FROM bookings b
        LEFT JOIN user_location   ul ON ul.user_id   = b.user_id
        LEFT JOIN driver_location dl ON dl.driver_id = b.driver_id
        WHERE b.id=%s
    """, (booking_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    if not row: return {"error": "not found"}, 404
    status = row[7]
    if status == "Completed":  # hard privacy stop
        return {"error": "forbidden"}, 403

    booking_meta = (row[0], row[1], row[4], status)
    if not booking_visible_to_current_user_for_track(booking_meta):
        return {"error": "forbidden"}, 403

    role = session.get("role")
    user_payload   = {"id": row[1], "lat": row[2], "lon": row[3]}
    driver_payload = {"id": row[4], "lat": row[5], "lon": row[6]}
    if role == "user" and status == "Pending":
        driver_payload["lat"] = None; driver_payload["lon"] = None

    return {"status": status, "user": user_payload, "driver": driver_payload}

# --- LIVE UPDATE HOOKS ---

@app.get("/api/driver/pending_count")
def api_driver_pending_count():
    """Driver: how many pending requests assigned to me? Used to detect new bookings live."""
    if "user_id" not in session or session.get("role") != "driver":
        return {"count": 0}, 200
    did = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bookings WHERE driver_id=%s AND status='Pending'", (did,))
    cnt = cur.fetchone()[0]
    cur.close(); conn.close()
    return {"count": int(cnt)}

@app.get("/api/user/suggestions_count")
def api_user_suggestions_count():
    """User: how many drivers currently available within recent ping window? (rough signal to refresh list)"""
    if "user_id" not in session or session.get("role") != "user":
        return {"count": 0}, 200
    # Reuse fetch_driver_cards scoring window; we only need the count
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        WITH busy AS (
            SELECT DISTINCT driver_id FROM bookings WHERE status='Accepted'
        )
        SELECT COUNT(*)
        FROM users u
        JOIN driver_location dl ON dl.driver_id = u.id
        WHERE u.role='driver'
          AND u.is_verified=TRUE
          AND u.is_online=TRUE
          AND dl.updated_at > NOW() - INTERVAL '5 minutes'
          AND u.id NOT IN (SELECT driver_id FROM busy)
    """)
    cnt = cur.fetchone()[0]
    cur.close(); conn.close()
    return {"count": int(cnt)}

# ------------------------------
# Driver API (compatibility endpoints)
# ------------------------------
@app.get("/driver/api/profile")
def driver_api_profile():
    """Compatibility: return current driver profile info.
    Some clients expect /driver/api/profile; mirror essential fields.
    """
    if "user_id" not in session or session.get("role") != "driver":
        return jsonify({"ok": False, "error": "driver only"}), 403
    did = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, username, is_verified, is_online FROM users WHERE id=%s", (did,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({
        "ok": True,
        "id": row[0],
        "username": row[1],
        "is_verified": bool(row[2]),
        "is_online": bool(row[3]),
    })

@app.get("/driver/api/assigned")
def driver_api_assigned():
    """Compatibility: list bookings assigned to the current driver.
    Returns separate arrays for active (Accepted) and pending (Pending).
    """
    if "user_id" not in session or session.get("role") != "driver":
        return jsonify({"ok": False, "error": "driver only"}), 403
    did = session["user_id"]
    conn = get_db_connection(); cur = conn.cursor()
    # Active (Accepted)
    cur.execute(
        """
        SELECT id, (SELECT username FROM users WHERE id=user_id) AS user_name,
               phone_no, pickup_location, destination, booking_time, status
        FROM bookings
        WHERE driver_id=%s AND status='Accepted'
        ORDER BY booking_time DESC
        """,
        (did,)
    )
    active_rows = cur.fetchall()
    # Pending
    cur.execute(
        """
        SELECT id, patient_name, phone_no, pickup_location, destination, booking_time, status
        FROM bookings
        WHERE driver_id=%s AND status='Pending'
        ORDER BY booking_time DESC
        """,
        (did,)
    )
    pending_rows = cur.fetchall()
    cur.close(); conn.close()

    def row_to_dict(r):
        return {
            "id": r[0],
            "user_name": r[1],
            "phone_no": r[2],
            "pickup_location": r[3],
            "destination": r[4],
            "booking_time": r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5]),
            "status": r[6],
        }

    return jsonify({
        "ok": True,
        "active": [row_to_dict(r) for r in active_rows],
        "pending": [row_to_dict(r) for r in pending_rows],
    })

@app.post("/driver/api/location")
def driver_api_location():
    """Compatibility: update driver location (same as /update_driver_location).
    Accepts form or JSON body with lat, lon.
    """
    if "user_id" not in session or session.get("role") != "driver":
        return jsonify({"ok": False, "error": "driver only"}), 403
    did = session["user_id"]

    data = request.get_json(silent=True) or {}
    lat_val = data.get("lat", request.form.get("lat"))
    lon_val = data.get("lon", request.form.get("lon"))
    try:
        lat = float(lat_val); lon = float(lon_val)
    except Exception:
        return jsonify({"ok": False, "error": "invalid coords"}), 400

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO driver_location (driver_id, latitude, longitude, updated_at)
        VALUES (%s,%s,%s,NOW())
        ON CONFLICT (driver_id) DO UPDATE
          SET latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude, updated_at=NOW()
        """,
        (did, lat, lon),
    )

    if is_user_verified(conn, did):
        cur.execute("UPDATE users SET is_online=TRUE, last_online_at=NOW() WHERE id=%s", (did,))
        made_online = True
    else:
        cur.execute("UPDATE users SET is_online=FALSE WHERE id=%s", (did,))
        made_online = False

    conn.commit(); cur.close(); conn.close()
    session["driver_is_online"] = made_online
    return jsonify({"ok": True, "online": made_online, "verified": session.get("driver_is_verified", False)})

# ------------------------------
# Errors
# ------------------------------
@app.errorhandler(404)
def not_found(e): return render_template("error.html", code=404, message="Not Found"), 404

@app.errorhandler(500)
def server_error(e): return render_template("error.html", code=500, message="Server Error"), 500


if __name__ == "__main__":
    app.run(debug=True)
