import json
import os
import re
import secrets
import smtplib
import ssl
import uuid
import hashlib
import hmac
import base64
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse, parse_qsl, urlencode

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ── dotenv ────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except Exception:
    pass

# ── Supabase Client ───────────────────────────────────────────────────────────
try:
    from supabase import create_client
except Exception as exc:
    create_client = None
    print(f"Supabase package unavailable: {exc}")

SUPABASE_PLACEHOLDERS = {
    "",
    "https://your-project-ref.supabase.co",
    "your-anon-key",
    "your-service-role-key",
}

supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
supabase_key = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or ""
).strip()

# Clear proxy settings that commonly break local Supabase/httpx initialization.
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

supabase = None
if create_client and supabase_url not in SUPABASE_PLACEHOLDERS and supabase_key not in SUPABASE_PLACEHOLDERS:
    try:
        supabase = create_client(supabase_url, supabase_key)
        print("Supabase auth connected")
    except Exception as e:
        print("Supabase auth disabled:", e)
        supabase = None
# ── SQLAlchemy / PostgreSQL ───────────────────────────────────────────────────
from sqlalchemy import (
    create_engine, text,
    Column, String, Boolean, Numeric, Integer, Text, DateTime, JSON
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.types import CHAR, TypeDecorator

def clean_env(value):
    return (value or "").strip().strip('"').strip("'")


BASE_DIR = Path(__file__).resolve().parent
SQLITE_FALLBACK_PATH = Path(os.getenv("SQLITE_FALLBACK_PATH") or "/tmp/microchip_cart.sqlite3")
if not os.getenv("VERCEL"):
    SQLITE_FALLBACK_PATH = BASE_DIR / "instance" / "local_store.sqlite3"
LOCAL_DATABASE_URL = "sqlite:///" + SQLITE_FALLBACK_PATH.resolve().as_posix()


def build_database_url():
    raw_url = clean_env(os.getenv("DATABASE_URL"))
    supabase_password = clean_env(os.getenv("SUPABASE_DB_PASSWORD"))
    supabase_host = clean_env(os.getenv("SUPABASE_DB_HOST")) or "db.ybbomppuyrucifdwgmpf.supabase.co"
    supabase_user = clean_env(os.getenv("SUPABASE_DB_USER")) or "postgres"
    supabase_name = clean_env(os.getenv("SUPABASE_DB_NAME")) or "postgres"
    supabase_port = clean_env(os.getenv("SUPABASE_DB_PORT")) or "5432"

    if supabase_password:
        database_url = (
            f"postgresql://{quote(supabase_user)}:{quote(supabase_password, safe='')}"
            f"@{supabase_host}:{supabase_port}/{supabase_name}"
        )
    elif raw_url and "[YOUR-PASSWORD]" not in raw_url:
        database_url = raw_url
        host_marker = f"@{supabase_host}"
        if host_marker in database_url and "://" in database_url:
            scheme, rest = database_url.split("://", 1)
            userinfo, host_and_path = rest.split(host_marker, 1)
            if ":" in userinfo:
                raw_user, raw_password = userinfo.split(":", 1)
                database_url = (
                    f"{scheme}://{quote(raw_user)}:{quote(raw_password, safe='')}"
                    f"{host_marker}{host_and_path}"
                )
    else:
        print("Database env not configured; using temporary SQLite fallback.")
        return LOCAL_DATABASE_URL

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg2"}:
        raise RuntimeError("DATABASE_URL must start with postgresql://")
    if "[YOUR-PASSWORD]" in database_url:
        raise RuntimeError("Replace [YOUR-PASSWORD] in DATABASE_URL with your real Supabase database password.")

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunparse(parsed._replace(query=urlencode(query)))


DATABASE_URL = build_database_url()
DATABASE_LABEL = "sqlite fallback" if DATABASE_URL.startswith("sqlite") else "postgresql"


def create_app_engine(database_url):
    if database_url.startswith("sqlite"):
        sqlite_path = database_url.replace("sqlite:///", "", 1)
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 10},
    )


engine = create_app_engine(DATABASE_URL)
DBSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class GUID(TypeDecorator):
    """Platform-independent UUIDs: PostgreSQL UUID, SQLite string."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return uuid.UUID(str(value)) if not isinstance(value, uuid.UUID) else value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(str(value))


class Base(DeclarativeBase):
    pass


# ── DB Models ─────────────────────────────────────────────────────────────────

class UserModel(Base):
    __tablename__ = "users"
    id             = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email          = Column(String(255), unique=True, nullable=False)
    phone          = Column(String(30), unique=True, nullable=True)
    password_hash  = Column(Text, nullable=True)
    name           = Column(String(255), nullable=True)
    full_name      = Column(String(255), nullable=True)
    account_type   = Column(String(10), default="B2C")
    role           = Column(String(30), default="customer")
    company_name   = Column(String(255), nullable=True)
    gstin          = Column(String(30), nullable=True)
    is_admin       = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)
    status         = Column(String(30), default="Active")
    last_login     = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BusinessProfileModel(Base):
    __tablename__ = "business_profiles"
    id               = Column(GUID(), primary_key=True)
    business_name    = Column(String(255), nullable=False)
    business_address = Column(Text, nullable=True)
    contact_number   = Column(String(30), nullable=False)
    gst_number       = Column(String(30), nullable=False)
    approval_status  = Column(String(30), default="Pending") # Pending, Approved, Rejected
    created_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ProductModel(Base):
    __tablename__ = "products"
    id            = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name          = Column(String(255), nullable=False)
    slug          = Column(String(255), unique=True, nullable=False)
    description   = Column(Text)
    category      = Column(String(100), default="Microchip")
    brand         = Column(String(100))
    model         = Column(String(100))
    sku           = Column(String(100))
    price         = Column(Numeric(10, 2), nullable=False)
    stock         = Column(Integer, default=0)
    image_url     = Column(Text)
    specs         = Column(JSON, default=dict)
    datasheet_url = Column(Text)
    warranty      = Column(String(200), default="7 days replacement")
    lead_time     = Column(String(200), default="Ready to dispatch")
    rating_sum    = Column(Integer, default=0)
    rating_count  = Column(Integer, default=0)
    review_count  = Column(Integer, default=0)
    views         = Column(Integer, default=0)
    cart_adds     = Column(Integer, default=0)
    is_active     = Column(Boolean, default=True)
    is_sample     = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OrderModel(Base):
    __tablename__ = "orders"
    id               = Column(GUID(), primary_key=True, default=uuid.uuid4)
    invoice_number   = Column(String(50))
    user_id          = Column(GUID(), nullable=True)
    customer         = Column(JSON, nullable=False, default=dict)
    items            = Column(JSON, nullable=False, default=list)
    totals           = Column(JSON, nullable=False, default=dict)
    payment_method   = Column(String(50), default="COD")
    payment_status   = Column(String(100), default="Demo placed - no payment captured")
    status           = Column(String(50), default="Pending")
    admin_notes      = Column(Text, default="")
    reviewed_at      = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ReviewModel(Base):
    __tablename__ = "reviews"
    id         = Column(GUID(), primary_key=True, default=uuid.uuid4)
    product_id = Column(GUID(), nullable=False)
    user_id    = Column(GUID(), nullable=True)
    user_name  = Column(String(255))
    rating     = Column(Integer, nullable=False)
    comment    = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EventModel(Base):
    __tablename__ = "events"
    id         = Column(GUID(), primary_key=True, default=uuid.uuid4)
    type       = Column(String(50), nullable=False)
    product_id = Column(GUID(), nullable=True)
    user_id    = Column(GUID(), nullable=True)
    event_metadata   = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SettingsModel(Base):
    __tablename__ = "settings"
    key   = Column(String(100), primary_key=True)
    value = Column(JSON)


class CommunityPostModel(Base):
    __tablename__ = "community_posts"
    id         = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id    = Column(GUID(), nullable=True)
    user_name  = Column(String(255), nullable=False)
    title      = Column(String(255), nullable=False)
    content    = Column(Text, nullable=False)
    category   = Column(String(50), default="Need Eyes")
    likes      = Column(Integer, default=0)
    liked_by   = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CommunityReplyModel(Base):
    __tablename__ = "community_replies"
    id         = Column(GUID(), primary_key=True, default=uuid.uuid4)
    post_id    = Column(GUID(), nullable=False)
    user_id    = Column(GUID(), nullable=True)
    user_name  = Column(String(255), nullable=False)
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def ensure_compatible_schema():
    if engine.dialect.name != "postgresql":
        return
    ddl_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_type VARCHAR(10) DEFAULT 'B2C'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gstin VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT false",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'Active'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(30) DEFAULT 'customer'",
        "ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT 'Microchip'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS brand VARCHAR(100)",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS model VARCHAR(100)",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS sku VARCHAR(100)",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS datasheet_url TEXT",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS warranty VARCHAR(200) DEFAULT '7 days replacement'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS lead_time VARCHAR(200) DEFAULT 'Ready to dispatch'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS rating_sum INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS rating_count INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS review_count INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS cart_adds INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_sample BOOLEAN DEFAULT false",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(50)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS total NUMERIC(10, 2)",
        "ALTER TABLE orders ALTER COLUMN total DROP NOT NULL",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer JSONB DEFAULT '{}'::jsonb",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS totals JSONB DEFAULT '{}'::jsonb",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50) DEFAULT 'COD'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status VARCHAR(100) DEFAULT 'Pending manual collection'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS admin_notes TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS user_name VARCHAR(255)",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_metadata JSONB DEFAULT '{}'::jsonb",
    ]
    with engine.begin() as connection:
        for statement in ddl_statements:
            connection.execute(text(statement))


def ensure_sqlite_schema():
    if engine.dialect.name != "sqlite":
        return
    ddl_statements = [
        "ALTER TABLE users ADD COLUMN account_type VARCHAR(10) DEFAULT 'B2C'",
        "ALTER TABLE users ADD COLUMN company_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN gstin VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN role VARCHAR(30) DEFAULT 'customer'",
        "ALTER TABLE users ADD COLUMN full_name VARCHAR(255)",
    ]
    with engine.begin() as connection:
        for statement in ddl_statements:
            try:
                connection.execute(text(statement))
            except SQLAlchemyError:
                pass
        user_columns = connection.execute(text("PRAGMA table_info(users)")).mappings().all()
        password_column = next((column for column in user_columns if column["name"] == "password_hash"), None)
        if password_column and password_column["notnull"]:
            connection.execute(text("""
                CREATE TABLE users_schema_fix (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    phone VARCHAR(30) UNIQUE,
                    password_hash TEXT,
                    name VARCHAR(255),
                    full_name VARCHAR(255),
                    account_type VARCHAR(10) DEFAULT 'B2C',
                    role VARCHAR(30) DEFAULT 'customer',
                    company_name VARCHAR(255),
                    gstin VARCHAR(30),
                    is_admin BOOLEAN DEFAULT 0,
                    email_verified BOOLEAN DEFAULT 0,
                    phone_verified BOOLEAN DEFAULT 0,
                    status VARCHAR(30) DEFAULT 'Active',
                    last_login DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            old_column_names = {column["name"] for column in user_columns}
            target_columns = [
                "id", "email", "phone", "password_hash", "name", "full_name",
                "account_type", "role", "company_name", "gstin", "is_admin",
                "email_verified", "phone_verified", "status", "last_login",
                "created_at", "updated_at",
            ]
            copy_columns = [column for column in target_columns if column in old_column_names]
            connection.execute(text(
                f"INSERT INTO users_schema_fix ({', '.join(copy_columns)}) "
                f"SELECT {', '.join(copy_columns)} FROM users"
            ))
            connection.execute(text("DROP TABLE users"))
            connection.execute(text("ALTER TABLE users_schema_fix RENAME TO users"))


def initialize_database():
    global engine, DBSession, DATABASE_LABEL
    try:
        Base.metadata.create_all(engine)
        ensure_compatible_schema()
        ensure_sqlite_schema()
    except SQLAlchemyError as exc:
        print(f"Database initialization failed; using SQLite fallback: {exc}")
        if os.getenv("APP_ENV") == "production" and not os.getenv("VERCEL"):
            raise
        engine = create_app_engine(LOCAL_DATABASE_URL)
        DBSession.configure(bind=engine)
        DATABASE_LABEL = "local sqlite"
        Base.metadata.create_all(engine)
        ensure_sqlite_schema()


# Create all tables if they don't exist yet, then patch older Supabase schemas.
initialize_database()


# ── DB session helper ─────────────────────────────────────────────────────────

def get_db():
    db = DBSession()
    try:
        yield db
    finally:
        db.close()


# ── Flask app ─────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "products"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config["SESSION_COOKIE_SECURE"]   = os.getenv("APP_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

ALLOWED_IMAGE_EXTENSIONS = {"webp"}
ADMIN_EMAIL              = (os.getenv("ADMIN_EMAIL", "admin@microchipcart.local")).strip().lower()
ADMIN_PASSWORD           = os.getenv("ADMIN_PASSWORD", "Admin@12345")
ADMIN_NOTIFICATION_EMAIL = (os.getenv("ADMIN_NOTIFICATION_EMAIL", ADMIN_EMAIL)).strip().lower()
OWNER_EMAIL              = (os.getenv("OWNER_EMAIL") or "owner@microchipcart.local").strip().lower()
OWNER_PASSWORD           = os.getenv("OWNER_PASSWORD") or "Owner@12345"
SMTP_PLACEHOLDERS        = {
    "",
    "yourgmail@gmail.com",
    "your-email@gmail.com",
    "noreply@yourdomain.com",
    "your-16-character-gmail-app-password",
}


# ── Utility helpers ───────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)

def now_iso():
    return now_utc().isoformat()

def money(value):
    return round(float(value or 0), 2)

def normalize_email(email):
    return (email or "").strip().lower()

def normalize_account_type(value):
    return "B2B" if str(value or "").upper() == "B2B" else "B2C"

GSTIN_REGEX = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"

def supabase_user_metadata(auth_user):
    if not auth_user:
        return {}
    metadata = getattr(auth_user, "user_metadata", None) or getattr(auth_user, "raw_user_meta_data", None) or {}
    return metadata if isinstance(metadata, dict) else {}

def supabase_account_type(auth_user, fallback="B2C"):
    metadata = supabase_user_metadata(auth_user)
    return normalize_account_type(metadata.get("account_type") or metadata.get("role") or fallback)

def session_login_for(user):
    session["user_id"] = str_id(user.id)
    if (user.account_type or "B2C") == "B2B" or getattr(user, "is_admin", False):
        session["admin_logged_in"] = True
        session["admin_role"] = "owner_admin" if getattr(user, "is_admin", False) else "distributor"
    else:
        session.pop("admin_logged_in", None)
        session.pop("admin_role", None)

def supabase_auth_signup(email, password):
    if not supabase:
        raise RuntimeError("missing Supabase env vars")
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        return getattr(response, "user", None), None
    except Exception as exc:
        print(f"Supabase signup failed: {exc}")
        return None, exc

def supabase_admin_client():
    if not create_client:
        return None
    service_role_key = clean_env(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    if supabase_url in SUPABASE_PLACEHOLDERS or service_role_key in SUPABASE_PLACEHOLDERS:
        return None
    try:
        return create_client(supabase_url, service_role_key)
    except Exception as exc:
        print(f"Supabase admin client unavailable: {exc}")
        return None

def auth_user_id(auth_user):
    if isinstance(auth_user, dict):
        return auth_user.get("id")
    return getattr(auth_user, "id", None) if auth_user else None

def auth_user_email(auth_user):
    if isinstance(auth_user, dict):
        return normalize_email(auth_user.get("email", ""))
    return normalize_email(getattr(auth_user, "email", "") if auth_user else "")

def auth_user_identities(auth_user):
    identities = getattr(auth_user, "identities", None)
    if identities is None:
        return None
    return identities if isinstance(identities, list) else list(identities or [])

def is_supabase_duplicate_error(exc):
    exc_str = str(exc or "").lower()
    return "already" in exc_str or "registered" in exc_str or "exists" in exc_str

def supabase_signup_existing_user(auth_user):
    identities = auth_user_identities(auth_user)
    return identities == []

def supabase_find_auth_user_by_email(email):
    admin_client = supabase_admin_client()
    if not admin_client:
        return None
    target = normalize_email(email)
    try:
        page = 1
        while True:
            users = admin_client.auth.admin.list_users(page=page, per_page=100)
            if not users:
                return None
            for auth_user in users:
                if auth_user_email(auth_user) == target:
                    return auth_user
            if len(users) < 100:
                return None
            page += 1
    except Exception as exc:
        print(f"Could not list Supabase Auth users: {exc}")
        return None

def supabase_prepare_email_otp_user(email):
    auth_user = supabase_find_auth_user_by_email(email)
    if auth_user:
        print("SUPABASE EMAIL OTP USER: existing auth user found.")
        return True, None

    admin_client = supabase_admin_client()
    if not admin_client:
        return False, "SUPABASE_SERVICE_ROLE_KEY is required to create an OTP auth user without sending a confirmation email."

    try:
        admin_client.auth.admin.create_user({
            "email": email,
            "password": secrets.token_urlsafe(32),
            "email_confirm": True,
            "user_metadata": {"otp_signup_pending": True},
        })
        print("SUPABASE EMAIL OTP USER: created auth user without confirmation email.")
        return True, None
    except Exception as exc:
        if is_supabase_duplicate_error(exc) and supabase_find_auth_user_by_email(email):
            print("SUPABASE EMAIL OTP USER: auth user already existed after create attempt.")
            return True, None
        return False, str(exc)

def supabase_response_user(response):
    if isinstance(response, dict):
        return response.get("user") or response
    return getattr(response, "user", None) or response

def supabase_ensure_verified_auth_user(email, password, metadata=None):
    admin_client = supabase_admin_client()
    if not admin_client:
        return None, "SUPABASE_SERVICE_ROLE_KEY is required to create the verified auth user."

    attrs = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": metadata or {},
    }
    try:
        response = admin_client.auth.admin.create_user(attrs)
        auth_user = supabase_response_user(response)
        if auth_user:
            print("SUPABASE AUTH USER SETUP: created verified auth user.")
            return auth_user, None
        return None, "Supabase auth user was created but no user was returned."
    except Exception as exc:
        if not is_supabase_duplicate_error(exc):
            return None, str(exc)

    auth_user = supabase_find_auth_user_by_email(email)
    user_id = auth_user_id(auth_user)
    if not user_id:
        return None, "This email already exists in Supabase Auth but could not be loaded for update."

    try:
        response = admin_client.auth.admin.update_user_by_id(str(user_id), attrs)
        updated_user = supabase_response_user(response) or auth_user
        print("SUPABASE AUTH USER SETUP: updated existing verified auth user.")
        return updated_user, None
    except Exception as update_exc:
        return None, str(update_exc)

def supabase_delete_auth_user(user_id):
    admin_client = supabase_admin_client()
    if not admin_client or not user_id:
        return False
    try:
        admin_client.auth.admin.delete_user(str(user_id))
        return True
    except Exception as exc:
        print(f"Could not delete Supabase Auth user {user_id}: {exc}")
        return False

def supabase_signup_with_metadata(email, password, account_type):
    response = supabase.auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {
                "account_type": account_type,
                "role": "business" if account_type == "B2B" else "customer",
            }
        }
    })
    return getattr(response, "user", None)

