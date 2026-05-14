# 🚑 Ambulance Booking System

A full-stack web application built with **Flask** and **PostgreSQL** that enables users to book ambulances in real-time, track live driver locations, and manage the entire dispatch workflow across three distinct roles: **User**, **Driver**, and **Admin**.

---

## 📋 Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Database Schema](#database-schema)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [User Roles & Workflows](#user-roles--workflows)
- [API Endpoints](#api-endpoints)
- [Running Tests](#running-tests)
- [Deployment](#deployment)
- [Default Admin Credentials](#default-admin-credentials)

---

## ✨ Features

### For Users (Patients / Requesters)
- Register and sign in securely
- Book an ambulance by entering patient name, phone number, pickup location, and destination
- View available drivers ranked by a smart scoring algorithm (rating + proximity)
- Track assigned driver location live on a map
- View booking history and current booking status
- Rate and review the driver after trip completion
- Receive in-app notifications (booking accepted, trip completed, etc.)

### For Drivers
- Register as a driver and submit KYC documents (license, vehicle bluebook, ambulance photo)
- Toggle online/offline status (only verified drivers can go online)
- Accept or reject incoming booking requests
- Mark trips as completed
- View trip history and personal ratings dashboard
- Live location pings update their visibility to users

### For Admins
- View all bookings across the platform
- View and manage all user accounts
- Review and approve or reject KYC submissions with document preview
- See top-rated drivers leaderboard
- Receive reason-based rejection notifications back to drivers/users

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, Flask |
| Database | PostgreSQL (psycopg2) |
| Auth | Werkzeug PBKDF2 password hashing (SHA-256 legacy supported) |
| Frontend | Jinja2 templates, HTML/CSS, vanilla JavaScript |
| File Uploads | Werkzeug `secure_filename`, local filesystem |
| Maps & Tracking | Browser Geolocation API + custom polling |
| Testing | pytest, Flask test client |
| Deployment | Render.com (render.yaml included) |

---

## 📁 Project Structure

```
Ambulance_booking-main/
├── app.py                  # Main Flask application — all routes and business logic
├── database.py             # DB connection, schema initialization, admin seed
├── wsgi.py                 # WSGI entry point for production servers
├── requirements.txt        # Python dependencies
├── render.yaml             # Render.com deployment config
│
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Base layout with nav, flash messages, notification badge
│   ├── home.html           # Landing page
│   ├── signin.html         # Sign-in form
│   ├── signup.html         # Sign-up form
│   ├── book.html           # Booking form (user)
│   ├── choose_driver.html  # Driver selection with ratings and distance
│   ├── my_bookings.html    # User booking history
│   ├── rate_driver.html    # Post-trip rating form
│   ├── track.html          # Live map tracking page
│   ├── driver_requests.html    # Driver: active + pending bookings
│   ├── driver_trips.html       # Driver: completed trip history
│   ├── driver_workboard.html   # Legacy redirect page
│   ├── dashboard_user.html     # User dashboard with recent trips + notifications
│   ├── dashboard_driver.html   # Driver dashboard with ratings summary
│   ├── dashboard_admin.html    # Admin panel: users, bookings, KYC, top drivers
│   ├── admin_user_detail.html  # Admin: detailed user KYC view
│   ├── kyc.html            # KYC document upload form
│   ├── notifications.html  # Notification inbox
│   └── error.html          # 404 / 500 error page
│
├── static/
│   ├── css/
│   │   ├── style.css       # Main stylesheet
│   │   └── 1.css           # Supplementary styles
│   ├── js/
│   │   └── ui.async.js     # Async UI helpers (live polling, location updates)
│   └── uploads/            # KYC and ambulance photos uploaded by users
│
└── tests/
    ├── conftest.py                 # Pytest fixtures: isolated test DB per session
    ├── test_auth.py                # Sign-up and sign-in tests
    ├── test_booking_flow.py        # Full booking lifecycle tests
    ├── test_driver_status.py       # Driver online/offline status tests
    ├── test_notifications_api.py   # Notification count and mark-read API tests
    └── test_suggestions_filter.py  # Driver suggestions filtering logic tests
```

---

## 🗄 Database Schema

### `users`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| username | VARCHAR(100) | |
| email | VARCHAR(150) | UNIQUE |
| password | VARCHAR(255) | PBKDF2 / SHA-256 |
| role | VARCHAR(20) | `user`, `driver`, or `admin` |
| is_verified | BOOLEAN | Admin must verify before driver goes online |
| kyc_role | VARCHAR(20) | Role at time of KYC submission |
| citizenship_path | TEXT | Users' citizenship document path |
| license_doc_path | TEXT | Driver's license path |
| bluebook_doc_path | TEXT | Vehicle bluebook path |
| ambulance_photo_path | TEXT | Ambulance photo path |
| is_online | BOOLEAN | Driver availability flag |
| last_online_at | TIMESTAMP | |

### `bookings`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| user_id | INT FK → users | Requester |
| driver_id | INT FK → users | Assigned driver |
| patient_name | VARCHAR(100) | |
| phone_no | VARCHAR(20) | |
| pickup_location | TEXT | Address or GPS coordinates |
| destination | TEXT | |
| booking_time | TIMESTAMP | Auto-set |
| status | VARCHAR(20) | `Pending`, `Accepted`, `Completed` |
| priority | VARCHAR(20) | `Normal` or `Emergency` |

### `driver_location` / `user_location`
Upserted on each GPS ping. Drivers with a ping older than 5 minutes are excluded from the available driver list.

### `driver_ratings`
One review per booking per user (enforced via `UNIQUE(booking_id, rater_user_id)`). Stars 1–5.

### `notifications`
Lightweight inbox per user: title, body, read/unread flag.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ running locally
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/ambulance-booking.git
cd ambulance-booking

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure the database (see Configuration section)

# 5. Run the app — the DB and tables are auto-created on first start
python app.py
```

The app will be available at `http://127.0.0.1:5000`.

---

## ⚙️ Configuration

Database credentials are set in `database.py`:

```python
DB_CFG = {
    "database": "ambulance_db",
    "user":     "postgres",
    "password": "your_password",
    "host":     "127.0.0.1",
    "port":     5432,
}
```

> ⚠️ **Security note:** Do not commit real credentials to version control. Use environment variables (e.g. `DATABASE_URL`) in production — a Render.com-compatible implementation is provided in comments inside `database.py`.

The Flask `SECRET_KEY` defaults to `"dev-secret-please-change"` and can be overridden via the environment:

```bash
export SECRET_KEY="your-strong-random-secret"
```

---

## 👥 User Roles & Workflows

### 1. User (Patient)
```
Sign Up → Sign In → /book (fill form) → /choose_driver (see scored list)
→ Request Driver → /mybookings (monitor status) → /track/<id> (live map)
→ /rate_driver/<id> (after completion)
```

### 2. Driver
```
Sign Up (role=driver) → Sign In → /kyc (upload license, bluebook, photo)
→ Wait for admin verification → Go Online (/driver/set_status)
→ /driver/requests (accept/reject requests, complete active trips)
→ /dashboard/driver (view ratings and trip history)
```

### 3. Admin
```
Sign In (seeded admin account) → /dashboard/admin
→ Review KYC documents → Verify or Reject users
→ Monitor all bookings and users
```

---

## 🔌 API Endpoints

### Location Updates
| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/update_user_location` | user | Upsert user GPS coordinates |
| POST | `/update_driver_location` | driver | Upsert driver GPS + auto online/offline |
| POST | `/driver/set_status` | driver | Manually toggle online/offline |

### Live Tracking
| Method | Endpoint | Description |
|---|---|---|
| GET | `/track/<booking_id>` | Live map page (Pending/Accepted only) |
| GET | `/api/booking_positions/<booking_id>` | JSON: user + driver lat/lon |

### Polling / Counts
| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/notifications/unread_count` | any | Unread notification badge count |
| POST | `/api/notifications/mark_read` | any | Mark all notifications as read |
| GET | `/api/driver/pending_count` | driver | Number of pending booking requests |
| GET | `/api/user/suggestions_count` | user | Count of currently available drivers |

### Driver Compatibility API
| Method | Endpoint | Description |
|---|---|---|
| GET | `/driver/api/profile` | Driver profile (id, username, verified, online) |
| GET | `/driver/api/assigned` | Active + pending bookings for current driver |
| POST | `/driver/api/location` | Location update (accepts JSON or form body) |

---

## 🧪 Running Tests

The test suite uses an isolated PostgreSQL database created and torn down per test session.

```bash
# Make sure PostgreSQL is running with credentials matching DB_CFG in database.py
pytest tests/ -v
```

### Test coverage includes:
- **`test_auth.py`** — signup, signin, duplicate emails, wrong passwords
- **`test_booking_flow.py`** — full lifecycle: book → accept → complete → rate
- **`test_driver_status.py`** — online/offline toggle, unverified driver restrictions
- **`test_notifications_api.py`** — unread count, mark-read API
- **`test_suggestions_filter.py`** — driver filter: online, verified, fresh ping, not busy

---

## ☁️ Deployment (Render.com)

A `render.yaml` is included for one-click deployment on [Render](https://render.com):

```yaml
services:
  - type: web
    name: ambulance-flask-app
    env: python
    startCommand: python app.py
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: ambulance-db

databases:
  - name: ambulance-db
```

Switch `database.py` to use the `DATABASE_URL` environment variable (commented-out implementation is already provided in `database.py`).

---

## 🔑 Default Admin Credentials

An admin account is automatically seeded when the database is initialized:

| Field | Value |
|---|---|
| Email | `raj@gmail.com` |
| Password | `raj123` |
| Role | `admin` |

> ⚠️ **Change these credentials immediately after your first login in any non-development environment.**

---

## 📄 License

This project is open source. See your repository's LICENSE file for details.
