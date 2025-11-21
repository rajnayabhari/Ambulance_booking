# database.py — ensure PBKDF2 admin + unique review constraint
import psycopg2
from werkzeug.security import generate_password_hash

DB_CFG = {
    "database": "ambulance_db",
    "user": "postgres",
    "password": "@hybesty123",
    "host": "127.0.0.1",
    "port": 5432,
}

def get_db_connection():
    return psycopg2.connect(**DB_CFG)

def initialize_db():
    admin_conn = psycopg2.connect(database="postgres", user=DB_CFG["user"], password=DB_CFG["password"], host=DB_CFG["host"], port=DB_CFG["port"])
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_CFG["database"],))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE {DB_CFG['database']}")
    admin_conn.close()

    with get_db_connection() as conn:
        cur = conn.cursor()
        # users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('user','driver','admin')),
            is_verified BOOLEAN DEFAULT FALSE,
            kyc_role VARCHAR(20),
            citizenship_path TEXT,
            license_doc_path TEXT,
            bluebook_doc_path TEXT,
            ambulance_photo_path TEXT,
            is_online BOOLEAN DEFAULT FALSE,
            last_online_at TIMESTAMP
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_is_online ON users (is_online);")

        # bookings
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id),
            driver_id INT REFERENCES users(id),
            patient_name VARCHAR(100) NOT NULL,
            phone_no VARCHAR(20) NOT NULL,
            pickup_location TEXT,
            destination TEXT NOT NULL,
            booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending','Accepted','Completed')),
            priority VARCHAR(20) DEFAULT 'Normal' CHECK (priority IN ('Normal','Emergency'))
        );
        """)

        # locations
        cur.execute("""
        CREATE TABLE IF NOT EXISTS driver_location (
            driver_id INT PRIMARY KEY REFERENCES users(id),
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_location (
            user_id INT PRIMARY KEY REFERENCES users(id),
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # ratings
        cur.execute("""
        CREATE TABLE IF NOT EXISTS driver_ratings (
            id SERIAL PRIMARY KEY,
            booking_id INT REFERENCES bookings(id) ON DELETE CASCADE,
            rater_user_id INT REFERENCES users(id) ON DELETE CASCADE,
            driver_id INT REFERENCES users(id) ON DELETE CASCADE,
            stars INT NOT NULL CHECK (stars BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Unique: one review per booking per rater
        cur.execute("SELECT 1 FROM pg_constraint WHERE conname='uniq_rating_per_booking'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE driver_ratings ADD CONSTRAINT uniq_rating_per_booking UNIQUE (booking_id, rater_user_id)")

        # notifications
        cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(120) NOT NULL,
            body TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id);")

        # Admin seed (PBKDF2)
        admin_email = "raj@gmail.com"
        pbkdf2_hash = generate_password_hash("raj123", method="pbkdf2:sha256", salt_length=16)
        cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (admin_email,))
        row = cur.fetchone()
        if not row:
            cur.execute("""
                INSERT INTO users (username, email, password, role, is_verified)
                VALUES (%s, %s, %s, 'admin', TRUE)
            """, ("raj", admin_email, pbkdf2_hash))
        else:
            admin_id = row[0]
            cur.execute("""
                UPDATE users
                SET password=%s, role='admin', is_verified=TRUE, username='raj'
                WHERE id=%s
            """, (pbkdf2_hash, admin_id))
        conn.commit()
        cur.close()




# for render.com
# def get_db_connection():
#     result = urlparse.urlparse(os.environ['DATABASE_URL'])
#     username = result.username
#     password = result.password
#     database = result.path[1:]
#     hostname = result.hostname
#     port = result.port

#     return psycopg2.connect(
#         database=database,
#         user=username,
#         password=password,
#         host=hostname,
#         port=port
#     )
# def initialize_db():
#     db_url = os.environ['DATABASE_URL']
#     result = urlparse.urlparse(db_url)

#     conn = psycopg2.connect(
#         database=result.path[1:],
#         user=result.username,
#         password=result.password,
#         host=result.hostname,
#         port=result.port
#     )

#     with conn.cursor() as cursor:
#         # Users table
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS users (
#                 id SERIAL PRIMARY KEY,
#                 username VARCHAR(100),
#                 email VARCHAR(100) UNIQUE,
#                 password VARCHAR(255),
#                 role VARCHAR(20) DEFAULT 'user'
#             );
#         """)

#         # Ambulance bookings
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS ambulance_booking (
#                 booking_id SERIAL PRIMARY KEY,
#                 user_id INTEGER REFERENCES users(id),
#                 driver_id INTEGER REFERENCES users(id),
#                 patient_name VARCHAR(100),
#                 phone_no VARCHAR(20),
#                 pickup_location TEXT,
#                 destination TEXT,
#                 booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                 status VARCHAR(50) DEFAULT 'Pending'
#             );
#         """)

#         # Driver live location
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS driver_location (
#                 driver_id INTEGER PRIMARY KEY REFERENCES users(id),
#                 latitude DOUBLE PRECISION,
#                 longitude DOUBLE PRECISION,
#                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#             );
#         """)

#         # User live location
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS user_location (
#                 user_id INTEGER PRIMARY KEY REFERENCES users(id),
#                 latitude DOUBLE PRECISION,
#                 longitude DOUBLE PRECISION,
#                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#             );
#         """)

#         # Default admin user
#         default_email = 'raj@gmail.com'
#         default_password = hash_password('raj123')
#         cursor.execute("""
#             INSERT INTO users (username, email, password, role)
#             SELECT %s, %s, %s, %s
#             WHERE NOT EXISTS (
#                 SELECT 1 FROM users WHERE email = %s
#             );
#         """, ('raj', default_email, default_password, 'admin', default_email))

#     conn.commit()
#     conn.close()