def supabase_signup_recovering_orphan(email, password, account_type):
    auth_user = None
    try:
        auth_user = supabase_signup_with_metadata(email, password, account_type)
        if auth_user and not supabase_signup_existing_user(auth_user):
            return auth_user, None
    except Exception as exc:
        if not is_supabase_duplicate_error(exc):
            return None, f"Supabase Auth failed: {str(exc)}"

    stale_auth_user = supabase_find_auth_user_by_email(email) or (
        auth_user if auth_user_email(auth_user) == normalize_email(email) else None
    )
    if not stale_auth_user:
        return None, "This email already exists in Supabase Auth. Delete it from Supabase Authentication users, then try again."

    if not supabase_delete_auth_user(auth_user_id(stale_auth_user)):
        return None, "This email still exists in Supabase Auth. Set SUPABASE_SERVICE_ROLE_KEY or delete it from Supabase Authentication users, then try again."

    try:
        return supabase_signup_with_metadata(email, password, account_type), None
    except Exception as exc:
        return None, f"Supabase Auth failed after cleanup: {str(exc)}"

def supabase_set_user_password(user_id, password, metadata=None):
    metadata = metadata or {}
    try:
        supabase.auth.update_user({"password": password, "data": metadata})
        return True, None
    except Exception as user_exc:
        admin_client = supabase_admin_client()
        if not admin_client:
            return False, str(user_exc)
        try:
            admin_client.auth.admin.update_user_by_id(str(user_id), {
                "password": password,
                "user_metadata": metadata,
                "email_confirm": True,
            })
            return True, None
        except Exception as admin_exc:
            return False, str(admin_exc)

def supabase_verify_email_otp(email, otp):
    email = normalize_email(email)
    otp = str(otp or "").strip()
    print("SUPABASE VERIFY EMAIL:", email)
    print("SUPABASE VERIFY OTP LENGTH:", len(otp or ""))
    last_error = None
    for verify_type in ("email", "signup"):
        payload = {
            "email": email,
            "token": otp,
            "type": verify_type,
        }
        print("SUPABASE VERIFY TYPE:", verify_type)
        try:
            response = supabase.auth.verify_otp(payload)
            print("SUPABASE OTP VERIFICATION SUCCESS")
            return response, verify_type, None
        except Exception as exc:
            last_error = exc
            print(f"SUPABASE OTP VERIFICATION FAILURE ({verify_type}): {exc}")
    return None, "signup", last_error

def supabase_auth_login(email, password):
    if not supabase:
        raise RuntimeError("missing Supabase env vars")
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return getattr(response, "user", None), None
    except Exception as exc:
        print(f"Supabase login failed: {exc}")
        return None, exc

def supabase_verify_password(email, password):
    if not supabase:
        return None, None, RuntimeError("missing Supabase env vars")
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return getattr(response, "user", None), getattr(response, "session", None), None
    except Exception as exc:
        print(f"Supabase password verification failed: {exc}")
        return None, None, exc

def supabase_update_password_for_session(auth_session, new_password):
    if not supabase:
        raise RuntimeError("missing Supabase env vars")
    access_token = getattr(auth_session, "access_token", None)
    refresh_token = getattr(auth_session, "refresh_token", None)
    if access_token and refresh_token:
        supabase.auth.set_session(access_token, refresh_token)
    return supabase.auth.update_user({"password": new_password})

def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",", 1)[0] or request.remote_addr or "unknown").strip()

def slugify(value):
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
    return value or secrets.token_hex(4)

def str_id(uid):
    """Convert UUID object to string safely."""
    return str(uid) if uid else None

def smtp_config_status():
    host = clean_env(os.getenv("SMTP_HOST"))
    username = clean_env(os.getenv("SMTP_USERNAME"))
    password = clean_env(os.getenv("SMTP_PASSWORD"))
    sender = clean_env(os.getenv("SMTP_FROM")) or username or ADMIN_NOTIFICATION_EMAIL
    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not sender or sender.lower() in SMTP_PLACEHOLDERS:
        missing.append("SMTP_FROM")
    if username and username.lower() in SMTP_PLACEHOLDERS:
        missing.append("SMTP_USERNAME")
    if username and (not password or password.lower() in SMTP_PLACEHOLDERS):
        missing.append("SMTP_PASSWORD")
    return not missing, missing


# ── Model serializers ─────────────────────────────────────────────────────────

def user_to_dict(u: UserModel) -> dict:
    return {
        "id":             str_id(u.id),
        "name":           u.name or "",
        "email":          u.email,
        "phone":          u.phone or "",
        "account_type":   u.account_type or "B2C",
        "company_name":   u.company_name or "",
        "gstin":          u.gstin or "",
        "status":         u.status or "Active",
        "email_verified": u.email_verified,
        "phone_verified": u.phone_verified,
        "last_login":     u.last_login.isoformat() if u.last_login else "",
        "created_at":     u.created_at.isoformat() if u.created_at else "",
    }

def public_user(u):
    if u is None:
        return None
    if isinstance(u, dict):
        return {k: u.get(k) for k in ("id", "name", "full_name", "email", "phone", "account_type", "role", "company_name", "gstin", "is_admin", "created_at")}
    return {
        "id":           str_id(u.id),
        "name":         u.name or "",
        "full_name":    u.full_name or u.name or "",
        "email":        u.email,
        "phone":        u.phone or "",
        "account_type": u.account_type or "B2C",
        "role":         u.role or ("business" if u.account_type == "B2B" else "customer"),
        "company_name": u.company_name or "",
        "gstin":        u.gstin or "",
        "is_admin":     bool(u.is_admin),
        "created_at":   u.created_at.isoformat() if u.created_at else "",
    }

def auth_redirect_url(user):
    if isinstance(user, dict):
        account_type = user.get("account_type") or "B2C"
        is_admin = user.get("is_admin") or False
    else:
        account_type = getattr(user, "account_type", None) or "B2C"
        is_admin = getattr(user, "is_admin", False) or False
    if is_admin:
        return "/admin"
    return "/admin" if account_type == "B2B" else "/"

def product_to_dict(p: ProductModel) -> dict:
    count = p.rating_count or 0
    rating_avg = round((p.rating_sum or 0) / count, 1) if count > 0 else 0
    return {
        "id":           str_id(p.id),
        "name":         p.name,
        "slug":         p.slug,
        "description":  p.description or "",
        "category":     p.category or "",
        "brand":        p.brand or "",
        "model":        p.model or "",
        "sku":          p.sku or "",
        "price":        money(p.price),
        "stock":        p.stock or 0,
        "image_url":    p.image_url or "/static/images/product-placeholder.webp",
        "specs":        p.specs or {},
        "datasheet_url":p.datasheet_url or "",
        "warranty":     p.warranty or "",
        "lead_time":    p.lead_time or "",
        "rating_sum":   p.rating_sum or 0,
        "rating_count": p.rating_count or 0,
        "review_count": p.review_count or 0,
        "rating_avg":   rating_avg,
        "views":        p.views or 0,
        "cart_adds":    p.cart_adds or 0,
        "active":       p.is_active,
        "sample":       p.is_sample,
        "created_at":   p.created_at.isoformat() if p.created_at else "",
        "updated_at":   p.updated_at.isoformat() if p.updated_at else "",
    }

def order_to_dict(o: OrderModel) -> dict:
    return {
        "id":             str_id(o.id),
        "invoice_number": o.invoice_number or "",
        "user_id":        str_id(o.user_id),
        "customer":       o.customer or {},
        "items":          o.items or [],
        "totals":         o.totals or {},
        "payment_method": o.payment_method or "COD",
        "payment_status": o.payment_status or "",
        "status":         o.status or "Pending",
        "admin_notes":    o.admin_notes or "",
        "reviewed_at":    o.reviewed_at.isoformat() if o.reviewed_at else "",
        "created_at":     o.created_at.isoformat() if o.created_at else "",
        "updated_at":     o.updated_at.isoformat() if o.updated_at else "",
    }

def review_to_dict(r: ReviewModel) -> dict:
    return {
        "id":         str_id(r.id),
        "product_id": str_id(r.product_id),
        "user_id":    str_id(r.user_id),
        "name":       r.user_name or "Anonymous",
        "rating":     r.rating,
        "comment":    r.comment or "",
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }

def can_delete_community_item(item) -> bool:
    if session.get("admin_logged_in"):
        return True
    user = current_user()
    return bool(user and str_id(getattr(item, "user_id", None)) == str_id(user.id))

def post_to_dict(p: CommunityPostModel, db) -> dict:
    reply_count = db.query(CommunityReplyModel).filter_by(post_id=p.id).count()
    return {
        "id":         str_id(p.id),
        "user_id":    str_id(p.user_id),
        "user_name":  p.user_name or "Anonymous",
        "title":      p.title,
        "content":    p.content,
        "category":   p.category or "Need Eyes",
        "likes":      p.likes or 0,
        "liked_by":   p.liked_by or [],
        "reply_count": reply_count,
        "can_delete": can_delete_community_item(p),
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }

def reply_to_dict(r: CommunityReplyModel) -> dict:
    return {
        "id":         str_id(r.id),
        "post_id":    str_id(r.post_id),
        "user_id":    str_id(r.user_id),
        "user_name":  r.user_name or "Anonymous",
        "content":    r.content,
        "can_delete": can_delete_community_item(r),
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


# ── Session / auth helpers ────────────────────────────────────────────────────

def request_auth_token(data=None):
    if data and data.get("auth_token"):
        return data.get("auth_token")
    return request.headers.get("X-Auth-Token")

def current_user(auth_token=None):
    user_id = session.get("user_id")
    if user_id:
        db = DBSession()
        try:
            user = db.query(UserModel).filter_by(id=user_id).first()
            if user:
                return user
            session.pop("user_id", None)
            session.pop("admin_logged_in", None)
        except SQLAlchemyError as exc:
            print(f"Could not load session user: {exc}")
            session.pop("user_id", None)
            session.pop("admin_logged_in", None)
            session.pop("admin_role", None)
        finally:
            db.close()
    return user_from_auth_token(auth_token or request_auth_token())

def auth_token_secret():
    return str(app.secret_key or os.getenv("FLASK_SECRET_KEY") or "microchip-cart").encode("utf-8")

def make_auth_token(user, max_age_seconds=60 * 60 * 24 * 14):
    if not user:
        return ""
    payload = {
        "user_id": str_id(user.id),
        "exp": int((now_utc() + timedelta(seconds=max_age_seconds)).timestamp()),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    sig = hmac.new(auth_token_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def user_from_auth_token(token):
    token = (token or "").strip()
    if "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(auth_token_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        padded = body + ("=" * (-len(body) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(now_utc().timestamp()):
        return None
    user_id = payload.get("user_id")
    if not user_id:
        return None
    db = DBSession()
    try:
        user = db.query(UserModel).filter_by(id=user_id).first()
        if user:
            session_login_for(user)
        return user
    finally:
        db.close()

def require_user(auth_token=None):
    user = current_user(auth_token)
    if not user:
        abort(make_response(api_error("Please login first.", 401)[0], 401))
    return user

def require_checkout_user(data):
    user = require_user(request_auth_token(data))
    return user

def require_admin():
    if not session.get("admin_logged_in"):
        abort(make_response(api_error("Admin login required.", 401)[0], 401))

def owner_auth_version():
    fingerprint = f"{OWNER_EMAIL}\0{OWNER_PASSWORD}".encode("utf-8")
    return hashlib.sha256(fingerprint).hexdigest()[:24]

def owner_session_is_current():
    return session.get("owner_logged_in") and session.get("owner_auth_version") == owner_auth_version()

def clear_owner_session():
    session.pop("owner_logged_in", None)
    session.pop("owner_auth_version", None)
    if session.get("admin_role") == "owner_admin":
        session.pop("admin_logged_in", None)
        session.pop("admin_role", None)

def require_owner():
    if not owner_session_is_current():
        clear_owner_session()
        abort(make_response(api_error("Owner login required.", 401)[0], 401))


# ── Response helpers ──────────────────────────────────────────────────────────

def api_ok(payload=None, status=200):
    return jsonify({"ok": True, "success": True, **(payload or {})}), status

def api_error(message, status=400):
    return jsonify({"ok": False, "success": False, "error": message}), status


# ── Email (SMTP) ──────────────────────────────────────────────────────────────

def send_email(to_email, subject, text_body, html_body=None):
    host     = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender   = os.getenv("SMTP_FROM", username or ADMIN_NOTIFICATION_EMAIL)
    configured, missing = smtp_config_status()
    if not configured:
        print(f"SMTP not configured ({', '.join(missing)}). Skipping: {subject} -> {to_email}")
        return False
    port    = int(os.getenv("SMTP_PORT", "587"))
    use_ssl = os.getenv("SMTP_SSL", "false").lower() == "true"
    use_tls = os.getenv("SMTP_TLS", "true").lower()  == "true"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
                if username and password:
                    s.login(username, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as s:
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                if username and password:
                    s.login(username, password)
                s.send_message(msg)
        return True
    except Exception as exc:
        print(f"SMTP send failed: {exc}")
        return False

# ── Product helpers ───────────────────────────────────────────────────────────

def parse_specs(raw):
    if isinstance(raw, dict):
        return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(k).strip()}
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k).strip(): str(v).strip() for k, v in parsed.items() if str(k).strip()}
    except Exception:
        pass
    specs = {}
    for line in raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            if k:
                specs[k] = v.strip()
    return specs

def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def next_product_image_path():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    used = set()
    for img in UPLOAD_DIR.glob("*.webp"):
        m = re.fullmatch(r"(\d+)\.webp", img.name)
        if m:
            used.add(int(m.group(1)))
    db = DBSession()
    try:
        for p in db.query(ProductModel).all():
            m = re.search(r"/static/uploads/products/(\d+)\.webp$", p.image_url or "")
            if m:
                used.add(int(m.group(1)))
    finally:
        db.close()
    index = 0
    while index in used:
        index += 1
    return {
        "index":        index,
        "filename":     f"{index}.webp",
        "web_path":     f"/static/uploads/products/{index}.webp",
        "display_path": f"static/uploads/products/{index}.webp",
        "absolute_path":str(UPLOAD_DIR / f"{index}.webp"),
        "exists":       (UPLOAD_DIR / f"{index}.webp").exists(),
    }

def save_product_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    filename = secure_filename(file_storage.filename)
    if not allowed_image(filename):
        raise ValueError("Product image must be a .webp file.")
    suggestion  = next_product_image_path()
    destination = UPLOAD_DIR / suggestion["filename"]
    file_storage.save(destination)
    return suggestion["web_path"]


# ── Order helpers ─────────────────────────────────────────────────────────────

def make_invoice_number():
    return f"MC-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

def order_totals(items):
    subtotal = sum(money(i["unit_price"]) * int(i["quantity"]) for i in items)
    tax      = money(subtotal * 0.18)
    shipping = 0 if subtotal >= 999 else 79
    return {
        "subtotal": money(subtotal),
        "tax":      tax,
        "shipping": money(shipping),
        "total":    money(subtotal + tax + shipping),
    }

def render_invoice_html(order):
    return render_template("invoice.html", order=order, generated_at=now_iso())

def send_order_email(order):
    html = render_invoice_html(order)
    lines = [
        f"New order: {order['invoice_number']}",
        f"Customer: {order['customer']['name']} <{order['customer']['email']}>",
        f"Total: INR {order['totals']['total']}",
        "Items:",
    ] + [f"- {i['name']} x {i['quantity']} = INR {i['line_total']}" for i in order["items"]]
    return send_email(
        ADMIN_NOTIFICATION_EMAIL,
        f"New Microchip Cart order {order['invoice_number']}",
        "\n".join(lines),
        html,
    )


# ── Analytics ─────────────────────────────────────────────────────────────────

def analytics_payload():
    db = DBSession()
    try:
        products = db.query(ProductModel).filter_by(is_sample=False).all()
        orders   = db.query(OrderModel).all()
        events   = db.query(EventModel).all()
        approved = [o for o in orders if o.status == "Approved"]

        product_rows = []
        for p in products:
            pid     = str_id(p.id)
            units   = revenue = order_mentions = 0
            for o in approved:
                for item in (o.items or []):
                    if item.get("product_id") == pid:
                        units        += int(item.get("quantity") or 0)
                        revenue      += money(item.get("line_total"))
                        order_mentions += 1
            views      = p.views or 0
            cart_adds  = p.cart_adds or 0
            reviews    = p.review_count or 0
            conversion = round((units / views) * 100, 1) if views else 0
            interest   = views + (cart_adds * 3) + (reviews * 2) + (order_mentions * 5)
            product_rows.append({
                "id":             pid,
                "name":           p.name,
                "sku":            p.sku or "",
                "sample":         p.is_sample,
                "views":          views,
                "cart_adds":      cart_adds,
                "reviews":        reviews,
                "units_sold":     units,
                "revenue":        money(revenue),
                "conversion":     conversion,
                "interest_score": interest,
            })
        product_rows.sort(key=lambda r: (r["revenue"], r["interest_score"]), reverse=True)

        status_counts = {}
        for o in orders:
            status_counts[o.status or "Pending"] = status_counts.get(o.status or "Pending", 0) + 1

        event_counts = {}
        for e in events:
            event_counts[e.type or "unknown"] = event_counts.get(e.type or "unknown", 0) + 1

        return {
            "products":    product_rows,
            "status_counts": status_counts,
            "event_counts":  event_counts,
            "top_product":   product_rows[0] if product_rows else None,
        }
    finally:
        db.close()

def owner_overview_payload():
    db = DBSession()
    try:
        users = db.query(UserModel).order_by(UserModel.created_at.desc()).all()
        business_profiles = db.query(BusinessProfileModel).order_by(BusinessProfileModel.created_at.desc()).all()
        products = db.query(ProductModel).order_by(ProductModel.created_at.desc()).all()
        orders = db.query(OrderModel).order_by(OrderModel.created_at.desc()).all()
        events = db.query(EventModel).order_by(EventModel.created_at.desc()).limit(120).all()
        settings_row = db.query(SettingsModel).filter_by(key="store").first()
        analytics = analytics_payload()

        customers = [u for u in users if (u.account_type or "B2C") != "B2B"]
        businesses = [u for u in users if (u.account_type or "B2C") == "B2B"]
        profile_by_id = {str_id(profile.id): profile for profile in business_profiles}

        spend_by_email = {}
        orders_by_email = {}
        last_order_by_email = {}
        b2b_revenue = 0
        b2c_revenue = 0
        for order in orders:
            customer = order.customer or {}
            email = normalize_email(customer.get("email"))
            total = money((order.totals or {}).get("total"))
            order_type = (customer.get("order_type") or (order.totals or {}).get("order_type") or "").upper()
            if not order_type:
                business = customer.get("business") if isinstance(customer.get("business"), dict) else {}
                order_type = (business.get("order_type") or "B2C").upper()
            if order_type == "B2B":
                b2b_revenue += total
            else:
                b2c_revenue += total
            if email:
                spend_by_email[email] = spend_by_email.get(email, 0) + total
                orders_by_email[email] = orders_by_email.get(email, 0) + 1
                last_order_by_email.setdefault(email, order.created_at.isoformat() if order.created_at else "")

        customer_rows = []
        for user in customers:
            email = normalize_email(user.email)
            customer_rows.append({
                **user_to_dict(user),
                "orders": orders_by_email.get(email, 0),
                "spend": money(spend_by_email.get(email, 0)),
                "last_order": last_order_by_email.get(email, ""),
            })

        business_rows = []
        for user in businesses:
            email = normalize_email(user.email)
            profile = profile_by_id.get(str_id(user.id))
            business_rows.append({
                **user_to_dict(user),
                "company_name": (profile.business_name if profile else user.company_name) or "",
                "business_address": (profile.business_address if profile else "") or "",
                "gstin": (profile.gst_number if profile else user.gstin) or "",
                "approval_status": (profile.approval_status if profile else user.status) or "Pending",
                "orders": orders_by_email.get(email, 0),
                "spend": money(spend_by_email.get(email, 0)),
                "last_order": last_order_by_email.get(email, ""),
            })

        category_counts = {}
        inventory_value = 0
        low_stock = []
        for product in products:
            category = product.category or "Uncategorized"
            category_counts[category] = category_counts.get(category, 0) + 1
            inventory_value += money(product.price) * int(product.stock or 0)
            if not product.is_sample and int(product.stock or 0) <= 5:
                low_stock.append(product_to_dict(product))

        revenue = sum(money((o.totals or {}).get("total")) for o in orders)
        average_order = money(revenue / len(orders)) if orders else 0
        event_counts = analytics.get("event_counts", {})
        cart_adds = event_counts.get("cart_add", 0)
        checkout_opens = event_counts.get("checkout_open", 0)
        cart_dropoff = max(cart_adds - checkout_opens, 0)

        return {
            "cards": {
                "customers": len(customers),
                "business_distributors": len(businesses),
                "pending_businesses": len([p for p in business_profiles if (p.approval_status or "Pending") == "Pending"]),
                "products": len([p for p in products if not p.is_sample]),
                "orders": len(orders),
                "revenue": money(revenue),
                "average_order": average_order,
                "b2b_revenue": money(b2b_revenue),
                "b2c_revenue": money(b2c_revenue),
                "pending_orders": len([o for o in orders if (o.status or "Pending") == "Pending"]),
                "inventory_value": money(inventory_value),
                "cart_dropoff": cart_dropoff,
            },
            "customers": customer_rows,
            "businesses": business_rows,
            "orders": [order_to_dict(o) for o in orders],
            "products": [product_to_dict(p) for p in products],
            "events": [{
                "id": str_id(e.id),
                "type": e.type,
                "product_id": str_id(e.product_id),
                "user_id": str_id(e.user_id),
                "metadata": e.event_metadata or {},
                "created_at": e.created_at.isoformat() if e.created_at else "",
            } for e in events],
            "settings": settings_row.value if settings_row else {},
            "analytics": analytics,
            "insights": {
                "category_counts": category_counts,
                "low_stock": low_stock[:10],
                "top_products": (analytics.get("products") or [])[:8],
                "status_counts": analytics.get("status_counts", {}),
                "event_counts": event_counts,
            },
        }
    finally:
        db.close()


# ── Bootstrap (sample products + default settings) ───────────────────────────

SAMPLE_PRODUCTS_DATA = [
    {
        "name": "STM32F407VGT6 Development MCU",
        "slug": "stm32f407vgt6-development-mcu",
        "description": "High-performance ARM Cortex-M4 microcontroller for robotics, automation, and embedded control projects.",
        "category": "Microcontroller", "brand": "STMicroelectronics", "model": "STM32F407VGT6",
        "sku": "MC-ST-407VG", "price": 1299, "stock": 38,
        "image_url": "/static/images/samples/sample-0.webp",
        "specs": {"Core": "ARM Cortex-M4", "Clock": "168 MHz", "Flash": "1 MB", "RAM": "192 KB", "Package": "LQFP-100", "Voltage": "1.8V - 3.6V"},
        "rating_sum": 23, "rating_count": 5, "review_count": 5,
    },
    {
        "name": "ESP32-WROOM-32E WiFi Bluetooth Module",
        "slug": "esp32-wroom-32e-wifi-bluetooth-module",
        "description": "Compact dual-core wireless module with WiFi and Bluetooth for IoT gateways, sensors, and connected products.",
        "category": "Wireless Module", "brand": "Espressif", "model": "ESP32-WROOM-32E",
        "sku": "MC-ES-WROOM32E", "price": 489, "stock": 74,
        "image_url": "/static/images/samples/sample-1.webp",
        "specs": {"Core": "Dual-core Xtensa LX6", "Clock": "240 MHz", "Connectivity": "WiFi 802.11 b/g/n, BLE", "Flash": "4 MB", "GPIO": "34 programmable pins", "Voltage": "3.0V - 3.6V"},
        "rating_sum": 42, "rating_count": 9, "review_count": 9,
    },
    {
        "name": "ATmega328P-PU 8-bit Microcontroller",
        "slug": "atmega328p-pu-8-bit-microcontroller",
        "description": "Reliable DIP package MCU for Arduino-compatible boards, prototyping, timing circuits, and student projects.",
        "category": "Microcontroller", "brand": "Microchip", "model": "ATmega328P-PU",
        "sku": "MC-MP-328PU", "price": 265, "stock": 116,
        "image_url": "/static/images/samples/sample-2.webp",
        "specs": {"Core": "8-bit AVR", "Clock": "20 MHz", "Flash": "32 KB", "SRAM": "2 KB", "EEPROM": "1 KB", "Package": "DIP-28"},
        "rating_sum": 31, "rating_count": 7, "review_count": 7,
    },
]

def ensure_bootstrap_data():
    db = DBSession()
    try:
        # Default settings
        if not db.query(SettingsModel).filter_by(key="store").first():
            db.add(SettingsModel(key="store", value={
                "store_name":   "Microchip Cart",
                "support_email": ADMIN_NOTIFICATION_EMAIL,
                "announcement": "Cyber-blue component deals for engineers, labs, and hardware teams.",
                "currency":     "INR",
                "created_at":   now_iso(),
            }))
            db.commit()

        # Sample products
        if db.query(ProductModel).count() == 0:
            for data in SAMPLE_PRODUCTS_DATA:
                db.add(ProductModel(
                    name=data["name"], slug=data["slug"], description=data["description"],
                    category=data["category"], brand=data["brand"], model=data["model"],
                    sku=data["sku"], price=data["price"], stock=data["stock"],
                    image_url=data["image_url"], specs=data["specs"],
                    rating_sum=data["rating_sum"], rating_count=data["rating_count"],
                    review_count=data["review_count"], is_active=True, is_sample=True,
                ))
            db.commit()
    finally:
        db.close()


ensure_bootstrap_data()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Pages
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def storefront_page():
    db = DBSession()
    try:
        row = db.query(SettingsModel).filter_by(key="store").first()
        settings = row.value if row else {}
    finally:
        db.close()
    return render_template("index.html", settings=settings, page_mode="home")


@app.get("/products")
def products_page():
    db = DBSession()
    try:
        row = db.query(SettingsModel).filter_by(key="store").first()
        settings = row.value if row else {}
    finally:
        db.close()
    return render_template("index.html", settings=settings, page_mode="products")

@app.get("/community")
def community_page():
    db = DBSession()
    try:
        row = db.query(SettingsModel).filter_by(key="store").first()
        settings = row.value if row else {}
    finally:
        db.close()
    return render_template("community/index.html", settings=settings, user=public_user(current_user()), page_mode="community")

@app.get("/help")
def help_page():
    db = DBSession()
    try:
        row = db.query(SettingsModel).filter_by(key="store").first()
        settings = row.value if row else {}
    finally:
        db.close()
    return render_template("help.html", settings=settings, page_mode="help")

@app.get("/login")
def login_page():
    return redirect("/#login")

@app.get("/signup")
def signup_page():
    return redirect("/#signup")

@app.get("/admin")
def admin_page():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login_page"))
    is_owner_admin = session.get("admin_role") == "owner_admin" or session.get("owner_logged_in")
    return render_template("admin.html", store_mode=DATABASE_LABEL, admin_email=ADMIN_EMAIL, is_owner_admin=is_owner_admin)

@app.get("/admin/login")
def admin_login_page():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_page"))
    return render_template("admin_login.html", admin_email=ADMIN_EMAIL)

@app.get("/admin/orders/<order_id>/invoice")
def admin_invoice(order_id):
    require_admin()
    db = DBSession()
    try:
        order = db.query(OrderModel).filter_by(id=order_id).first()
    finally:
        db.close()
    if not order:
        abort(404)
    return render_invoice_html(order_to_dict(order))

@app.get("/owner")
def owner_page():
    if session.get("admin_role") == "distributor" and not session.get("owner_logged_in"):
        return redirect(url_for("admin_page"))
    if not owner_session_is_current():
        clear_owner_session()
        return redirect(url_for("owner_login_page"))
    return render_template("owner_admin.html", store_mode=DATABASE_LABEL, owner_email=OWNER_EMAIL)

@app.get("/owner/login")
def owner_login_page():
    if owner_session_is_current():
        return redirect(url_for("owner_page"))
    clear_owner_session()
    return render_template("owner_login.html", owner_email=OWNER_EMAIL)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Config
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/config")
def api_config():
    db = DBSession()
    try:
        row      = db.query(SettingsModel).filter_by(key="store").first()
        settings = row.value if row else {}
        sample_mode = not db.query(ProductModel).filter_by(is_sample=False, is_active=True).count()
    finally:
        db.close()
    smtp_ok, smtp_missing = smtp_config_status()
    return api_ok({
        "settings":       settings,
        "sample_mode":    sample_mode,
        "store_mode":     DATABASE_LABEL,
        "smtp_configured": smtp_ok,
        "smtp_missing":    smtp_missing,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Auth
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def api_health():
    db_ok = False
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    smtp_ok, smtp_missing = smtp_config_status()
    supabase_configured = bool(clean_env(os.getenv("SUPABASE_DB_HOST")) or clean_env(os.getenv("DATABASE_URL")))
    supabase_connected = engine.dialect.name == "postgresql" and db_ok
    return api_ok({
        "status": "ok" if db_ok else "database_error",
        "database": "connected" if db_ok else "unavailable",
        "store_mode": DATABASE_LABEL,
        "supabase_configured": supabase_configured,
        "supabase_connected": supabase_connected,
        "smtp_configured": smtp_ok,
        "smtp_missing": smtp_missing,
        "environment": os.getenv("APP_ENV", "development"),
        "time": now_iso(),
    }, 200 if db_ok else 503)


phone_otps = {}
email_otp_last_sent = {}
EMAIL_OTP_COOLDOWN_SECONDS = 60
EMAIL_OTP_LENGTH = 6
EMAIL_OTP_TTL_SECONDS = 10 * 60
INVALID_EMAIL_OTP_MESSAGE = "Invalid or expired OTP. Please request a new code."

def email_otp_digest(email, otp):
    secret = str(app.secret_key or FLASK_SECRET_KEY or "microchip-cart").encode("utf-8")
    message = f"{normalize_email(email)}:{str(otp or '').strip()}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()

def email_otp_token_signature(email, digest, expires_at):
    secret = str(app.secret_key or FLASK_SECRET_KEY or "microchip-cart").encode("utf-8")
    message = f"{normalize_email(email)}:{digest}:{expires_at}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()

def make_email_otp_token(email, otp, expires_at):
    expires_at_text = expires_at.isoformat()
    digest = email_otp_digest(email, otp)
    payload = {
        "email": normalize_email(email),
        "digest": digest,
        "expires_at": expires_at_text,
        "sig": email_otp_token_signature(email, digest, expires_at_text),
    }
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")

def read_email_otp_token(token):
    try:
        raw = base64.urlsafe_b64decode(str(token or "").encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, "bad_token"

    email = normalize_email(payload.get("email"))
    digest = payload.get("digest")
    expires_at_text = payload.get("expires_at")
    sig = payload.get("sig")
    if not email or not digest or not expires_at_text or not sig:
        return None, "bad_token"
    expected_sig = email_otp_token_signature(email, digest, expires_at_text)
    if not hmac.compare_digest(sig, expected_sig):
        return None, "bad_signature"
    try:
        expires_at = datetime.fromisoformat(expires_at_text)
    except Exception:
        return None, "bad_expiry"
    return {"email": email, "digest": digest, "expires_at": expires_at}, None

def send_app_email_otp(email):
    otp = f"{secrets.randbelow(10 ** EMAIL_OTP_LENGTH):0{EMAIL_OTP_LENGTH}d}"
    expires_at = now_utc() + timedelta(seconds=EMAIL_OTP_TTL_SECONDS)
    text_body = (
        f"Your MicroChip Cart verification code is {otp}.\n\n"
        "This code expires in 10 minutes. Do not share it with anyone."
    )
    html_body = (
        "<p>Your MicroChip Cart verification code is:</p>"
        f"<h2 style=\"letter-spacing:4px;\">{otp}</h2>"
        "<p>This code expires in 10 minutes. Do not share it with anyone.</p>"
    )
    if not send_email(email, f"Your MicroChip Cart OTP: {otp}", text_body, html_body):
        return None
    return make_email_otp_token(email, otp, expires_at)

def local_email_verification_fallback(email):
    smtp_ok, _ = smtp_config_status()
    if supabase or smtp_ok:
        return None
    otp = "000000"
    expires_at = now_utc() + timedelta(seconds=EMAIL_OTP_TTL_SECONDS)
    return {
        "otp": otp,
        "otp_token": make_email_otp_token(email, otp, expires_at),
        "message": "Email OTP is unavailable on this deployment. Continue with the pre-filled verification code.",
    }

def can_auto_create_test_account():
    return not supabase and engine.dialect.name == "sqlite" and os.getenv("APP_ENV", "development") != "production"

def create_local_test_user(db, email, password, requested_type):
    account_type = normalize_account_type(requested_type or "B2C")
    full_name = email.split("@", 1)[0]
    user = UserModel(
        email=email,
        password_hash=generate_password_hash(password),
        name=full_name,
        full_name=full_name,
        account_type=account_type,
        role="business" if account_type == "B2B" else "customer",
        is_admin=False,
        email_verified=True,
        phone_verified=False,
        status="Pending" if account_type == "B2B" else "Active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db.add(user)
    db.flush()
    if account_type == "B2B":
        db.add(BusinessProfileModel(
            id=user.id,
            business_name=full_name,
            business_address="",
            contact_number="",
            gst_number="",
            approval_status="Pending",
            created_at=now_utc(),
            updated_at=now_utc(),
        ))
    return user

def verify_app_email_otp(email, otp, otp_token):
    email = normalize_email(email)
    otp = str(otp or "").strip()
    token_record, token_error = read_email_otp_token(otp_token)
    if not token_record:
        print(f"APP EMAIL OTP TOKEN FAILURE: {token_error}")
        return False, token_error
    if token_record["email"] != email:
        print("APP EMAIL OTP EMAIL MISMATCH:", mask_email_for_log(email), mask_email_for_log(token_record["email"]))
        return False, "email_mismatch"
    if now_utc() > token_record["expires_at"]:
        print("APP EMAIL OTP EXPIRED")
        return False, "expired"
    actual = email_otp_digest(email, otp)
    print("APP EMAIL OTP VERIFY EMAIL:", email)
    print("APP EMAIL OTP VERIFY LENGTH:", len(otp))
    if hmac.compare_digest(token_record["digest"], actual):
        print("APP EMAIL OTP VERIFICATION SUCCESS")
        return True, None
    print("APP EMAIL OTP VERIFICATION FAILURE: invalid")
    return False, "invalid"

def signup_payload():
    data = request.get_json(silent=True) or {}
    data["email"] = normalize_email(data.get("email"))
    data["name"] = (data.get("name") or data.get("full_name") or "").strip()
    data["full_name"] = (data.get("full_name") or data.get("name") or "").strip()
    data["phone"] = (data.get("phone") or "").strip()
    data["password"] = data.get("password") or ""
    data["account_type"] = normalize_account_type(data.get("account_type"))
    data["company_name"] = (data.get("company_name") or "").strip()
    data["gstin"] = (data.get("gstin") or "").strip().upper()
    data["business_address"] = (data.get("business_address") or "").strip()
    return data

def normalize_email_otp(value):
    return str(value or "").strip()

def mask_email_for_log(email):
    email = normalize_email(email)
    if "@" not in email:
        return email or "(blank)"
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        masked_name = name[:1] + "*"
    else:
        masked_name = name[:2] + "***" + name[-1:]
    return f"{masked_name}@{domain}"

def validate_signup_payload(data, require_otp=False):
    name = data.get("name") or data.get("full_name")
    if not name or not data.get("email") or not data.get("password"):
        return "Name, email and password are required."
    if require_otp and not (data.get("otp") or "").strip():
        return "Email OTP is required."
    if require_otp and not re.fullmatch(rf"\d{{{EMAIL_OTP_LENGTH}}}", data.get("otp") or ""):
        return INVALID_EMAIL_OTP_MESSAGE
    if len(data.get("password") or "") < 6:
        return "Password must be at least 6 characters."
    if data.get("account_type") == "B2B":
        if not data.get("company_name"):
            return "Business Name is required for business accounts."
        if data.get("gstin") and not re.match(GSTIN_REGEX, data["gstin"]):
            return "Invalid GST format. Please enter a valid 15-character GSTIN."
    return None

def create_or_update_verified_user(db, auth_user, data, store_password=False):
    email = data["email"]
    account_type = data["account_type"]
    role = "business" if account_type == "B2B" else "customer"
    full_name = data.get("full_name") or data.get("name") or email.split("@", 1)[0]
    phone = data.get("phone") or None
    auth_id = auth_user_id(auth_user)

    existing = db.query(UserModel).filter_by(email=email).first()
    if existing and existing.email_verified:
        return None, "This email already has an account."
    if phone:
        phone_user = db.query(UserModel).filter(UserModel.phone == phone).first()
        if phone_user and (not existing or str_id(phone_user.id) != str_id(existing.id)):
            return None, "This phone number is already registered."

    user = existing
    if not user:
        user = UserModel(email=email, created_at=getattr(auth_user, "created_at", now_utc()))
        if auth_id:
            user.id = auth_id
        db.add(user)
    elif auth_id and str_id(user.id) != str_id(auth_id):
        old_id = user.id
        profile = db.query(BusinessProfileModel).filter_by(id=old_id).first()
        if profile:
            profile.id = auth_id
        user.id = auth_id

    user.name = full_name
    user.full_name = full_name
    user.phone = phone
    user.password_hash = generate_password_hash(data["password"]) if store_password else None
    user.account_type = account_type
    user.role = role
    user.company_name = data.get("company_name") if account_type == "B2B" else None
    user.gstin = data.get("gstin") if account_type == "B2B" else None
    user.is_admin = False
    user.email_verified = True
    user.phone_verified = False
    user.status = "Pending" if account_type == "B2B" else "Active"
    user.updated_at = now_utc()
    db.flush()

    if account_type == "B2B":
        business = db.query(BusinessProfileModel).filter_by(id=user.id).first()
        if not business:
            business = BusinessProfileModel(id=user.id)
            db.add(business)
        business.business_name = data.get("company_name")
        business.business_address = data.get("business_address") or ""
        business.contact_number = phone or ""
        business.gst_number = data.get("gstin") or ""
        business.approval_status = "Pending"
        business.updated_at = now_utc()

    return user, None

@app.post("/api/auth/send-email-otp")
def api_send_email_otp():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email"))
    print("SEND EMAIL OTP REQUEST EMAIL:", email or "(missing)")
    if not email:
        print("SEND EMAIL OTP ERROR: missing email.")
        return api_error("Email is required.", 400)

    db = DBSession()
    try:
        existing = db.query(UserModel).filter_by(email=email).first()
        if existing and existing.email_verified:
            print("SEND EMAIL OTP ERROR: email already has a verified account.")
            return api_error("This email already has an account.", 400)
    finally:
        db.close()

    print("APP EMAIL OTP SEND EMAIL:", email)
    otp_token = send_app_email_otp(email)
    if not otp_token:
        fallback = local_email_verification_fallback(email)
        if fallback:
            print("APP EMAIL OTP FALLBACK: SMTP unavailable; using local signed verification token.")
            email_otp_last_sent[email] = now_utc()
            return api_ok({
                "message": fallback["message"],
                "otp_token": fallback["otp_token"],
                "otp": fallback["otp"],
                "verification_fallback": True,
                "cooldown_seconds": 10,
            })
        print("APP EMAIL OTP SEND ERROR: SMTP send failed.")
        return api_error("Could not send email OTP. Please check SMTP settings.", 400)
    print("APP EMAIL OTP SEND RESULT: success")
    email_otp_last_sent[email] = now_utc()
    return api_ok({"message": "OTP sent to your email.", "otp_token": otp_token})

@app.post("/api/auth/verify-email-otp")
def api_verify_email_otp():
    data = signup_payload()
    data["otp"] = normalize_email_otp(data.get("otp"))
    verify_type = "email"
    print("OTP VERIFY REQUEST")
    print("OTP VERIFY EMAIL:", data.get("email"))
    print("OTP VERIFY LENGTH:", len(data.get("otp") or ""))
    print("VERIFY TYPE:", "app-email")
    validation_error = validate_signup_payload(data, require_otp=True)
    if validation_error:
        print(f"OTP VERIFY VALIDATION FAILED: {validation_error}")
        return api_error(validation_error, 400)

    otp_ok, otp_error = verify_app_email_otp(data["email"], data["otp"], data.get("otp_token"))
    if not otp_ok:
        print(f"APP EMAIL OTP VERIFICATION FAILED: {otp_error}")
        return api_error(INVALID_EMAIL_OTP_MESSAGE, 400)

    print("APP EMAIL OTP VERIFIED")
    metadata = {
        "name": data.get("full_name") or data.get("name"),
        "account_type": data["account_type"],
        "role": "business" if data["account_type"] == "B2B" else "customer",
    }
    auth_user = None
    store_password = False
    if supabase:
        auth_user, auth_error = supabase_ensure_verified_auth_user(data["email"], data["password"], metadata)
        if not auth_user:
            print(f"Supabase auth user setup failed after OTP verification: {auth_error}")
            return api_error("Email verified, but auth setup failed. Please try again.", 400)
    else:
        print("SUPABASE AUTH NOT CONFIGURED: creating local password user after OTP verification.")
        store_password = True

    db = DBSession()
    try:
        user, user_error = create_or_update_verified_user(db, auth_user, data, store_password=store_password)
        if user_error:
            print(f"LOCAL USER SETUP AFTER OTP FAILED: {user_error}")
            if user_error == "This email already has an account.":
                existing_user = db.query(UserModel).filter_by(email=data["email"]).first()
                db.rollback()
                return api_ok({
                    "message": "Email already verified. Please login.",
                    "user": public_user(existing_user),
                })
            db.rollback()
            return api_ok({
                "message": "Account created. Please login.",
                "profile_warning": user_error,
            }, 201)
        db.commit()
        db.refresh(user)
        message = (
            "Business account created. Phone/GST verification and admin approval are pending."
            if data["account_type"] == "B2B"
            else "Email verified. Account created successfully. Please login."
        )
        return api_ok({"message": message, "user": public_user(user)}, 201)
    except Exception as exc:
        db.rollback()
        print(f"LOCAL USER SETUP EXCEPTION AFTER AUTH SUCCESS: {exc}")
        if isinstance(exc, IntegrityError):
            error_text = str(getattr(exc, "orig", exc)).lower()
            if "phone" in error_text:
                return api_ok({
                    "message": "Account created. Please login.",
                    "profile_warning": "This phone number is already registered.",
                }, 201)
            if "email" in error_text:
                return api_ok({
                    "message": "Email already verified. Please login.",
                })
        return api_ok({
            "message": "Account created. Please login.",
            "profile_warning": str(exc),
        }, 201)
    finally:
        db.close()

@app.post("/api/auth/send-phone-otp")
def api_send_phone_otp():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return api_error("Phone number is required.")
    otp = str(secrets.randbelow(900000) + 100000)
    phone_otps[phone] = otp
    print(f"\n[MOCK SMS] OTP for {phone} is: {otp}\n")
    return api_ok({"message": "OTP sent."})


@app.post("/api/auth/signup")
def api_signup_compat():
    data = signup_payload()
    validation_error = validate_signup_payload(data)
    if validation_error:
        return api_error(validation_error, 400)

    last_sent = email_otp_last_sent.get(data["email"])
    if last_sent:
        elapsed = (now_utc() - last_sent).total_seconds()
        if elapsed < EMAIL_OTP_COOLDOWN_SECONDS:
            remaining = max(1, int(EMAIL_OTP_COOLDOWN_SECONDS - elapsed))
            return api_ok({
                "message": f"OTP already sent. Please wait {remaining} seconds before requesting another.",
                "requires_email_otp": True,
                "cooldown_seconds": remaining,
                "user": None,
                "redirect_url": None,
            })

    db = DBSession()
    try:
        existing = db.query(UserModel).filter_by(email=data["email"]).first()
        if existing and existing.email_verified:
            return api_error("This email already has an account.", 400)
        if data["phone"]:
            phone_user = db.query(UserModel).filter_by(phone=data["phone"]).first()
            if phone_user and (not existing or str_id(phone_user.id) != str_id(existing.id)):
                return api_error("This phone number is already registered.", 400)
    except Exception as e:
        return api_error(f"Error during signup: {str(e)}", 409)
    finally:
        db.close()

    print("APP SIGNUP EMAIL OTP SEND EMAIL:", data["email"])
    otp_token = send_app_email_otp(data["email"])
    if not otp_token:
        fallback = local_email_verification_fallback(data["email"])
        if fallback:
            print("APP SIGNUP FALLBACK: SMTP unavailable; returning local signed verification token.")
            email_otp_last_sent[data["email"]] = now_utc()
            return api_ok({
                "message": fallback["message"],
                "requires_email_otp": True,
                "otp_token": fallback["otp_token"],
                "otp": fallback["otp"],
                "verification_fallback": True,
                "cooldown_seconds": 10,
                "user": None,
                "redirect_url": None,
            })
        print("APP SIGNUP EMAIL OTP SEND ERROR: SMTP send failed.")
        return api_error("Could not send email OTP. Please check SMTP settings.", 400)
    email_otp_last_sent[data["email"]] = now_utc()
    return api_ok({
        "message": "OTP sent to your email.",
        "requires_email_otp": True,
        "otp_token": otp_token,
        "user": None,
        "redirect_url": None,
    })


@app.post("/api/auth/login")
def api_login_direct():
    """Password login for customer and business accounts."""
    data     = request.get_json(silent=True) or {}
    email    = normalize_email(data.get("email"))
    password = data.get("password") or ""
    requested_type = data.get("account_type")
    
    if not email or not password:
        return api_error("Email and password are required.", 400)

    db = DBSession()
    try:
        if not supabase:
            user = db.query(UserModel).filter_by(email=email).first()
            if not user and can_auto_create_test_account():
                print(f"LOCAL TEST AUTH: auto-creating fallback account for {mask_email_for_log(email)}")
                user = create_local_test_user(db, email, password, requested_type)
            if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
                return api_error("Invalid email or password.", 401)
            if requested_type and normalize_account_type(requested_type) != normalize_account_type(user.account_type):
                return api_error("Please choose the correct account type for this email.", 403)
            if not user.email_verified and not getattr(user, "is_admin", False):
                return api_error("Please verify your email before logging in.", 403)
            if (user.status or "Active") not in ("Active", "Pending"):
                return api_error("This account is not active. Please contact support.", 403)
            user.last_login = now_utc()
            db.commit()
            db.refresh(user)
            session_login_for(user)
            return api_ok({"user": public_user(user), "auth_token": make_auth_token(user), "redirect_url": auth_redirect_url(user)})

        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            auth_user = res.user
        except Exception as exc:
            exc_str = str(exc).lower()
            if "invalid" in exc_str or "credentials" in exc_str:
                return api_error("Invalid email or password.", 401)
            return api_error(f"Supabase Auth failed: {str(exc)}", 401)

        if not auth_user:
            return api_error("Invalid email or password.", 401)

        user = db.query(UserModel).filter_by(id=auth_user.id).first()
        if not user:
            user = db.query(UserModel).filter_by(email=email).first()
            if user:
                user.id = auth_user.id
                db.flush()

        email_verified = bool(getattr(auth_user, "email_confirmed_at", None))
        account_type = supabase_account_type(auth_user, requested_type or "B2C")
        role = "business" if account_type == "B2B" else "customer"

        if not user:
            user = UserModel(
                id=auth_user.id,
                email=email,
                phone=auth_user.phone or None,
                password_hash=None,
                name=email.split("@", 1)[0],
                full_name=email.split("@", 1)[0],
                account_type=account_type,
                role=role,
                is_admin=False,
                email_verified=email_verified,
                status="Active",
                created_at=getattr(auth_user, "created_at", now_utc()),
            )
            db.add(user)
            db.flush()
        else:
            user.email_verified = email_verified
            if not user.role:
                user.role = role
            user.password_hash = None

        if not user.email_verified and not getattr(user, "is_admin", False):
            db.rollback()
            return api_error("Please verify your email before logging in.", 403)

        user.last_login = now_utc()
        db.commit()
        db.refresh(user)
        session_login_for(user)
        return api_ok({"user": public_user(user), "auth_token": make_auth_token(user), "redirect_url": auth_redirect_url(user)})
    except Exception as exc:
        db.rollback()
        print(f"Login failed unexpectedly: {exc}")
        return api_error(f"Login failed: {str(exc)}", 500)
    finally:
        db.close()


@app.post("/api/auth/logout")
def api_logout():
    if supabase:
        try:
            supabase.auth.sign_out()
        except Exception as exc:
            print(f"Supabase logout failed: {exc}")
    session.pop("user_id", None)
    session.pop("admin_logged_in", None)
    return api_ok()


@app.get("/api/auth/me")
def api_me():
    user = current_user()
    return api_ok({"user": public_user(user), "auth_token": make_auth_token(user) if user else ""})


@app.patch("/api/auth/me")
def api_update_me():
    user = require_user()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = normalize_email(data.get("email") or user.email)
    phone = (data.get("phone") or "").strip()
    company_name = (data.get("company_name") or "").strip()
    gstin = (data.get("gstin") or "").strip()

    if not name or not email:
        return api_error("Name and email are required.")

    db = DBSession()
    try:
        row = db.query(UserModel).filter_by(id=user.id).first()
        if not row:
            return api_error("User not found.", 404)
        existing_email = db.query(UserModel).filter(UserModel.email == email, UserModel.id != row.id).first()
        if existing_email:
            return api_error("This email already has an account.")
        if phone:
            existing_phone = db.query(UserModel).filter(UserModel.phone == phone, UserModel.id != row.id).first()
            if existing_phone:
                return api_error("This phone number is already registered.")
        row.name = name
        row.email = email
        row.phone = phone or None
        if (row.account_type or "B2C") == "B2B":
            row.company_name = company_name
            row.gstin = gstin
        row.updated_at = now_utc()
        db.commit()
        db.refresh(row)
        return api_ok({"user": public_user(row)})
    finally:
        db.close()


@app.post("/api/auth/change-password")
def api_change_password():
    user = require_user()
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    confirm_password = data.get("confirm_password") or ""

    if not current_password:
        return api_error("Current password is required.")
    if len(new_password) < 6:
        return api_error("Password must be at least 6 characters.")
    if new_password != confirm_password:
        return api_error("New passwords do not match.")

    local_password_ok = bool(user.password_hash and check_password_hash(user.password_hash, current_password))
    supabase_password_ok = False
    supabase_session = None
    supabase_error = None
    if supabase:
        supabase_user, supabase_session, supabase_error = supabase_verify_password(user.email, current_password)
        supabase_password_ok = bool(supabase_user)

    if not local_password_ok and not supabase_password_ok:
        return api_error("Current password is incorrect.", 401)

    if supabase_password_ok:
        try:
            supabase_update_password_for_session(supabase_session, new_password)
        except Exception as exc:
            return api_error(f"Failed to change password: {str(exc)}", 400)
    elif user.password_hash and supabase_error:
        print(f"Skipping Supabase password update for local password user {mask_email_for_log(user.email)}: {supabase_error}")

    db = DBSession()
    try:
        row = db.query(UserModel).filter_by(id=user.id).first()
        if row:
            row.password_hash = generate_password_hash(new_password)
            row.updated_at = now_utc()
            db.commit()
            session_login_for(row)
            user = row
    finally:
        db.close()

    return api_ok({"message": "Password changed.", "auth_token": make_auth_token(user)})


@app.delete("/api/auth/me")
def api_delete_me():
    user = require_user()
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    confirm = (data.get("confirm") or "").strip()

    if confirm != "DELETE":
        return api_error("Type DELETE to confirm account deletion.")

    if user.password_hash:
        if not check_password_hash(user.password_hash, password):
            return api_error("Password is incorrect.", 401)
    else:
        if not supabase:
            return api_error("missing Supabase env vars", 500)
        try:
            supabase.auth.sign_in_with_password({"email": user.email, "password": password})
        except Exception:
            return api_error("Password is incorrect.", 401)

    db = DBSession()
    try:
        row = db.query(UserModel).filter_by(id=user.id).first()
        if row:
            db.delete(row)
            db.commit()

        if not user.password_hash and supabase:
            if not supabase_delete_auth_user(user.id):
                print(f"Failed to delete user {user.id} from Supabase Auth")

        session.pop("user_id", None)
        return api_ok({"message": "Account deleted."})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Products (public)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/products")
def api_products():
    db = DBSession()
    try:
        all_p  = db.query(ProductModel).filter_by(is_active=True).all()
        real   = [p for p in all_p if not p.is_sample]
        visible = real if real else [p for p in all_p if p.is_sample]
        visible.sort(key=lambda p: p.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return api_ok({"products": [product_to_dict(p) for p in visible]})
    finally:
        db.close()


@app.get("/api/products/<product_id>")
def api_product(product_id):
    user = current_user()
    db = DBSession()
    try:
        product = db.query(ProductModel).filter_by(id=product_id, is_active=True).first()
        if not product:
            return api_error("Product not found.", 404)
        # Track view
        product.views = (product.views or 0) + 1
        db.add(EventModel(type="view", product_id=product.id,
                          user_id=user.id if user else None))
        db.commit()
        reviews = (db.query(ReviewModel)
                     .filter_by(product_id=product.id)
                     .order_by(ReviewModel.created_at.desc())
                     .limit(20).all())
        return api_ok({
            "product": product_to_dict(product),
            "reviews": [review_to_dict(r) for r in reviews],
        })
    finally:
        db.close()


@app.post("/api/products/<product_id>/reviews")
def api_review(product_id):
    user = require_user()
    db   = DBSession()
    try:
        product = db.query(ProductModel).filter_by(id=product_id).first()
        if not product:
            return api_error("Product not found.", 404)
        data    = request.get_json(silent=True) or {}
        rating  = int(data.get("rating") or 0)
        comment = (data.get("comment") or "").strip()
        if rating < 1 or rating > 5:
            return api_error("Rating must be between 1 and 5.")
        review = ReviewModel(
            product_id = product.id,
            user_id    = user.id,
            user_name  = user.name or user.email,
            rating     = rating,
            comment    = comment,
        )
        db.add(review)
        product.rating_sum   = (product.rating_sum   or 0) + rating
        product.rating_count = (product.rating_count or 0) + 1
        product.review_count = (product.review_count or 0) + 1
        product.updated_at   = now_utc()
        db.commit()
        db.refresh(review)
        db.refresh(product)
        return api_ok({"review": review_to_dict(review), "product": product_to_dict(product)}, 201)
    finally:
        db.close()


# ── Community Discussion Board APIs ──────────────────────────────────────────

@app.get("/api/community/posts")
def api_get_community_posts():
    db = DBSession()
    try:
        posts = db.query(CommunityPostModel).order_by(CommunityPostModel.created_at.desc()).all()
        return api_ok({"posts": [post_to_dict(p, db) for p in posts]})
    finally:
        db.close()

@app.post("/api/community/posts")
def api_create_community_post():
    data    = request.get_json(silent=True) or {}
    title   = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    category = (data.get("category") or "Need Eyes").strip()
    if not title or not content:
        return api_error("Title and content are required.")
    
    user = current_user()
    db   = DBSession()
    try:
        user_id = user.id if user else None
        user_name = user.name or user.email if user else (data.get("name") or "Anonymous").strip()
        
        post = CommunityPostModel(
            user_id    = user_id,
            user_name  = user_name,
            title      = title,
            content    = content,
            category   = category,
            likes      = 0,
            liked_by   = []
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        return api_ok({"post": post_to_dict(post, db)}, 201)
    finally:
        db.close()

@app.post("/api/community/posts/<post_id>/like")
def api_like_community_post(post_id):
    user = current_user()
    db   = DBSession()
    try:
        post = db.query(CommunityPostModel).filter_by(id=post_id).first()
        if not post:
            return api_error("Post not found.", 404)
        
        liked_by = list(post.liked_by or [])
        user_identifier = str_id(user.id) if user else client_ip()
        
        if user_identifier in liked_by:
            liked_by.remove(user_identifier)
            post.likes = max(0, (post.likes or 0) - 1)
        else:
            liked_by.append(user_identifier)
            post.likes = (post.likes or 0) + 1
            
        post.liked_by = liked_by
        db.commit()
        db.refresh(post)
        return api_ok({"post": post_to_dict(post, db)})
    finally:
        db.close()

@app.delete("/api/community/posts/<post_id>")
def api_delete_community_post(post_id):
    db = DBSession()
    try:
        post = db.query(CommunityPostModel).filter_by(id=post_id).first()
        if not post:
            return api_error("Post not found.", 404)
        if not can_delete_community_item(post):
            return api_error("Only the author or an admin can delete this post.", 403)

        replies = db.query(CommunityReplyModel).filter_by(post_id=post.id).all()
        for reply in replies:
            db.delete(reply)
        db.delete(post)
        db.commit()
        return api_ok({"message": "Post deleted."})
    finally:
        db.close()

@app.get("/api/community/posts/<post_id>/replies")
def api_get_community_replies(post_id):
    db = DBSession()
    try:
        replies = (db.query(CommunityReplyModel)
                     .filter_by(post_id=post_id)
                     .order_by(CommunityReplyModel.created_at.asc())
                     .all())
        return api_ok({"replies": [reply_to_dict(r) for r in replies]})
    finally:
        db.close()

@app.post("/api/community/posts/<post_id>/replies")
def api_create_community_reply(post_id):
    data    = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return api_error("Reply content is required.")
        
    user = current_user()
    db   = DBSession()
    try:
        post = db.query(CommunityPostModel).filter_by(id=post_id).first()
        if not post:
            return api_error("Post not found.", 404)
            
        user_id = user.id if user else None
        user_name = user.name or user.email if user else (data.get("name") or "Anonymous").strip()
        
        reply = CommunityReplyModel(
            post_id   = post.id,
            user_id   = user_id,
            user_name = user_name,
            content   = content
        )
        db.add(reply)
        db.commit()
        db.refresh(reply)
        return api_ok({"reply": reply_to_dict(reply)}, 201)
    finally:
        db.close()

@app.delete("/api/community/replies/<reply_id>")
def api_delete_community_reply(reply_id):
    db = DBSession()
    try:
        reply = db.query(CommunityReplyModel).filter_by(id=reply_id).first()
        if not reply:
            return api_error("Reply not found.", 404)
        if not can_delete_community_item(reply):
            return api_error("Only the author or an admin can delete this reply.", 403)

        post_id = str_id(reply.post_id)
        db.delete(reply)
        db.commit()
        return api_ok({"message": "Reply deleted.", "post_id": post_id})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Events
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/events")
def api_event():
    data       = request.get_json(silent=True) or {}
    event_type = data.get("type")
    if event_type not in {"view", "cart_add", "checkout_open", "payment_selected"}:
        return api_error("Unsupported event type.")
    user = current_user()
    db = DBSession()
    try:
        product_id = data.get("product_id")
        event = EventModel(
            type       = event_type,
            product_id = product_id,
            user_id    = user.id if user else None,
            event_metadata = data.get("metadata") or {},
        )
        db.add(event)
        if product_id and event_type == "cart_add":
            p = db.query(ProductModel).filter_by(id=product_id).first()
            if p:
                p.cart_adds  = (p.cart_adds or 0) + 1
                p.updated_at = now_utc()
        db.commit()
        return api_ok({"event": {"id": str_id(event.id), "type": event_type}}, 201)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Orders (user)
# ══════════════════════════════════════════════════════════════════════════════

def checkout_lookup(value):
    return str(value or "").strip().lower()

def resolve_checkout_product(db, entry):
    pid = str(entry.get("product_id") or entry.get("id") or "").strip()
    if pid:
        try:
            product = db.query(ProductModel).filter_by(id=pid, is_active=True).first()
            if product:
                return product
        except (ValueError, SQLAlchemyError) as exc:
            db.rollback()
            print(f"Checkout product id lookup failed for {pid}: {exc}")

    sku = checkout_lookup(entry.get("sku"))
    slug = checkout_lookup(entry.get("slug"))
    name = checkout_lookup(entry.get("name"))
    if not any([sku, slug, name]):
        return None

    active_products = db.query(ProductModel).filter_by(is_active=True).all()
    for product in active_products:
        if sku and checkout_lookup(product.sku) == sku:
            return product
    for product in active_products:
        if slug and checkout_lookup(product.slug) == slug:
            return product
    for product in active_products:
        if name and checkout_lookup(product.name) == name:
            return product
    return None

@app.post("/api/orders")
def api_create_order():
    data = request.get_json(silent=True) or {}
    user = require_checkout_user(data)
    raw_items = data.get("items") or []
    if not raw_items:
        return api_error("Cart is empty.")

    db = DBSession()
    try:
        items = []
        for entry in raw_items:
            quantity = max(1, int(entry.get("quantity") or 1))
            product  = resolve_checkout_product(db, entry)
            if not product:
                return api_error("One product in your cart is not available.")
            if quantity > (product.stock or 0):
                return api_error(f"{product.name} has only {product.stock} units available.")
            items.append({
                "product_id": str_id(product.id),
                "name":       product.name,
                "sku":        product.sku or "",
                "image_url":  product.image_url or "",
                "unit_price": money(product.price),
                "quantity":   quantity,
                "line_total": money(money(product.price) * quantity),
            })

        totals  = order_totals(items)
        address = data.get("address") or {}
        customer_name  = (address.get("name") or user.name or "").strip()
        customer_email = normalize_email(address.get("email") or user.email)
        if not customer_name or not customer_email:
            return api_error("Customer name and email are required.")

        order = OrderModel(
            invoice_number = make_invoice_number(),
            user_id        = user.id,
            customer       = {
                "name":    customer_name,
                "email":   customer_email,
                "phone":   address.get("phone") or user.phone or "",
                "line1":   address.get("line1", ""),
                "city":    address.get("city", ""),
                "state":   address.get("state", ""),
                "pincode": address.get("pincode", ""),
            },
            items          = items,
            totals         = totals,
            payment_method = data.get("payment_method") or "COD",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        order_dict = order_to_dict(order)
        email_sent = send_order_email(order_dict)
        return api_ok({"order": order_dict, "email_sent": email_sent}, 201)
    finally:
        db.close()


@app.get("/api/orders/my")
def api_my_orders():
    user = require_user()
    db   = DBSession()
    try:
        orders = (db.query(OrderModel)
                    .filter_by(user_id=user.id)
                    .order_by(OrderModel.created_at.desc())
                    .all())
        return api_ok({"orders": [order_to_dict(o) for o in orders]})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Admin
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/admin/login")
def api_admin_login():
    data     = request.get_json(silent=True) or {}
    email    = normalize_email(data.get("email"))
    password = data.get("password") or ""
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        session["admin_role"] = "owner_admin"
        return api_ok()
    return api_error("Invalid admin credentials.", 401)


@app.post("/api/admin/logout")
def api_admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_role", None)
    session.pop("owner_logged_in", None)
    return api_ok()

@app.post("/api/owner/login")
def api_owner_login():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email"))
    password = data.get("password") or ""
    if email == OWNER_EMAIL and password == OWNER_PASSWORD:
        session["owner_logged_in"] = True
        session["owner_auth_version"] = owner_auth_version()
        session["admin_logged_in"] = True
        session["admin_role"] = "owner_admin"
        return api_ok({"redirect_url": url_for("owner_page")})
    return api_error("Invalid owner credentials.", 401)

@app.post("/api/owner/logout")
def api_owner_logout():
    clear_owner_session()
    return api_ok()

@app.get("/api/owner/overview")
def api_owner_overview():
    require_owner()
    return api_ok(owner_overview_payload())


@app.get("/api/admin/summary")
def api_admin_summary():
    require_admin()
    db = DBSession()
    try:
        users_count    = db.query(UserModel).count()
        real_products  = db.query(ProductModel).filter_by(is_sample=False).count()
        total_orders   = db.query(OrderModel).count()
        pending_orders = db.query(OrderModel).filter_by(status="Pending").count()
        pending_businesses = db.query(BusinessProfileModel).filter_by(approval_status="Pending").count()
        approved       = db.query(OrderModel).filter_by(status="Approved").all()
        revenue        = sum(float((o.totals or {}).get("total") or 0) for o in approved)
        smtp_ok, smtp_missing = smtp_config_status()
        return api_ok({
            "cards": {
                "users":            users_count,
                "products":         real_products,
                "orders":           total_orders,
                "pending_orders":   pending_orders,
                "pending_approvals": pending_orders + pending_businesses,
                "approved_revenue": money(revenue),
            },
            "store_mode":     DATABASE_LABEL,
            "smtp_configured": smtp_ok,
            "smtp_missing":    smtp_missing,
        })
    finally:
        db.close()


@app.get("/api/admin/products")
def api_admin_products():
    require_admin()
    db = DBSession()
    try:
        products = db.query(ProductModel).filter_by(is_sample=False).order_by(ProductModel.created_at.desc()).all()
        return api_ok({
            "products":   [product_to_dict(p) for p in products],
            "next_image": next_product_image_path(),
        })
    finally:
        db.close()

@app.get("/api/admin/products/lookup")
def api_admin_lookup_product():
    require_admin()
    code = (request.args.get("code") or "").strip()
    if not code:
        return api_error("Enter a barcode or SKU to scan.")
    db = DBSession()
    try:
        product = (db.query(ProductModel)
                     .filter(ProductModel.is_sample == False)
                     .filter((ProductModel.sku == code) | (ProductModel.model == code))
                     .first())
        if not product:
            return api_ok({"found": False, "code": code})
        return api_ok({"found": True, "product": product_to_dict(product)})
    finally:
        db.close()


@app.post("/api/admin/products")
def api_admin_create_product():
    require_admin()
    form = request.form if request.form else (request.get_json(silent=True) or {})
    name        = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    if not name or not description:
        return api_error("Product name and description are required.")
    try:
        price = money(form.get("price"))
        stock = int(form.get("stock") or 0)
    except Exception:
        return api_error("Valid price and stock are required.")

    image_url  = (form.get("image_url") or "").strip()
    image_file = request.files.get("image")
    try:
        uploaded_url = save_product_image(image_file)
        if uploaded_url:
            image_url = uploaded_url
    except ValueError as exc:
        return api_error(str(exc))
    if not image_url and form.get("use_suggested_image") == "true":
        image_url = next_product_image_path()["web_path"]
    if not image_url:
        image_url = "/static/images/product-placeholder.webp"

    db = DBSession()
    try:
        product = ProductModel(
            name          = name,
            slug          = slugify(name),
            description   = description,
            category      = (form.get("category") or "Microchip").strip(),
            brand         = (form.get("brand") or "").strip(),
            model         = (form.get("model") or "").strip(),
            sku           = (form.get("sku") or "").strip() or f"MC-{secrets.token_hex(3).upper()}",
            price         = price,
            stock         = stock,
            image_url     = image_url,
            specs         = parse_specs(form.get("specs")),
            datasheet_url = (form.get("datasheet_url") or "").strip(),
            warranty      = (form.get("warranty") or "7 days replacement").strip(),
            lead_time     = (form.get("lead_time") or "Ready to dispatch").strip(),
            is_active     = str(form.get("active", "true")).lower() != "false",
            is_sample     = False,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return api_ok({"product": product_to_dict(product), "next_image": next_product_image_path()}, 201)
    finally:
        db.close()


@app.patch("/api/admin/products/<product_id>")
def api_admin_update_product(product_id):
    require_admin()
    db = DBSession()
    try:
        product = db.query(ProductModel).filter_by(id=product_id).first()
        if not product:
            return api_error("Product not found.", 404)
        data = request.get_json(silent=True) or {}
        for field in ("name", "description", "category", "brand", "model", "sku",
                      "datasheet_url", "warranty", "lead_time", "image_url"):
            if field in data:
                setattr(product, field, data[field])
        if "price"  in data: product.price    = money(data["price"])
        if "stock"  in data: product.stock    = int(data["stock"] or 0)
        if "active" in data: product.is_active = bool(data["active"])
        if "specs"  in data: product.specs    = parse_specs(data["specs"])
        product.updated_at = now_utc()
        db.commit()
        db.refresh(product)
        return api_ok({"product": product_to_dict(product)})
    finally:
        db.close()


@app.delete("/api/admin/products/<product_id>")
def api_admin_delete_product(product_id):
    require_admin()
    db = DBSession()
    try:
        product = db.query(ProductModel).filter_by(id=product_id).first()
        if not product:
            return api_error("Product not found.", 404)
        if product.is_sample:
            return api_error("Sample products are hidden automatically. They are not deleted.")
        db.delete(product)
        db.commit()
        return api_ok()
    finally:
        db.close()


@app.get("/api/admin/next-image-path")
def api_admin_next_image_path():
    require_admin()
    return api_ok({"next_image": next_product_image_path()})


@app.get("/api/admin/users")
def api_admin_users():
    require_admin()
    db = DBSession()
    try:
        users = db.query(UserModel).order_by(UserModel.created_at.desc()).all()
        return api_ok({"users": [user_to_dict(u) for u in users]})
    finally:
        db.close()


@app.get("/api/admin/businesses")
def api_admin_businesses():
    require_admin()
    db = DBSession()
    try:
        profiles = db.query(BusinessProfileModel).all()
        # We also need the user email and name, let's join or just fetch users
        users = db.query(UserModel).filter(UserModel.account_type == "B2B").all()
        user_map = {u.id: u for u in users}
        
        results = []
        for p in profiles:
            u = user_map.get(p.id)
            results.append({
                "id": str_id(p.id),
                "name": u.name if u else "",
                "email": u.email if u else "",
                "company_name": p.business_name,
                "address": p.business_address,
                "phone": p.contact_number,
                "gstin": p.gst_number,
                "status": p.approval_status
            })
        return api_ok({"businesses": results})
    finally:
        db.close()


@app.patch("/api/admin/businesses/<business_id>")
def api_admin_update_business(business_id):
    require_admin()
    db = DBSession()
    try:
        business = db.query(BusinessProfileModel).filter_by(id=business_id).first()
        user = db.query(UserModel).filter_by(id=business_id).first()
        if not business and not user:
            return api_error("Business not found.", 404)
        
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        if status in {"Pending", "Approved", "Rejected"}:
            if business:
                business.approval_status = status
            db.commit()
            
            if user:
                user.status = "Active" if status == "Approved" else status
                db.commit()
                
            return api_ok({"message": f"Business {status.lower()}"})
        return api_error("Invalid status")
    finally:
        db.close()


@app.get("/api/admin/orders")
def api_admin_orders():
    require_admin()
    db = DBSession()
    try:
        orders = db.query(OrderModel).order_by(OrderModel.created_at.desc()).all()
        return api_ok({"orders": [order_to_dict(o) for o in orders]})
    finally:
        db.close()


@app.patch("/api/admin/orders/<order_id>")
def api_admin_update_order(order_id):
    require_admin()
    db = DBSession()
    try:
        order = db.query(OrderModel).filter_by(id=order_id).first()
        if not order:
            return api_error("Order not found.", 404)
        data   = request.get_json(silent=True) or {}
        status = data.get("status")
        if status not in {"Pending", "Approved", "Rejected"}:
            return api_error("Status must be Pending, Approved, or Rejected.")
        old_status        = order.status
        order.status      = status
        order.admin_notes = (data.get("admin_notes") or order.admin_notes or "").strip()
        order.updated_at  = now_utc()
        if status in {"Approved", "Rejected"}:
            order.reviewed_at = now_utc()
        # Deduct stock when approving
        if status == "Approved" and old_status != "Approved":
            for item in (order.items or []):
                p = db.query(ProductModel).filter_by(id=item.get("product_id")).first()
                if p:
                    p.stock      = max(0, (p.stock or 0) - int(item.get("quantity") or 0))
                    p.updated_at = now_utc()
        db.commit()
        db.refresh(order)
        return api_ok({"order": order_to_dict(order)})
    finally:
        db.close()


@app.get("/api/admin/analytics")
def api_admin_analytics():
    require_admin()
    return api_ok({"analytics": analytics_payload()})


@app.get("/api/admin/settings")
def api_admin_settings():
    require_admin()
    db = DBSession()
    try:
        row = db.query(SettingsModel).filter_by(key="store").first()
        return api_ok({"settings": row.value if row else {}})
    finally:
        db.close()


@app.put("/api/admin/settings")
def api_admin_update_settings():
    require_admin()
    data = request.get_json(silent=True) or {}
    db   = DBSession()
    try:
        row     = db.query(SettingsModel).filter_by(key="store").first()
        current = row.value if row else {}
        section_fields = {
            "store_profile": ("tagline", "marketplace_description", "default_currency"),
            "business_details": ("legal_name", "gstin", "business_address", "business_phone"),
            "payout_info": ("payout_method", "account_label", "settlement_cycle"),
            "shipping_preferences": ("dispatch_window", "shipping_regions", "default_carrier"),
            "approval_preferences": ("auto_submit_products", "require_owner_review", "allow_backorders"),
            "notification_preferences": ("order_email", "stock_alerts", "community_replies"),
            "marketplace_visibility": ("public_profile", "show_stock_count", "accept_bulk_requests"),
            "support_contact": ("support_name", "support_phone", "support_hours"),
        }
        section_updates = {}
        for section, fields in section_fields.items():
            existing = current.get(section) if isinstance(current.get(section), dict) else {}
            section_updates[section] = {**existing}
            for field in fields:
                key = f"{section}.{field}"
                if key in data:
                    section_updates[section][field] = str(data.get(key) or "").strip()
        updated = {
            **current,
            "store_name":   (data.get("store_name") or current.get("store_name") or "Microchip Cart").strip(),
            "support_email": normalize_email(data.get("support_email") or current.get("support_email") or ADMIN_NOTIFICATION_EMAIL),
            "announcement": (data.get("announcement") or current.get("announcement") or "").strip(),
            **section_updates,
            "currency":     "INR",
            "updated_at":   now_iso(),
        }
        if row:
            row.value = updated
        else:
            db.add(SettingsModel(key="store", value=updated))
        db.commit()
        return api_ok({"settings": updated})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Error handlers
# ══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return api_error("Not found.", 404)
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
