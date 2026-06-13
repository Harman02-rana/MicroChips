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
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse, parse_qsl, urlencode

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ── dotenv ────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
except Exception:
    pass

# ── Supabase Client ───────────────────────────────────────────────────────────
try:
    from supabase import ClientOptions, create_client
except Exception as exc:
    ClientOptions = None
    create_client = None
    print(f"Supabase package unavailable: {exc}")

try:
    import httpx
except Exception:
    httpx = None

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
supabase_admin = None
supabase_oauth = None
def supabase_client_options(flow_type=None):
    if not ClientOptions:
        return None
    timeout = float(os.getenv("SUPABASE_HTTP_TIMEOUT_SECONDS", "8"))
    options = {
        "postgrest_client_timeout": timeout,
        "storage_client_timeout": int(timeout),
        "function_client_timeout": int(timeout),
    }
    if flow_type:
        options["flow_type"] = flow_type
    if httpx:
        options["httpx_client"] = httpx.Client(timeout=timeout)
    return ClientOptions(**options)

if create_client and supabase_url not in SUPABASE_PLACEHOLDERS and supabase_key not in SUPABASE_PLACEHOLDERS:
    try:
        supabase = create_client(supabase_url, supabase_key, options=supabase_client_options())
        print("Supabase auth connected")
    except Exception as e:
        print("Supabase auth disabled:", e)
        supabase = None
# ── SQLAlchemy / PostgreSQL ───────────────────────────────────────────────────
from sqlalchemy import (
    create_engine, text,
    Column, String, Boolean, Numeric, Integer, Text, DateTime, JSON, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.pool import NullPool
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
    supabase_host = clean_env(os.getenv("SUPABASE_DB_HOST")) or "aws-1-ap-south-1.pooler.supabase.com"
    supabase_user = clean_env(os.getenv("SUPABASE_DB_USER")) or "postgres.ybbomppuyrucifdwgmpf"
    supabase_name = clean_env(os.getenv("SUPABASE_DB_NAME")) or "postgres"
    supabase_port = clean_env(os.getenv("SUPABASE_DB_PORT")) or "6543"

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
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )


engine = create_app_engine(DATABASE_URL)
DBSession = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


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
    auth_user_id   = Column(GUID(), nullable=True)
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
    profile_completed = Column(Boolean, default=False, nullable=True)
    last_login     = Column(DateTime(timezone=True), nullable=True)
    reset_password_hash       = Column(Text, nullable=True)
    reset_password_expires_at = Column(DateTime(timezone=True), nullable=True)
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
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_user_id UUID",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_type VARCHAR(10) DEFAULT 'B2C'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gstin VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT false",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'Active'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_password_hash TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_password_expires_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(30) DEFAULT 'customer'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_completed BOOLEAN DEFAULT false",
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
        "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id)",
        "CREATE INDEX IF NOT EXISTS idx_community_replies_post_id ON community_replies(post_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_product_id ON events(product_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_products_is_sample ON products(is_sample)",
        "CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_business_profiles_approval_status ON business_profiles(approval_status)",
    ]
    with engine.begin() as connection:
        for statement in ddl_statements:
            connection.execute(text(statement))


def ensure_sqlite_schema():
    if engine.dialect.name != "sqlite":
        return
    ddl_statements = [
        "ALTER TABLE users ADD COLUMN account_type VARCHAR(10) DEFAULT 'B2C'",
        "ALTER TABLE users ADD COLUMN auth_user_id CHAR(36)",
        "ALTER TABLE users ADD COLUMN password_hash TEXT",
        "ALTER TABLE users ADD COLUMN company_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN gstin VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN role VARCHAR(30) DEFAULT 'customer'",
        "ALTER TABLE users ADD COLUMN full_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN reset_password_hash TEXT",
        "ALTER TABLE users ADD COLUMN reset_password_expires_at DATETIME",
        "ALTER TABLE users ADD COLUMN profile_completed BOOLEAN DEFAULT 0",
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
                    profile_completed BOOLEAN DEFAULT 0,
                    last_login DATETIME,
                    reset_password_hash TEXT,
                    reset_password_expires_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            old_column_names = {column["name"] for column in user_columns}
            target_columns = [
                "id", "email", "phone", "password_hash", "name", "full_name",
                "account_type", "role", "company_name", "gstin", "is_admin",
                "email_verified", "phone_verified", "status", "profile_completed", "last_login",
                "reset_password_hash", "reset_password_expires_at",
                "created_at", "updated_at",
            ]
            copy_columns = [column for column in target_columns if column in old_column_names]
            connection.execute(text(
                f"INSERT INTO users_schema_fix ({', '.join(copy_columns)}) "
                f"SELECT {', '.join(copy_columns)} FROM users"
            ))
            connection.execute(text("DROP TABLE users"))
            connection.execute(text("ALTER TABLE users_schema_fix RENAME TO users"))

    # Create SQLite indexes
    sqlite_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id)",
        "CREATE INDEX IF NOT EXISTS idx_community_replies_post_id ON community_replies(post_id)",
        "CREATE INDEX IF NOT EXISTS idx_products_is_sample ON products(is_sample)",
        "CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active)",
    ]
    with engine.begin() as connection:
        for stmt in sqlite_indexes:
            try:
                connection.execute(text(stmt))
            except Exception:
                pass


def initialize_database():
    global engine, DBSession, DATABASE_LABEL

    try:
        Base.metadata.create_all(engine)
        ensure_compatible_schema()
        ensure_sqlite_schema()
        
        # Mark database as initialized
        db = DBSession()
        try:
            row = db.query(SettingsModel).filter_by(key="schema_version").first()
            if not row:
                db.add(SettingsModel(key="schema_version", value=2))
            else:
                row.value = 2
            db.commit()
        except Exception as e:
            db.rollback()
            print("Failed to save schema version to database:", e)
        finally:
            db.close()
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
TEMP_COMPANY_EMAIL       = (os.getenv("TEMP_COMPANY_EMAIL") or "microchipcaty025@gmail.com").strip().lower()
TEMP_COMPANY_PASSWORD    = os.getenv("TEMP_COMPANY_PASSWORD") or "MicrochipOwner@2026"
SMTP_PLACEHOLDERS        = {
    "",
    "yourgmail@gmail.com",
    "your-email@gmail.com",
    "noreply@yourdomain.com",
    "your-16-character-gmail-app-password",
}
PRIVATE_SMTP_SENDERS     = {
    email.strip().lower()
    for email in (os.getenv("PRIVATE_SMTP_SENDERS") or "harmanrana709@gmail.com").split(",")
    if email.strip()
}
COMPANY_EMAIL_SENDER     = (os.getenv("COMPANY_EMAIL_SENDER") or ADMIN_NOTIFICATION_EMAIL or "mcc_noreply@microchipcart.com").strip().lower()


# ── Utility helpers ───────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)

def as_utc(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

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

def env_flag(name, default=False):
    raw = clean_env(os.getenv(name))
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}

SUPABASE_AUTH_LOGIN_FALLBACK = env_flag("SUPABASE_AUTH_LOGIN_FALLBACK", False)
SUPABASE_AUTH_SYNC_ON_SIGNUP = env_flag("SUPABASE_AUTH_SYNC_ON_SIGNUP", False)
SUPABASE_EMAIL_OTP_ENABLED = env_flag("SUPABASE_EMAIL_OTP_ENABLED", True)

def supabase_admin_client():
    global supabase_admin
    if supabase_admin:
        return supabase_admin
    if not create_client:
        return None
    service_role_key = clean_env(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    if supabase_url in SUPABASE_PLACEHOLDERS or service_role_key in SUPABASE_PLACEHOLDERS:
        return None
    try:
        supabase_admin = create_client(supabase_url, service_role_key, options=supabase_client_options())
        return supabase_admin
    except Exception as exc:
        print(f"Supabase admin client unavailable: {exc}")
        return None

def supabase_oauth_client():
    global supabase_oauth
    if supabase_oauth:
        return supabase_oauth
    if not create_client or supabase_url in SUPABASE_PLACEHOLDERS or supabase_key in SUPABASE_PLACEHOLDERS:
        return None
    try:
        supabase_oauth = create_client(supabase_url, supabase_key, options=supabase_client_options("implicit"))
        return supabase_oauth
    except Exception as exc:
        print(f"Supabase OAuth client unavailable: {exc}")
        return None

def public_base_url():
    configured = clean_env(os.getenv("PUBLIC_BASE_URL"))
    if configured:
        return configured.rstrip("/")
    return request.host_url.rstrip("/")

def google_oauth_callback_url():
    return f"{public_base_url()}/auth/google/callback"

def oauth_response_url(response):
    if isinstance(response, dict):
        return response.get("url") or response.get("data", {}).get("url")
    return getattr(response, "url", None)

def auth_response_session_user(response):
    auth_session = getattr(response, "session", None)
    auth_user = getattr(response, "user", None)
    data = getattr(response, "data", None)
    if data:
        auth_session = auth_session or getattr(data, "session", None)
        auth_user = auth_user or getattr(data, "user", None)
    if isinstance(response, dict):
        auth_session = response.get("session") or response.get("data", {}).get("session")
        auth_user = response.get("user") or response.get("data", {}).get("user")
    if auth_session and not auth_user:
        auth_user = getattr(auth_session, "user", None)
        if isinstance(auth_session, dict):
            auth_user = auth_session.get("user")
    return auth_session, auth_user

def oauth_user_profile(auth_user):
    email = auth_user_email(auth_user)
    metadata = supabase_user_metadata(auth_user)
    full_name = (
        metadata.get("full_name")
        or metadata.get("name")
        or metadata.get("display_name")
        or (email.split("@", 1)[0] if email else "Google user")
    )
    return email, str(full_name).strip()

def create_or_update_oauth_user(db, auth_user, account_type="B2C"):
    auth_id = auth_user_id(auth_user)
    email, full_name = oauth_user_profile(auth_user)
    if not auth_id or not email:
        return None, "Google did not return a verified email. Please use email signup."

    account_type = normalize_account_type(account_type)
    role = "business" if account_type == "B2B" else "customer"
    user = db.query(UserModel).filter_by(auth_user_id=auth_id).first()
    if not user:
        user = db.query(UserModel).filter_by(id=auth_id).first()
    if not user:
        user = db.query(UserModel).filter_by(email=email).first()
        if user:
            user.auth_user_id = auth_id
            db.flush()

    if not user:
        user = UserModel(
            id=auth_id,
            auth_user_id=auth_id,
            email=email,
            name=full_name,
            full_name=full_name,
            account_type=account_type,
            role=role,
            is_admin=False,
            email_verified=True,
            status="Active",
            created_at=as_utc(getattr(auth_user, "created_at", None)) or now_utc(),
        )
        db.add(user)
        db.flush()
    else:
        user.auth_user_id = auth_id
        user.email = user.email or email
        if not user.name:
            user.name = full_name
        if not user.full_name:
            user.full_name = full_name
        if not user.account_type:
            user.account_type = account_type
        if not user.role:
            user.role = role
        user.email_verified = True
        user.status = user.status or "Active"
        user.updated_at = now_utc()

    user.last_login = now_utc()
    return user, None

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

def supabase_find_auth_user_by_id(user_id):
    user_id = str_id(user_id)
    if not user_id:
        return None
    admin_client = supabase_admin_client()
    if not admin_client:
        return None
    try:
        response = admin_client.auth.admin.get_user_by_id(user_id)
        return supabase_response_user(response)
    except Exception as exc:
        print(f"Could not load Supabase Auth user by id: {exc}")
        return None

def linked_auth_user_id(user):
    return str_id(getattr(user, "auth_user_id", None) or getattr(user, "id", None))

def supabase_verify_password_for_user(user, password):
    if not supabase or not user:
        return None, None, RuntimeError("missing Supabase env vars")

    emails_to_try = []
    primary_email = normalize_email(getattr(user, "email", ""))
    if primary_email:
        emails_to_try.append(primary_email)

    auth_user = supabase_find_auth_user_by_id(getattr(user, "auth_user_id", None))
    auth_email = auth_user_email(auth_user)
    if auth_email and auth_email not in emails_to_try:
        emails_to_try.append(auth_email)

    email_auth_user = None
    if primary_email:
        email_auth_user = supabase_find_auth_user_by_email(primary_email)
        email_auth_id = str_id(auth_user_id(email_auth_user))
        if email_auth_id and str_id(getattr(user, "auth_user_id", None)) != email_auth_id:
            user.auth_user_id = email_auth_id
        email_auth_email = auth_user_email(email_auth_user)
        if email_auth_email and email_auth_email not in emails_to_try:
            emails_to_try.append(email_auth_email)

    last_error = None
    for email in emails_to_try:
        supabase_user, supabase_session, error = supabase_verify_password(email, password)
        if supabase_user:
            if str_id(getattr(user, "auth_user_id", None)) != str_id(auth_user_id(supabase_user)):
                user.auth_user_id = auth_user_id(supabase_user)
            return supabase_user, supabase_session, None
        last_error = error

    return None, None, last_error

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

def send_supabase_email_otp(email):
    if not supabase:
        return False, "missing Supabase env vars"
    try:
        supabase.auth.sign_in_with_otp({
            "email": normalize_email(email),
            "options": {"should_create_user": True},
        })
        return True, None
    except Exception as exc:
        print(f"SUPABASE OTP SEND FAILURE: {exc}")
        return False, str(exc)

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

def mail_env(*names, default=""):
    for name in names:
        value = clean_env(os.getenv(name))
        if value:
            return value
    return default

def smtp_config():
    host = mail_env("SMTP_HOST", "MAIL_SERVER")
    username = mail_env("SMTP_USERNAME", "MAIL_USERNAME")
    password = mail_env("SMTP_PASSWORD", "MAIL_PASSWORD")
    sender = mail_env("SMTP_FROM", "MAIL_DEFAULT_SENDER", default=COMPANY_EMAIL_SENDER)
    sender_name_from_header, sender_addr_from_header = parseaddr(sender)
    if normalize_email(sender_addr_from_header or sender) in PRIVATE_SMTP_SENDERS:
        sender = formataddr((sender_name_from_header or "MicrochipCart", COMPANY_EMAIL_SENDER))
    sender_name = mail_env("SMTP_FROM_NAME", "MAIL_DEFAULT_SENDER_NAME", default="MicrochipCart")
    port = mail_env("SMTP_PORT", "MAIL_PORT", default="587")
    use_ssl = mail_env("SMTP_SSL", "MAIL_USE_SSL", default="false").lower() == "true"
    use_tls = mail_env("SMTP_TLS", "MAIL_USE_TLS", default="true").lower() == "true"
    timeout = int(mail_env("SMTP_TIMEOUT_SECONDS", default="10"))
    return host, username, password, sender, sender_name, port, use_ssl, use_tls, timeout

def smtp_sender_address():
    _, username_addr = parseaddr(mail_env("SMTP_USERNAME", "MAIL_USERNAME"))
    _, sender_addr = parseaddr(mail_env("SMTP_FROM", "MAIL_DEFAULT_SENDER", default=COMPANY_EMAIL_SENDER))
    if normalize_email(sender_addr) in PRIVATE_SMTP_SENDERS:
        sender_addr = COMPANY_EMAIL_SENDER
    return (sender_addr or username_addr or "").strip().lower()

def smtp_uses_private_sender():
    return smtp_sender_address() in PRIVATE_SMTP_SENDERS

def smtp_config_status():
    host, username, password, sender, *_ = smtp_config()
    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not sender or sender.lower() in SMTP_PLACEHOLDERS:
        missing.append("SMTP_FROM")
    if smtp_uses_private_sender():
        missing.append("company SMTP_FROM")
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
        "profile_completed": bool(getattr(u, "profile_completed", False)),
    }

def public_user(u):
    if u is None:
        return None
    if isinstance(u, dict):
        return {k: u.get(k) for k in ("id", "name", "full_name", "email", "phone", "account_type", "role", "company_name", "gstin", "is_admin", "created_at", "profile_completed", "auth_provider", "approval_status")}
    
    approval_status = "Approved"
    if u.account_type == "B2B":
        db = DBSession()
        try:
            business = db.query(BusinessProfileModel).filter_by(id=u.id).first()
            approval_status = business.approval_status if business else "Pending"
        except Exception:
            approval_status = "Pending"
        finally:
            db.close()

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
        "profile_completed": bool(getattr(u, "profile_completed", False)),
        "auth_provider": "google" if (getattr(u, "auth_user_id", None) and not getattr(u, "password_hash", None)) else "email",
        "approval_status": approval_status,
    }

def auth_redirect_url(user):
    if isinstance(user, dict):
        account_type = user.get("account_type") or "B2C"
        is_admin = user.get("is_admin") or False
        profile_completed = user.get("profile_completed") or False
        approval_status = user.get("approval_status") or "Approved"
    else:
        account_type = getattr(user, "account_type", None) or "B2C"
        is_admin = getattr(user, "is_admin", False) or False
        profile_completed = getattr(user, "profile_completed", False) or False
        
        approval_status = "Approved"
        if account_type == "B2B":
            db = DBSession()
            try:
                business = db.query(BusinessProfileModel).filter_by(id=user.id).first()
                approval_status = business.approval_status if business else "Pending"
            except Exception:
                approval_status = "Pending"
            finally:
                db.close()
                
    if not is_admin and not profile_completed:
        return "/?setup_profile=1"
    if is_admin:
        return "/admin"
    if account_type == "B2B":
        return "/admin"
    return "/"

def product_to_dict(p: ProductModel) -> dict:
    count = p.rating_count or 0
    rating_avg = round((p.rating_sum or 0) / count, 1) if count > 0 else 0
    specs = p.specs or {}
    owner_flags = specs.get("_owner_flags") if isinstance(specs.get("_owner_flags"), dict) else {}
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
        "specs":        specs,
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
        "visible":      p.is_active,
        "featured":     bool(owner_flags.get("featured")),
        "sale_price":   owner_flags.get("sale_price") or "",
        "on_sale":      bool(owner_flags.get("on_sale")),
        "out_of_stock_label": bool(owner_flags.get("out_of_stock_label")),
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

def can_delete_community_item(item, user=None) -> bool:
    if session.get("admin_logged_in"):
        return True
    if user is None:
        user = current_user()
    return bool(user and str_id(getattr(item, "user_id", None)) == str_id(user.id))

def post_to_dict(p: CommunityPostModel, db, user=None, reply_count=None) -> dict:
    if reply_count is None:
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
        "can_delete": can_delete_community_item(p, user),
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }

def reply_to_dict(r: CommunityReplyModel, user=None) -> dict:
    return {
        "id":         str_id(r.id),
        "post_id":    str_id(r.post_id),
        "user_id":    str_id(r.user_id),
        "user_name":  r.user_name or "Anonymous",
        "content":    r.content,
        "can_delete": can_delete_community_item(r, user),
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
            if not user:
                user = db.query(UserModel).filter_by(auth_user_id=user_id).first()
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
        if not user:
            user = db.query(UserModel).filter_by(auth_user_id=user_id).first()
        if user:
            session_login_for(user)
        return user
    finally:
        db.close()

def require_user(auth_token=None):
    user = current_user(auth_token)
    if not user:
        abort(make_response(api_error("Please login first.", 401)[0], 401))
    if (user.status or "Active") in {"Banned", "Suspended", "Rejected"}:
        abort(make_response(api_error(f"Account {(user.status or 'blocked').lower()}. Please contact support.", 403)[0], 403))
    return user

def require_checkout_user(data):
    user = require_user(request_auth_token(data))
    return user

def require_admin():
    if not session.get("admin_logged_in"):
        abort(make_response(api_error("Admin login required.", 401)[0], 401))

def is_company_admin_session():
    return bool(session.get("admin_role") == "owner_admin" or owner_session_is_current())

def require_company_admin():
    require_admin()
    if not is_company_admin_session():
        abort(make_response(api_error("Company admin access required.", 403)[0], 403))

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


DEFAULT_HERO_SLIDES = [
    {
        "id": "slide-esp32", "order": 1, "kicker": "Chip deal zone", "title": "ESP32 IoT module kits",
        "description": "Wireless modules, dev boards, and sensor-ready parts for connected builds.",
        "cta_label": "Shop modules", "cta_link": "/products#wireless",
        "product1_name": "ESP32-WROOM-32E", "product1_price": "INR 489", "product1_badge": "Best seller", "product1_image": "/static/images/samples/sample-1.webp",
        "product2_name": "LoRa SX1278 Module", "product2_price": "Long range", "product2_badge": "New arrival", "product2_image": "/static/images/product-placeholder.webp",
    },
    {
        "id": "slide-mcu", "order": 2, "kicker": "MCU launch picks", "title": "Microcontrollers for labs",
        "description": "STM32, AVR, and embedded control chips for prototypes and small batches.",
        "cta_label": "Explore bulk deals", "cta_link": "/products#bulk",
        "product1_name": "STM32F407VGT6", "product1_price": "INR 1,299", "product1_badge": "Top rated", "product1_image": "/static/images/samples/sample-0.webp",
        "product2_name": "ATmega328P-PU", "product2_price": "INR 265", "product2_badge": "Fast moving", "product2_image": "/static/images/samples/sample-2.webp",
    },
    {
        "id": "slide-prototype", "order": 3, "kicker": "Prototype essentials", "title": "Boards, sensors & power ICs",
        "description": "Build faster with core components, breadboard-ready parts, and bench essentials.",
        "cta_label": "View deals", "cta_link": "/products#deals",
        "product1_name": "Sensor starter kit", "product1_price": "20+ parts", "product1_badge": "Prototype ready", "product1_image": "/static/images/product-placeholder.webp",
        "product2_name": "Power IC pack", "product2_price": "Bulk ready", "product2_badge": "Lab supply", "product2_image": "/static/images/product-placeholder.webp",
    },
]

DEFAULT_TRUST_BADGES = [
    {"id": "stock", "icon": "OK", "label": "Verified stock", "text": "Compare specs, prices, ratings, and stock before checkout."},
    {"id": "checkout", "icon": "PAY", "label": "Fast checkout", "text": "COD, UPI, card options, GST invoices, and order tracking."},
    {"id": "support", "icon": "HELP", "label": "Buyer protection", "text": "Returns, support, and clear order help."},
    {"id": "b2b", "icon": "GST", "label": "B2B ready", "text": "Distributor approvals, GST details, and invoice-friendly orders."},
]

DEFAULT_CATEGORY_CHIPS = [
    {"id": "all", "code": "FY", "label": "For You", "category": "All", "visible": True},
    {"id": "mcu", "code": "MCU", "label": "Microcontrollers", "category": "Microcontroller", "visible": True},
    {"id": "wireless", "code": "RF", "label": "Wireless Modules", "category": "Wireless Module", "visible": True},
    {"id": "sensor", "code": "SNS", "label": "Sensors", "category": "Sensor", "visible": True},
    {"id": "power", "code": "PWR", "label": "Power ICs", "category": "Power IC", "visible": True},
    {"id": "connector", "code": "I/O", "label": "Connectors", "category": "Connector", "visible": True},
    {"id": "dev", "code": "DEV", "label": "Development Boards", "category": "Development Board", "visible": True},
    {"id": "display", "code": "DSP", "label": "Displays", "category": "Display", "visible": True},
    {"id": "tool", "code": "TL", "label": "Tools", "category": "Tool", "visible": True},
    {"id": "robotics", "code": "BOT", "label": "Robotics", "category": "Robotics", "visible": True},
    {"id": "resistor", "code": "R", "label": "Resistors", "category": "Resistor", "visible": True},
    {"id": "capacitor", "code": "C", "label": "Capacitors", "category": "Capacitor", "visible": True},
]

DEFAULT_HERO_METRICS = [
    {"id": "delivery", "strong": "Fast", "text": "delivery"},
    {"id": "trust", "strong": "Trust", "text": ""},
    {"id": "resources", "strong": "Reliable", "text": "resources"},
]

def store_settings(db):
    row = db.query(SettingsModel).filter_by(key="store").first()
    return row.value if row and isinstance(row.value, dict) else {}

def save_store_settings(db, settings):
    row = db.query(SettingsModel).filter_by(key="store").first()
    if row:
        row.value = settings
    else:
        db.add(SettingsModel(key="store", value=settings))
    db.commit()
    return settings

def storefront_controls(settings):
    settings = settings or {}
    return {
        "hero_slides": settings.get("hero_slides") or DEFAULT_HERO_SLIDES,
        "trust_badges": settings.get("trust_badges") or DEFAULT_TRUST_BADGES,
        "category_chips": settings.get("category_chips") or DEFAULT_CATEGORY_CHIPS,
        "hero_metrics": settings.get("hero_metrics") or DEFAULT_HERO_METRICS,
        "announcement": settings.get("announcement") or "",
        "announcement_visible": bool(settings.get("announcement_visible", bool(settings.get("announcement")))),
        "maintenance_mode": bool(settings.get("maintenance_mode", False)),
    }

def normalize_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "visible", "active"}


# ── Email (SMTP) ──────────────────────────────────────────────────────────────

def send_email(to_email, subject, text_body, html_body=None):
    host, username, password, sender, configured_sender_name, port, use_ssl, use_tls, timeout = smtp_config()
    configured, missing = smtp_config_status()
    if not configured:
        print(f"SMTP not configured ({', '.join(missing)}). Skipping: {subject} -> {to_email}")
        return False
    port = int(port)
    sender_name, sender_addr = parseaddr(sender)
    _, recipient_addr = parseaddr(to_email)
    _, username_addr = parseaddr(username or "")
    sender_addr = sender_addr or username_addr or sender
    recipient_addr = recipient_addr or to_email
    envelope_from = mail_env("SMTP_ENVELOPE_FROM", default=username_addr or sender_addr)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = formataddr((sender_name or configured_sender_name or "MicrochipCart", sender_addr))
    msg["To"]      = recipient_addr
    msg["Date"]    = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=(sender_addr.split("@", 1)[1] if "@" in sender_addr else None))
    if username_addr and username_addr.lower() != sender_addr.lower():
        msg["Reply-To"] = sender_addr
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as s:
                if username and password:
                    s.login(username, password)
                refused = s.sendmail(envelope_from, [recipient_addr], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as s:
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                if username and password:
                    s.login(username, password)
                refused = s.sendmail(envelope_from, [recipient_addr], msg.as_string())
        if refused:
            print(f"SMTP refused recipients: {refused}")
            return False
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
    used = set()
    try:
        if UPLOAD_DIR.exists():
            for img in UPLOAD_DIR.glob("*.webp"):
                m = re.fullmatch(r"(\d+)\.webp", img.name)
                if m:
                    used.add(int(m.group(1)))
    except OSError as exc:
        print(f"Could not inspect product upload directory: {exc}")
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
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_storage.save(destination)
    except OSError as exc:
        print(f"Product image upload failed: {exc}")
        raise ValueError("Product image storage is unavailable on this deployment. Use an image URL instead.")
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

def send_order_email_async(order):
    smtp_ok, _ = smtp_config_status()
    if not smtp_ok:
        return
    import threading
    def send():
        with app.app_context():
            try:
                send_order_email(order)
            except Exception as e:
                print(f"Async order email send failed: {e}")
    threading.Thread(target=send, daemon=True).start()


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
            inactive = orders_by_email.get(email, 0) == 0 and user.created_at and user.created_at < (now_utc() - timedelta(days=60))
            customer_rows.append({
                **user_to_dict(user),
                "orders": orders_by_email.get(email, 0),
                "spend": money(spend_by_email.get(email, 0)),
                "last_order": last_order_by_email.get(email, ""),
                "inactive": bool(inactive),
                "banned": (user.status or "") == "Banned",
                "signup_ip": "",
            })

        business_rows = []
        gst_seen = {}
        ip_seen = {}
        tempmail_domains = {"tempmail.com", "10minutemail.com", "mailinator.com", "guerrillamail.com", "yopmail.com"}
        for user in businesses:
            if user.gstin:
                gst_seen[user.gstin.upper()] = gst_seen.get(user.gstin.upper(), 0) + 1
            meta_ip = ""
            if isinstance(getattr(user, "profile_completed", None), dict):
                meta_ip = user.profile_completed.get("signup_ip", "")
            if meta_ip:
                ip_seen[meta_ip] = ip_seen.get(meta_ip, 0) + 1
        for user in businesses:
            email = normalize_email(user.email)
            profile = profile_by_id.get(str_id(user.id))
            gstin = (profile.gst_number if profile else user.gstin) or ""
            age_cutoff = now_utc() - timedelta(days=90)
            domain = email.rsplit("@", 1)[-1] if "@" in email else ""
            flag_reasons = []
            if orders_by_email.get(email, 0) == 0 and user.created_at and user.created_at < age_cutoff:
                flag_reasons.append("No orders in 90 days")
            if gstin and gst_seen.get(gstin.upper(), 0) > 1:
                flag_reasons.append("Duplicate GSTIN")
            if domain in tempmail_domains:
                flag_reasons.append("Temporary email domain")
            business_rows.append({
                **user_to_dict(user),
                "company_name": (profile.business_name if profile else user.company_name) or "",
                "business_address": (profile.business_address if profile else "") or "",
                "city_state": ((profile.business_address if profile else "") or "").split(",")[-2:] if (profile and profile.business_address) else [],
                "gstin": gstin,
                "gstin_verified": bool(gstin and len(gstin) >= 15),
                "approval_status": (profile.approval_status if profile else user.status) or "Pending",
                "orders": orders_by_email.get(email, 0),
                "spend": money(spend_by_email.get(email, 0)),
                "last_order": last_order_by_email.get(email, ""),
                "flagged": bool(flag_reasons) or (user.status or "") == "Suspended",
                "flag_reason": ", ".join(flag_reasons),
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
            "settings": {**(settings_row.value if settings_row else {}), **storefront_controls(settings_row.value if settings_row else {})},
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

SEO_BASE_URL = "https://microchipcart.in"
PUBLIC_SITEMAP_PATHS = ("/", "/products", "/community", "/help")
ROBOTS_TXT = f"""User-agent: *
Allow: /
Sitemap: {SEO_BASE_URL}/sitemap.xml
"""


def build_public_sitemap():
    urls = "\n".join(
        f"  <url><loc>{SEO_BASE_URL}{path}</loc></url>"
        for path in PUBLIC_SITEMAP_PATHS
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )


@app.get("/robots.txt")
def robots_txt():
    response = make_response(ROBOTS_TXT)
    response.mimetype = "text/plain"
    return response


@app.get("/sitemap.xml")
@app.get("/sitemap-website.xml")
@app.get("/sitemap-0.xml")
def public_sitemap():
    response = make_response(build_public_sitemap())
    response.mimetype = "application/xml"
    return response


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

@app.get("/api/auth/google/start")
def api_google_oauth_start():
    return api_error("Google signup is disabled. Please use email signup with a Gmail address.", 403)

@app.get("/auth/google/callback")
def google_oauth_callback_page():
    return redirect("/?google_oauth=failed#signup")

@app.post("/api/auth/google/session")
def api_google_oauth_session():
    return api_error("Google signup is disabled.", 403)

@app.get("/admin")
def admin_page():
    if session.get("user_id") and not session.get("admin_logged_in"):
        return redirect("/")
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login_page"))
    is_owner_admin = is_company_admin_session()
    
    if not is_owner_admin:
        db = DBSession()
        try:
            user_id = session.get("user_id")
            user = db.query(UserModel).filter_by(id=user_id).first()
            if not user:
                user = db.query(UserModel).filter_by(auth_user_id=user_id).first()
            if user:
                is_complete = check_and_auto_complete_profile(user, db)
                if not is_complete:
                    return redirect("/?setup_profile=1")
        finally:
            db.close()

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

@app.get("/company")
@app.get("/owner")
def owner_page():
    if session.get("admin_role") == "distributor" and not session.get("owner_logged_in"):
        return redirect(url_for("admin_page"))
    if not owner_session_is_current():
        clear_owner_session()
        return redirect(url_for("owner_login_page"))
    return render_template("owner_admin.html", store_mode=DATABASE_LABEL, owner_email=OWNER_EMAIL)

@app.get("/company/login")
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
        settings = {**settings, **storefront_controls(settings)}
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


@app.get("/api/storefront/hero-slides")
def api_storefront_hero_slides():
    db = DBSession()
    try:
        controls = storefront_controls(store_settings(db))
        return api_ok({"data": controls["hero_slides"], "slides": controls["hero_slides"]})
    finally:
        db.close()


@app.get("/api/storefront/controls")
def api_storefront_controls():
    db = DBSession()
    try:
        controls = storefront_controls(store_settings(db))
        return api_ok({"data": controls, **controls})
    finally:
        db.close()


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
    supabase_auth_configured = bool(
        supabase_url
        and supabase_url not in SUPABASE_PLACEHOLDERS
        and supabase_key
        and supabase_key not in SUPABASE_PLACEHOLDERS
    )
    supabase_admin_configured = bool(
        supabase_url
        and supabase_url not in SUPABASE_PLACEHOLDERS
        and clean_env(os.getenv("SUPABASE_SERVICE_ROLE_KEY")) not in SUPABASE_PLACEHOLDERS
    )
    supabase_connected = engine.dialect.name == "postgresql" and db_ok
    return api_ok({
        "status": "ok" if db_ok else "database_error",
        "database": "connected" if db_ok else "unavailable",
        "store_mode": DATABASE_LABEL,
        "supabase_configured": supabase_configured,
        "supabase_connected": supabase_connected,
        "supabase_auth_configured": supabase_auth_configured,
        "supabase_auth_connected": bool(supabase),
        "supabase_admin_configured": supabase_admin_configured,
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
PASSWORD_RESET_TTL_SECONDS = 15 * 60
PASSWORD_RESET_LENGTH = 6
PASSWORD_RESET_GENERIC_MESSAGE = "If an account exists for that email, a reset code has been sent."
EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

def email_otp_digest(email, otp):
    secret = auth_token_secret()
    message = f"{normalize_email(email)}:{str(otp or '').strip()}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()

def password_reset_digest(email, code):
    message = f"password-reset:{normalize_email(email)}:{str(code or '').strip()}".encode("utf-8")
    return hmac.new(auth_token_secret(), message, hashlib.sha256).hexdigest()

def email_otp_token_signature(email, digest, expires_at):
    secret = auth_token_secret()
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

def make_supabase_email_otp_token(email, expires_at):
    expires_at_text = expires_at.isoformat()
    email = normalize_email(email)
    payload = {
        "email": email,
        "provider": "supabase",
        "expires_at": expires_at_text,
        "sig": email_otp_token_signature(email, "supabase", expires_at_text),
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

def read_supabase_email_otp_token(token):
    try:
        raw = base64.urlsafe_b64decode(str(token or "").encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, "bad_token"

    email = normalize_email(payload.get("email"))
    provider = payload.get("provider")
    expires_at_text = payload.get("expires_at")
    sig = payload.get("sig")
    if provider != "supabase" or not email or not expires_at_text or not sig:
        return None, "bad_token"
    expected_sig = email_otp_token_signature(email, "supabase", expires_at_text)
    if not hmac.compare_digest(sig, expected_sig):
        return None, "bad_signature"
    try:
        expires_at = datetime.fromisoformat(expires_at_text)
    except Exception:
        return None, "bad_expiry"
    return {"email": email, "expires_at": expires_at}, None

def send_app_email_otp(email):
    expires_at = now_utc() + timedelta(seconds=EMAIL_OTP_TTL_SECONDS)
    otp = f"{secrets.randbelow(10 ** EMAIL_OTP_LENGTH):0{EMAIL_OTP_LENGTH}d}"
    text_body = (
        f"Your MicroChip Cart verification code is {otp}.\n\n"
        "This code expires in 10 minutes. Do not share it with anyone."
    )
    html_body = (
        "<p>Your MicroChip Cart verification code is:</p>"
        f"<h2 style=\"letter-spacing:4px;\">{otp}</h2>"
        "<p>This code expires in 10 minutes. Do not share it with anyone.</p>"
    )
    smtp_ok, _ = smtp_config_status()
    if smtp_ok:
        if send_email(email, "Your MicroChip Cart verification code", text_body, html_body):
            return make_email_otp_token(email, otp, expires_at)
        print("APP EMAIL OTP SMTP SEND FAILED; trying Supabase fallback.")

    if supabase and SUPABASE_EMAIL_OTP_ENABLED:
        sent, error = send_supabase_email_otp(email)
        if sent:
            return make_supabase_email_otp_token(email, expires_at)
        print(f"SUPABASE OTP SEND FAILURE AFTER SMTP PATH: {error}")

    return None

def local_email_verification_fallback(email):
    smtp_ok, _ = smtp_config_status()
    if (
        os.getenv("APP_ENV", "development") == "production"
        or supabase
        or smtp_ok
        or not env_flag("ALLOW_DEV_OTP_DISPLAY", False)
    ):
        return None
    otp = "000000"
    expires_at = now_utc() + timedelta(seconds=EMAIL_OTP_TTL_SECONDS)
    return {
        "otp": otp,
        "otp_token": make_email_otp_token(email, otp, expires_at),
        "message": "Email OTP is unavailable on this deployment. Continue with the pre-filled verification code.",
    }

def send_password_reset_email(email, code):
    text_body = (
        f"Your MicroChip Cart password reset code is {code}.\n\n"
        "This code expires in 15 minutes. If you did not request it, you can ignore this email."
    )
    html_body = (
        "<p>Your MicroChip Cart password reset code is:</p>"
        f"<h2 style=\"letter-spacing:4px;\">{code}</h2>"
        "<p>This code expires in 15 minutes. If you did not request it, you can ignore this email.</p>"
    )
    return send_email(email, "Reset your MicroChip Cart password", text_body, html_body)

def local_password_reset_fallback(email, code):
    smtp_ok, _ = smtp_config_status()
    if supabase or smtp_ok:
        return None
    return {
        "reset_code": code,
        "password_reset_fallback": True,
        "message": "Password reset email is unavailable on this deployment. Continue with the pre-filled reset code.",
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
        supabase_token_record, supabase_token_error = read_supabase_email_otp_token(otp_token)
        if not supabase_token_record:
            print(f"APP EMAIL OTP TOKEN FAILURE: {token_error}; SUPABASE TOKEN FAILURE: {supabase_token_error}")
            return False, token_error
        if supabase_token_record["email"] != email:
            print("SUPABASE EMAIL OTP EMAIL MISMATCH:", mask_email_for_log(email), mask_email_for_log(supabase_token_record["email"]))
            return False, "email_mismatch"
        if now_utc() > supabase_token_record["expires_at"]:
            print("SUPABASE EMAIL OTP EXPIRED")
            return False, "expired"
        if not supabase:
            print("SUPABASE EMAIL OTP VERIFY FAILURE: missing Supabase client")
            return False, "missing_supabase"
        _, _, supabase_error = supabase_verify_email_otp(email, otp)
        if supabase_error:
            print(f"SUPABASE EMAIL OTP VERIFICATION FAILURE: {supabase_error}")
            return False, "invalid"
        print("SUPABASE EMAIL OTP VERIFICATION SUCCESS")
        return True, None
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
    data["account_type"] = data.get("account_type")
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
    account_type = data.get("account_type")
    if not account_type:
        return "Account type is required."
    if account_type not in ("B2C", "B2B"):
        return "Invalid account type."
    email = normalize_email(data.get("email") or "")
    if not re.match(EMAIL_REGEX, email):
        return "Enter a valid email address."
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

    existing = None
    if auth_id:
        existing = db.query(UserModel).filter_by(auth_user_id=auth_id).first()
        if not existing:
            existing = db.query(UserModel).filter_by(id=auth_id).first()
    if not existing:
        existing = db.query(UserModel).filter_by(email=email).first()
    if phone:
        phone_user = db.query(UserModel).filter(UserModel.phone == phone).first()
        if phone_user and (not existing or str_id(phone_user.id) != str_id(existing.id)):
            print(f"SIGNUP PHONE CONFLICT: continuing without duplicate phone for {mask_email_for_log(email)}")
            phone = None

    user = existing
    if not user:
        user = UserModel(email=email, created_at=getattr(auth_user, "created_at", now_utc()))
        if auth_id:
            user.id = auth_id
            user.auth_user_id = auth_id
        db.add(user)
    elif auth_id:
        user.auth_user_id = auth_id

    existing_verified = bool(existing and existing.email_verified)
    if existing_verified:
        return None, "This email already has an account. Please login."

    if account_type == "B2B" and getattr(existing, "account_type", None) != "B2B":
        user.status = "Pending"

    user.name = full_name
    user.full_name = full_name
    user.phone = phone
    user.password_hash = generate_password_hash(data["password"])
    user.account_type = account_type
    user.role = role
    if account_type == "B2B":
        user.company_name = data.get("company_name") or user.company_name
        user.gstin = data.get("gstin") or user.gstin
    elif not existing_verified:
        user.company_name = None
        user.gstin = None
    user.is_admin = False
    user.email_verified = True
    user.phone_verified = False
    user.status = user.status or ("Pending" if account_type == "B2B" else "Active")
    user.profile_completed = True
    user.updated_at = now_utc()
    db.flush()

    if account_type == "B2B":
        business = db.query(BusinessProfileModel).filter_by(id=user.id).first()
        if not business:
            business = BusinessProfileModel(
                id=user.id,
                business_name=data.get("company_name") or full_name,
                business_address=data.get("business_address") or "",
                contact_number=phone or "",
                gst_number=data.get("gstin") or "",
                approval_status="Pending",
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            db.add(business)
        business.business_name = data.get("company_name") or full_name
        business.business_address = data.get("business_address") or ""
        business.contact_number = phone or ""
        business.gst_number = data.get("gstin") or ""
        business.approval_status = "Pending"
        business.updated_at = now_utc()
        db.flush()

    return user, None

def signup_user_response(user, approval_status="Approved"):
    return {
        "id": str_id(user.id),
        "name": user.name or "",
        "full_name": user.full_name or user.name or "",
        "email": user.email,
        "phone": user.phone or "",
        "account_type": user.account_type or "B2C",
        "role": user.role or ("business" if user.account_type == "B2B" else "customer"),
        "company_name": user.company_name or "",
        "gstin": user.gstin or "",
        "is_admin": bool(user.is_admin),
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "profile_completed": bool(getattr(user, "profile_completed", False)),
        "auth_provider": "email",
        "approval_status": approval_status,
    }

@app.post("/api/auth/send-email-otp")
def api_send_email_otp():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email"))
    print("SEND EMAIL OTP REQUEST EMAIL:", email or "(missing)")
    if not email:
        print("SEND EMAIL OTP ERROR: missing email.")
        return api_error("Email is required.", 400)
    if not re.match(EMAIL_REGEX, email):
        print("SEND EMAIL OTP ERROR: invalid email.")
        return api_error("Enter a valid email address.", 400)

    db = DBSession()
    try:
        existing = db.query(UserModel).filter_by(email=email).first()
        if existing and existing.email_verified:
            print("SEND EMAIL OTP: existing verified account; OTP can confirm ownership and refresh password.")
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
                "cooldown_seconds": EMAIL_OTP_COOLDOWN_SECONDS,
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
    def signup_error(message):
        return api_error(message, 200)

    validation_error = validate_signup_payload(data, require_otp=True)
    if validation_error:
        print(f"OTP VERIFY VALIDATION FAILED: {validation_error}")
        return signup_error(validation_error)

    otp_ok, otp_error = verify_app_email_otp(data["email"], data["otp"], data.get("otp_token"))
    if not otp_ok:
        print(f"APP EMAIL OTP VERIFICATION FAILED: {otp_error}")
        return signup_error(INVALID_EMAIL_OTP_MESSAGE)

    print("APP EMAIL OTP VERIFIED")
    metadata = {
        "name": data.get("full_name") or data.get("name"),
        "account_type": data["account_type"],
        "role": "business" if data["account_type"] == "B2B" else "customer",
    }
    auth_user = None
    store_password = True
    auth_error = None
    if supabase:
        auth_user, auth_error = supabase_ensure_verified_auth_user(data["email"], data["password"], metadata)
        if not auth_user:
            print(f"Supabase admin auth user setup failed after OTP verification: {auth_error}")
            try:
                auth_user, auth_error = supabase_signup_recovering_orphan(data["email"], data["password"], data["account_type"])
            except Exception as signup_exc:
                auth_user = None
                auth_error = str(signup_exc)
            if not auth_user and engine.dialect.name == "postgresql":
                return signup_error("Account auth setup failed. Please contact support to check Supabase service role settings.")
        else:
            store_password = False
    else:
        print("Creating local password user after OTP verification.")

    db = DBSession()
    try:
        user, user_error = create_or_update_verified_user(db, auth_user, data, store_password=store_password)
        if user_error:
            print(f"LOCAL USER SETUP AFTER OTP FAILED: {user_error}")
            if user_error.startswith("This email already has an account"):
                db.rollback()
                return signup_error(user_error)
            db.rollback()
            return signup_error(user_error)
        user_payload = signup_user_response(
            user,
            "Pending" if data["account_type"] == "B2B" else "Approved",
        )
        redirect_url = "/?setup_profile=1" if not user_payload["profile_completed"] else ("/admin" if data["account_type"] == "B2B" else "/")
        db.commit()
        session_login_for(user)
        message = (
            "Business account created. Phone/GST verification and admin approval are pending."
            if data["account_type"] == "B2B"
            else "Email verified. Account created successfully."
        )
        return api_ok({
            "message": message,
            "user": user_payload,
            "auth_token": make_auth_token(user),
            "redirect_url": redirect_url
        }, 201)
    except Exception as exc:
        db.rollback()
        print(f"LOCAL USER SETUP EXCEPTION AFTER AUTH SUCCESS ({type(exc).__name__}): {exc}")
        if isinstance(exc, IntegrityError):
            error_text = str(getattr(exc, "orig", exc)).lower()
            if "phone" in error_text:
                return signup_error("This phone number is already registered.")
            if "email" in error_text:
                return signup_error("This email already has an account.")
            if "business_profiles" in error_text or "business profile" in error_text:
                return signup_error("Business profile could not be saved. Please check your company details and try again.")
            if "not-null" in error_text or "not null" in error_text:
                return signup_error("Please complete all required signup fields.")
        if isinstance(exc, SQLAlchemyError):
            error_text = str(getattr(exc, "orig", exc)).lower()
            if "foreign key" in error_text and ("auth" in error_text or "users" in error_text):
                return signup_error("Account auth setup failed. Please contact support to check Supabase service role settings.")
            return signup_error("Account could not be created. Please check your signup details and try again.")
        return api_error("Account could not be created. Please try again.", 500)
    finally:
        db.close()

@app.post("/api/auth/forgot-password")
def api_forgot_password():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email"))
    if not email:
        return api_error("Email is required.", 400)

    db = DBSession()
    try:
        user = db.query(UserModel).filter_by(email=email).first()
        if not user and supabase:
            auth_user = supabase_find_auth_user_by_email(email)
            auth_id = auth_user_id(auth_user)
            if auth_user and auth_id:
                user = db.query(UserModel).filter_by(auth_user_id=auth_id).first()
                if not user:
                    account_type = supabase_account_type(auth_user, "B2C")
                    name = (
                        supabase_user_metadata(auth_user).get("name")
                        or auth_user_email(auth_user).split("@", 1)[0]
                    )
                    created_at = as_utc(getattr(auth_user, "created_at", None)) or now_utc()
                    user = UserModel(
                        id=auth_id,
                        auth_user_id=auth_id,
                        email=email,
                        name=name,
                        full_name=name,
                        account_type=account_type,
                        role="business" if account_type == "B2B" else "customer",
                        email_verified=bool(getattr(auth_user, "email_confirmed_at", None)),
                        status="Active",
                        created_at=created_at,
                        updated_at=now_utc(),
                    )
                    db.add(user)
                    db.flush()
        if not user:
            print(f"Password reset requested for unknown email: {mask_email_for_log(email)}")
            return api_ok({"message": PASSWORD_RESET_GENERIC_MESSAGE})
        if (user.status or "Active") not in ("Active", "Pending"):
            print(f"Password reset skipped for inactive account: {mask_email_for_log(email)}")
            return api_ok({"message": PASSWORD_RESET_GENERIC_MESSAGE})

        code = f"{secrets.randbelow(10 ** PASSWORD_RESET_LENGTH):0{PASSWORD_RESET_LENGTH}d}"
        user.reset_password_hash = password_reset_digest(email, code)
        user.reset_password_expires_at = now_utc() + timedelta(seconds=PASSWORD_RESET_TTL_SECONDS)
        user.updated_at = now_utc()
        db.commit()

        if send_password_reset_email(email, code):
            return api_ok({"message": PASSWORD_RESET_GENERIC_MESSAGE})

        fallback = local_password_reset_fallback(email, code)
        if fallback:
            return api_ok(fallback)

        user.reset_password_hash = None
        user.reset_password_expires_at = None
        user.updated_at = now_utc()
        db.commit()
        return api_error("Could not send reset email. Please check SMTP settings.", 400)
    except Exception as exc:
        db.rollback()
        print(f"Password reset request failed: {exc}")
        return api_error("Could not start password reset. Please try again.", 500)
    finally:
        db.close()


@app.post("/api/auth/reset-password")
def api_reset_password():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email"))
    code = str(data.get("code") or "").strip()
    new_password = data.get("new_password") or ""
    confirm_password = data.get("confirm_password") or ""

    if not email or not code:
        return api_error("Email and reset code are required.", 400)
    if len(new_password) < 6:
        return api_error("Password must be at least 6 characters.")
    if new_password != confirm_password:
        return api_error("New passwords do not match.")

    db = DBSession()
    try:
        user = db.query(UserModel).filter_by(email=email).first()
        if not user or not user.reset_password_hash or not user.reset_password_expires_at:
            return api_error("Invalid or expired reset code.", 400)
        expires_at = as_utc(user.reset_password_expires_at)
        if not expires_at or now_utc() > expires_at:
            user.reset_password_hash = None
            user.reset_password_expires_at = None
            user.updated_at = now_utc()
            db.commit()
            return api_error("Invalid or expired reset code.", 400)
        if not hmac.compare_digest(user.reset_password_hash, password_reset_digest(email, code)):
            return api_error("Invalid or expired reset code.", 400)

        if supabase:
            auth_user = supabase_find_auth_user_by_id(getattr(user, "auth_user_id", None))
            if not auth_user:
                auth_user = supabase_find_auth_user_by_email(email)
            if auth_user:
                ok, admin_error = supabase_set_user_password(auth_user_id(auth_user), new_password, supabase_user_metadata(auth_user))
                if not ok:
                    return api_error(f"Failed to reset password: {admin_error}", 400)
                if not user.auth_user_id:
                    user.auth_user_id = auth_user_id(auth_user)

        user.password_hash = generate_password_hash(new_password)
        user.reset_password_hash = None
        user.reset_password_expires_at = None
        user.updated_at = now_utc()
        db.commit()
        session_login_for(user)
        return api_ok({
            "message": "Password reset. You are now logged in.",
            "user": public_user(user),
            "auth_token": make_auth_token(user),
            "redirect_url": auth_redirect_url(user),
        })
    except Exception as exc:
        db.rollback()
        print(f"Password reset failed: {exc}")
        return api_error("Could not reset password. Please try again.", 500)
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
                "cooldown_seconds": EMAIL_OTP_COOLDOWN_SECONDS,
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
        local_user = db.query(UserModel).filter_by(email=email).first()
        if local_user and local_user.password_hash:
            if check_password_hash(local_user.password_hash, password):
                if not local_user.email_verified and not getattr(local_user, "is_admin", False):
                    return api_error("Please verify your email before logging in.", 403)
                if (local_user.status or "Active") not in ("Active", "Pending"):
                    return api_error("This account is not active. Please contact support.", 403)
                check_and_auto_complete_profile(local_user, db)
                local_user.last_login = now_utc()
                db.commit()
                db.refresh(local_user)
                session_login_for(local_user)
                return api_ok({"user": public_user(local_user), "auth_token": make_auth_token(local_user), "redirect_url": auth_redirect_url(local_user)})
            return api_error("Invalid email or password.", 401)

        should_try_supabase_auth = bool(
            supabase
            and SUPABASE_AUTH_LOGIN_FALLBACK
            and local_user
            and not local_user.password_hash
        )
        if not should_try_supabase_auth:
            user = local_user
            if not user and can_auto_create_test_account():
                print(f"LOCAL TEST AUTH: auto-creating fallback account for {mask_email_for_log(email)}")
                user = create_local_test_user(db, email, password, requested_type)
            if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
                return api_error("Invalid email or password.", 401)
            if not user.email_verified and not getattr(user, "is_admin", False):
                return api_error("Please verify your email before logging in.", 403)
            if (user.status or "Active") not in ("Active", "Pending"):
                return api_error("This account is not active. Please contact support.", 403)
            check_and_auto_complete_profile(user, db)
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
            user = db.query(UserModel).filter_by(auth_user_id=auth_user.id).first()
        if not user:
            user = db.query(UserModel).filter_by(email=email).first()
            if user:
                user.auth_user_id = auth_user.id
                db.flush()

        email_verified = bool(getattr(auth_user, "email_confirmed_at", None))
        account_type = supabase_account_type(auth_user, getattr(local_user, "account_type", None) or requested_type or "B2C")
        role = "business" if account_type == "B2B" else "customer"

        if not user:
            user = UserModel(
                id=auth_user.id,
                auth_user_id=auth_user.id,
                email=email,
                phone=auth_user.phone or None,
                password_hash=generate_password_hash(password),
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
            user.auth_user_id = auth_user.id
            user.email_verified = bool(user.email_verified or email_verified)
            if not user.role:
                user.role = role
            if not user.account_type:
                user.account_type = account_type
            if not user.password_hash:
                user.password_hash = generate_password_hash(password)

        if not user.email_verified and not getattr(user, "is_admin", False):
            db.rollback()
            return api_error("Please verify your email before logging in.", 403)

        check_and_auto_complete_profile(user, db)
        user.last_login = now_utc()
        db.commit()
        db.refresh(user)
        session_login_for(user)
        return api_ok({"user": public_user(user), "auth_token": make_auth_token(user), "redirect_url": auth_redirect_url(user)})
    except Exception as exc:
        db.rollback()
        print(f"Login failed unexpectedly: {exc}")
        if isinstance(exc, SQLAlchemyError):
            return api_error("Login is temporarily busy. Please try again in a moment.", 503)
        return api_error("Login failed. Please try again.", 500)
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


def is_profile_complete(user):
    if not user:
        return True
    if getattr(user, "is_admin", False):
        return True
    return bool(getattr(user, "profile_completed", False))

def check_and_auto_complete_profile(user, db):
    if not user:
        return False
    if getattr(user, "profile_completed", False):
        return True
    if getattr(user, "is_admin", False):
        user.profile_completed = True
        db.commit()
        return True
    
    # Check if they have complete details pre-filled
    has_name = bool((user.name or "").strip()) and not (user.name or "").strip().lower().startswith("google user")
    has_phone = bool((user.phone or "").strip())
    
    if (user.account_type or "B2C") == "B2B":
        has_business = bool((user.company_name or "").strip())
        if has_name and has_phone and has_business:
            user.profile_completed = True
            db.commit()
            return True
    else:
        if has_name and has_phone:
            user.profile_completed = True
            db.commit()
            return True
    return False

@app.get("/api/auth/me")
def api_me():
    user = current_user()
    return api_ok({"user": public_user(user), "auth_token": make_auth_token(user) if user else ""})

@app.post("/api/auth/complete-profile")
def api_complete_profile():
    user = current_user()
    if not user:
        return api_error("Please log in first.", 401)
        
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    account_type = normalize_account_type(data.get("account_type") or "B2C")
    
    if not name or not phone:
        return api_error("Name and phone number are required.", 400)
        
    db = DBSession()
    try:
        row = db.query(UserModel).filter_by(id=user.id).first()
        if not row:
            row = db.query(UserModel).filter_by(auth_user_id=user.id).first()
        if not row:
            return api_error("User not found.", 404)
            
        existing_phone = db.query(UserModel).filter(UserModel.phone == phone, UserModel.id != row.id).first()
        if existing_phone:
            return api_error("This phone number is already registered.", 400)
            
        row.name = name
        row.full_name = name
        row.phone = phone
        row.account_type = account_type
        row.role = "business" if account_type == "B2B" else "customer"
        
        if account_type == "B2B":
            company_name = (data.get("company_name") or "").strip()
            gstin = (data.get("gstin") or "").strip().upper()
            business_address = (data.get("business_address") or "").strip()
            
            if not company_name:
                return api_error("Company name is required for business accounts.", 400)
            if gstin and not re.match(GSTIN_REGEX, gstin):
                return api_error("Invalid GST format. Please enter a valid 15-character GSTIN.", 400)
                
            row.company_name = company_name
            row.gstin = gstin
            
            business = db.query(BusinessProfileModel).filter_by(id=row.id).first()
            if not business:
                business = BusinessProfileModel(id=row.id)
                db.add(business)
            business.business_name = company_name
            business.business_address = business_address
            business.contact_number = phone
            business.gst_number = gstin
            business.approval_status = getattr(business, "approval_status", "Pending") or "Pending"
            business.updated_at = now_utc()
            
        row.profile_completed = True
        row.updated_at = now_utc()
        db.commit()
        db.refresh(row)
        
        session_login_for(row)
        
        return api_ok({
            "message": "Profile setup completed.",
            "user": public_user(row),
            "auth_token": make_auth_token(row),
            "redirect_url": auth_redirect_url(row)
        })
    except Exception as exc:
        db.rollback()
        print(f"Complete profile failed: {exc}")
        return api_error("Could not complete profile setup. Please try again.", 500)
    finally:
        db.close()


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
    data = request.get_json(silent=True) or {}
    user = require_user(request_auth_token(data))
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
    supabase_user = None
    supabase_error = None
    if supabase:
        supabase_user, supabase_session, supabase_error = supabase_verify_password_for_user(user, current_password)
        supabase_password_ok = bool(supabase_user)

    if not local_password_ok and not supabase_password_ok:
        return api_error("Current password is incorrect.", 401)

    if supabase_password_ok:
        try:
            supabase_update_password_for_session(supabase_session, new_password)
        except Exception as exc:
            return api_error(f"Failed to change password: {str(exc)}", 400)
    elif local_password_ok and supabase:
        auth_id = linked_auth_user_id(user)
        auth_user = supabase_find_auth_user_by_id(auth_id)
        if auth_user:
            ok, admin_error = supabase_set_user_password(auth_user_id(auth_user), new_password, supabase_user_metadata(auth_user))
            if not ok:
                return api_error(f"Failed to change password: {admin_error}", 400)
        elif supabase_error:
            print(f"Skipping Supabase password update for local password user {mask_email_for_log(user.email)}: {supabase_error}")

    db = DBSession()
    try:
        row = db.query(UserModel).filter_by(id=user.id).first()
        if not row:
            row = db.query(UserModel).filter_by(auth_user_id=linked_auth_user_id(user)).first()
        if row:
            if getattr(user, "auth_user_id", None) and not row.auth_user_id:
                row.auth_user_id = user.auth_user_id
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
    if getattr(user, "is_admin", False):
        return api_error("Admin and owner accounts cannot be deleted.", 403)

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
        # Nullify user_id references in other tables to avoid foreign key constraint violations
        db.query(OrderModel).filter(OrderModel.user_id == user.id).update({OrderModel.user_id: None}, synchronize_session=False)
        db.query(ReviewModel).filter(ReviewModel.user_id == user.id).update({ReviewModel.user_id: None}, synchronize_session=False)
        db.query(EventModel).filter(EventModel.user_id == user.id).update({EventModel.user_id: None}, synchronize_session=False)
        db.query(CommunityPostModel).filter(CommunityPostModel.user_id == user.id).update({CommunityPostModel.user_id: None}, synchronize_session=False)
        db.query(CommunityReplyModel).filter(CommunityReplyModel.user_id == user.id).update({CommunityReplyModel.user_id: None}, synchronize_session=False)

        # Delete corresponding business profile if it exists
        db.query(BusinessProfileModel).filter(BusinessProfileModel.id == user.id).delete(synchronize_session=False)

        # Delete the user from the users table
        row = db.query(UserModel).filter_by(id=user.id).first()
        if row:
            db.delete(row)
            db.commit()

        # Delete the user from Supabase Auth if linked
        auth_id = getattr(user, "auth_user_id", None) or user.id
        if auth_id and supabase:
            if not supabase_delete_auth_user(auth_id):
                print(f"Failed to delete user {auth_id} from Supabase Auth")

        # Clear all session variables
        session.pop("user_id", None)
        session.pop("admin_logged_in", None)
        session.pop("admin_role", None)
        session.pop("owner_logged_in", None)
        session.pop("owner_auth_version", None)

        return api_ok({"message": "Account deleted."})
    except Exception as exc:
        db.rollback()
        print(f"Failed to delete account: {exc}")
        return api_error("Could not delete account. Please try again.", 500)
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
        
        # Track view asynchronously
        import threading
        def track_view_async(prod_id, usr_id):
            with app.app_context():
                db_local = DBSession()
                try:
                    p = db_local.query(ProductModel).filter_by(id=prod_id).first()
                    if p:
                        p.views = (p.views or 0) + 1
                        db_local.add(EventModel(type="view", product_id=p.id, user_id=usr_id))
                        db_local.commit()
                except Exception as e:
                    db_local.rollback()
                    print(f"Async view tracking failed: {e}")
                finally:
                    db_local.close()
        
        threading.Thread(target=track_view_async, args=(product.id, user.id if user else None)).start()

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
    user = current_user()
    db = DBSession()
    try:
        posts = db.query(CommunityPostModel).order_by(CommunityPostModel.created_at.desc()).all()
        reply_counts = {}
        if posts:
            counts = (
                db.query(CommunityReplyModel.post_id, func.count(CommunityReplyModel.id))
                  .filter(CommunityReplyModel.post_id.in_([p.id for p in posts]))
                  .group_by(CommunityReplyModel.post_id)
                  .all()
            )
            reply_counts = {str_id(post_id): count for post_id, count in counts}
        return api_ok({"posts": [post_to_dict(p, db, user, reply_counts.get(str_id(p.id), 0)) for p in posts]})
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
        return api_ok({"post": post_to_dict(post, db, user)}, 201)
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
        return api_ok({"post": post_to_dict(post, db, user)})
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
    user = current_user()
    db = DBSession()
    try:
        replies = (db.query(CommunityReplyModel)
                     .filter_by(post_id=post_id)
                     .order_by(CommunityReplyModel.created_at.asc())
                     .all())
        return api_ok({"replies": [reply_to_dict(r, user) for r in replies]})
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
    product_id = data.get("product_id")
    event_metadata = data.get("metadata") or {}

    import threading
    def log_event_async():
        with app.app_context():
            db_local = DBSession()
            try:
                event = EventModel(
                    type       = event_type,
                    product_id = product_id,
                    user_id    = user.id if user else None,
                    event_metadata = event_metadata,
                )
                db_local.add(event)
                if product_id and event_type == "cart_add":
                    p = db_local.query(ProductModel).filter_by(id=product_id).first()
                    if p:
                        p.cart_adds  = (p.cart_adds or 0) + 1
                        p.updated_at = now_utc()
                db_local.commit()
            except Exception as e:
                db_local.rollback()
                print(f"Async event logging failed: {e}")
            finally:
                db_local.close()

    threading.Thread(target=log_event_async).start()
    return api_ok({"message": "Event logged asynchronously."}, 201)


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
        send_order_email_async(order_dict)
        return api_ok({"order": order_dict, "email_sent": True}, 201)
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


@app.post("/api/orders/<order_id>/cancel")
def api_cancel_order(order_id):
    user = require_user()
    db = DBSession()
    try:
        order = db.query(OrderModel).filter_by(id=order_id, user_id=user.id).first()
        if not order:
            return api_error("Order not found.", 404)
        if order.status != "Pending":
            return api_error("Only pending orders can be cancelled.", 400)
        
        order.status = "Cancelled"
        order.updated_at = now_utc()
        db.commit()
        db.refresh(order)
        return api_ok({"order": order_to_dict(order), "message": "Order cancelled successfully."})
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
        
    db = DBSession()
    try:
        user = db.query(UserModel).filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            if (user.account_type or "B2C") == "B2B":
                if not user.email_verified:
                    return api_error("Please verify your email before logging in.", 403)
                
                business = db.query(BusinessProfileModel).filter_by(id=user.id).first()
                if not business or (business.approval_status or "Pending") != "Approved":
                    return api_error("Your business account is pending approval. Please wait for an administrator to review your request.", 403)
                
                if (user.status or "Active") not in ("Active", "Pending"):
                    return api_error("This account is not active. Please contact support.", 403)
                
                check_and_auto_complete_profile(user, db)
                session_login_for(user)
                user.last_login = now_utc()
                db.commit()
                return api_ok()
    finally:
        db.close()
        
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
    owner_credentials_ok = email == OWNER_EMAIL and password == OWNER_PASSWORD
    admin_credentials_ok = email == ADMIN_EMAIL and password == ADMIN_PASSWORD
    temp_credentials_ok = email == TEMP_COMPANY_EMAIL and password == TEMP_COMPANY_PASSWORD
    if owner_credentials_ok or admin_credentials_ok or temp_credentials_ok:
        session["owner_logged_in"] = True
        session["owner_auth_version"] = owner_auth_version()
        session["owner_login_at"] = now_iso()
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


@app.get("/api/owner/hero-slides")
def api_owner_hero_slides():
    require_owner()
    db = DBSession()
    try:
        slides = storefront_controls(store_settings(db))["hero_slides"]
        return api_ok({"data": slides, "slides": slides})
    finally:
        db.close()


def slide_from_payload(data, fallback=None):
    fallback = fallback or {}
    allowed = (
        "kicker", "title", "description", "cta_label", "cta_link",
        "product1_name", "product1_price", "product1_badge", "product1_image",
        "product2_name", "product2_price", "product2_badge", "product2_image",
    )
    slide = {**fallback}
    slide["id"] = str(fallback.get("id") or data.get("id") or f"slide-{secrets.token_hex(4)}")
    slide["order"] = int(data.get("order") or fallback.get("order") or 999)
    for field in allowed:
        if field in data:
            slide[field] = str(data.get(field) or "").strip()
    return slide


@app.post("/api/owner/hero-slides")
def api_owner_create_hero_slide():
    require_owner()
    data = request.get_json(silent=True) or {}
    db = DBSession()
    try:
        settings = store_settings(db)
        slides = list(storefront_controls(settings)["hero_slides"])
        slide = slide_from_payload({**data, "order": len(slides) + 1})
        slides.append(slide)
        settings["hero_slides"] = slides
        settings["updated_at"] = now_iso()
        save_store_settings(db, settings)
        return api_ok({"data": slide, "slide": slide}, 201)
    finally:
        db.close()


@app.put("/api/owner/hero-slides/<slide_id>")
def api_owner_update_hero_slide(slide_id):
    require_owner()
    data = request.get_json(silent=True) or {}
    db = DBSession()
    try:
        settings = store_settings(db)
        slides = list(storefront_controls(settings)["hero_slides"])
        updated = None
        for index, slide in enumerate(slides):
            if str(slide.get("id")) == slide_id:
                updated = slide_from_payload(data, slide)
                slides[index] = updated
                break
        if not updated:
            return api_error("Slide not found.", 404)
        settings["hero_slides"] = sorted(slides, key=lambda item: int(item.get("order") or 999))
        settings["updated_at"] = now_iso()
        save_store_settings(db, settings)
        return api_ok({"data": updated, "slide": updated})
    finally:
        db.close()


@app.delete("/api/owner/hero-slides/<slide_id>")
def api_owner_delete_hero_slide(slide_id):
    require_owner()
    db = DBSession()
    try:
        settings = store_settings(db)
        slides = [slide for slide in storefront_controls(settings)["hero_slides"] if str(slide.get("id")) != slide_id]
        settings["hero_slides"] = [{**slide, "order": index + 1} for index, slide in enumerate(slides)]
        settings["updated_at"] = now_iso()
        save_store_settings(db, settings)
        return api_ok({"data": settings["hero_slides"], "slides": settings["hero_slides"]})
    finally:
        db.close()


@app.put("/api/owner/hero-slides/order")
def api_owner_order_hero_slides():
    require_owner()
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    db = DBSession()
    try:
        settings = store_settings(db)
        slide_map = {str(slide.get("id")): slide for slide in storefront_controls(settings)["hero_slides"]}
        ordered = []
        for index, slide_id in enumerate(ids):
            if str(slide_id) in slide_map:
                ordered.append({**slide_map.pop(str(slide_id)), "order": index + 1})
        ordered.extend({**slide, "order": len(ordered) + i + 1} for i, slide in enumerate(slide_map.values()))
        settings["hero_slides"] = ordered
        settings["updated_at"] = now_iso()
        save_store_settings(db, settings)
        return api_ok({"data": ordered, "slides": ordered})
    finally:
        db.close()


@app.put("/api/owner/settings")
def api_owner_update_settings():
    require_owner()
    data = request.get_json(silent=True) or {}
    db = DBSession()
    try:
        settings = store_settings(db)
        for key in ("announcement", "store_name", "support_email", "session_timeout_minutes", "whitelist_ips"):
            if key in data:
                settings[key] = str(data.get(key) or "").strip()
        for key in ("announcement_visible", "maintenance_mode"):
            if key in data:
                settings[key] = normalize_bool(data.get(key))
        for key in ("trust_badges", "category_chips", "hero_metrics"):
            if isinstance(data.get(key), list):
                settings[key] = data[key]
        settings["updated_at"] = now_iso()
        save_store_settings(db, settings)
        return api_ok({"data": settings, "settings": settings})
    finally:
        db.close()


@app.get("/api/owner/notifications")
def api_owner_notifications():
    require_owner()
    payload = owner_overview_payload()
    cards = payload.get("cards", {})
    flagged = [row for row in payload.get("businesses", []) if row.get("flagged")]
    low_stock = payload.get("insights", {}).get("low_stock", [])
    alerts = [
        {"type": "distributors", "label": "New distributor applications", "count": cards.get("pending_businesses", 0), "url": "/owner#businesses"},
        {"type": "orders", "label": "Pending orders", "count": cards.get("pending_orders", 0), "url": "/owner#commerce"},
        {"type": "flagged", "label": "Flagged accounts", "count": len(flagged), "url": "/owner#businesses"},
        {"type": "stock", "label": "Low-stock products", "count": len(low_stock), "url": "/owner#products"},
    ]
    now = now_iso()
    return api_ok({"data": {"alerts": [{**alert, "timestamp": now} for alert in alerts], "count": sum(int(a["count"] or 0) for a in alerts)}})


@app.get("/api/admin/summary")
def api_admin_summary():
    require_admin()
    is_company_admin = is_company_admin_session()
    db = DBSession()
    try:
        real_products  = db.query(ProductModel).filter_by(is_sample=False).count()
        total_orders   = db.query(OrderModel).count()
        pending_orders = db.query(OrderModel).filter_by(status="Pending").count()
        approved       = db.query(OrderModel).filter_by(status="Approved").all()
        revenue        = sum(float((o.totals or {}).get("total") or 0) for o in approved)
        smtp_ok, smtp_missing = smtp_config_status()
        cards = {
            "products":         real_products,
            "orders":           total_orders,
            "pending_orders":   pending_orders,
            "pending_approvals": pending_orders,
            "approved_revenue": money(revenue),
        }
        if is_company_admin:
            users_count = db.query(UserModel).count()
            pending_businesses = db.query(BusinessProfileModel).filter_by(approval_status="Pending").count()
            cards["users"] = users_count
            cards["pending_approvals"] = pending_orders + pending_businesses
        return api_ok({
            "cards":          cards,
            "company_admin":  is_company_admin,
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
@app.put("/api/admin/products/<product_id>")
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
        if "active" in data: product.is_active = normalize_bool(data["active"])
        if "visible" in data: product.is_active = normalize_bool(data["visible"])
        if "specs"  in data: product.specs    = parse_specs(data["specs"])
        specs = product.specs if isinstance(product.specs, dict) else {}
        flags = specs.get("_owner_flags") if isinstance(specs.get("_owner_flags"), dict) else {}
        if "featured" in data:
            flags["featured"] = normalize_bool(data.get("featured"))
        if "sale_price" in data:
            flags["sale_price"] = str(data.get("sale_price") or "").strip()
            flags["on_sale"] = bool(flags["sale_price"])
        if "on_sale" in data:
            flags["on_sale"] = normalize_bool(data.get("on_sale"))
        if "out_of_stock_label" in data:
            flags["out_of_stock_label"] = normalize_bool(data.get("out_of_stock_label"))
        if flags:
            specs["_owner_flags"] = flags
            product.specs = specs
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
    require_company_admin()
    db = DBSession()
    try:
        users = db.query(UserModel).order_by(UserModel.created_at.desc()).all()
        return api_ok({"users": [user_to_dict(u) for u in users]})
    finally:
        db.close()


@app.get("/api/admin/businesses")
def api_admin_businesses():
    require_company_admin()
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
@app.put("/api/admin/businesses/<business_id>")
def api_admin_update_business(business_id):
    require_company_admin()
    db = DBSession()
    try:
        business = db.query(BusinessProfileModel).filter_by(id=business_id).first()
        user = db.query(UserModel).filter_by(id=business_id).first()
        if not business and not user:
            return api_error("Business not found.", 404)
        
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        if status in {"Pending", "Approved", "Rejected", "Suspended"}:
            if business:
                business.approval_status = status
                business.updated_at = now_utc()
            db.commit()
            
            if user:
                user.status = "Active" if status == "Approved" else status
                user.updated_at = now_utc()
                db.commit()
                
            return api_ok({"message": f"Business {status.lower()}"})
        return api_error("Invalid status")
    finally:
        db.close()


@app.delete("/api/admin/businesses/<business_id>")
def api_admin_delete_business(business_id):
    require_company_admin()
    db = DBSession()
    try:
        business = db.query(BusinessProfileModel).filter_by(id=business_id).first()
        user = db.query(UserModel).filter_by(id=business_id).first()
        if not business and not user:
            return api_error("Business not found.", 404)
        if business:
            db.delete(business)
        if user:
            user.status = "Deleted"
            user.updated_at = now_utc()
        db.commit()
        return api_ok()
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


@app.put("/api/owner/customers/<customer_id>")
def api_owner_update_customer(customer_id):
    require_owner()
    data = request.get_json(silent=True) or {}
    db = DBSession()
    try:
        user = db.query(UserModel).filter_by(id=customer_id).first()
        if not user or (user.account_type or "B2C") == "B2B":
            return api_error("Customer not found.", 404)
        if "banned" in data:
            user.status = "Banned" if normalize_bool(data.get("banned")) else "Active"
        elif "status" in data:
            user.status = str(data.get("status") or "Active")
        user.updated_at = now_utc()
        db.commit()
        return api_ok({"data": user_to_dict(user), "customer": user_to_dict(user)})
    finally:
        db.close()


@app.delete("/api/owner/customers/<customer_id>")
def api_owner_delete_customer(customer_id):
    require_owner()
    db = DBSession()
    try:
        user = db.query(UserModel).filter_by(id=customer_id).first()
        if not user or (user.account_type or "B2C") == "B2B":
            return api_error("Customer not found.", 404)
        if user.is_admin:
            return api_error("Admin accounts cannot be deleted.", 403)
        user.status = "Deleted"
        user.updated_at = now_utc()
        db.commit()
        return api_ok()
    finally:
        db.close()


@app.post("/api/owner/businesses/bulk-action")
def api_owner_business_bulk_action():
    require_owner()
    data = request.get_json(silent=True) or {}
    ids = [str(item) for item in (data.get("ids") or [])]
    action = data.get("action")
    if action not in {"suspend", "delete", "clear_flag"}:
        return api_error("Invalid bulk action.")
    db = DBSession()
    try:
        changed = 0
        for business_id in ids:
            business = db.query(BusinessProfileModel).filter_by(id=business_id).first()
            user = db.query(UserModel).filter_by(id=business_id).first()
            if action == "delete":
                if business:
                    db.delete(business)
                if user:
                    user.status = "Deleted"
                    changed += 1
            elif action == "suspend":
                if business:
                    business.approval_status = "Suspended"
                if user:
                    user.status = "Suspended"
                    changed += 1
            elif action == "clear_flag":
                if business and business.approval_status == "Suspended":
                    business.approval_status = "Pending"
                if user and user.status == "Suspended":
                    user.status = "Pending"
                changed += 1
        db.commit()
        return api_ok({"data": {"changed": changed}})
    finally:
        db.close()


@app.post("/api/owner/send-email")
def api_owner_send_email():
    require_owner()
    data = request.get_json(silent=True) or {}
    to_email = normalize_email(data.get("to"))
    subject = (data.get("subject") or "Microchip Cart update").strip()
    message = (data.get("message") or "").strip()
    if not to_email or not message:
        return api_error("Recipient and message are required.")
    smtp_ok, missing = smtp_config_status()
    if not smtp_ok:
        return api_ok({"data": {"sent": False, "mailto": f"mailto:{to_email}?subject={quote(subject)}&body={quote(message)}", "missing": missing}})
    try:
        host, username, password, sender, sender_name, port, use_ssl, use_tls, timeout = smtp_config()
        email = EmailMessage()
        email["From"] = formataddr((sender_name, sender))
        email["To"] = to_email
        email["Subject"] = subject
        email["Date"] = formatdate(localtime=True)
        email.set_content(message)
        context = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, int(port), timeout=timeout, context=context) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(email)
        else:
            with smtplib.SMTP(host, int(port), timeout=timeout) as smtp:
                if use_tls:
                    smtp.starttls(context=context)
                if username:
                    smtp.login(username, password)
                smtp.send_message(email)
        return api_ok({"data": {"sent": True}})
    except Exception as exc:
        return api_error(f"Email send failed: {exc}", 502)


@app.get("/api/owner/insights/revenue")
def api_owner_insights_revenue():
    require_owner()
    period = request.args.get("period", "30d")
    days = 7 if period == "7d" else 90 if period == "90d" else 30
    start = now_utc() - timedelta(days=days - 1)
    db = DBSession()
    try:
        orders = db.query(OrderModel).filter(OrderModel.created_at >= start).all()
        buckets = {}
        for i in range(days):
            key = (start + timedelta(days=i)).date().isoformat()
            buckets[key] = 0
        for order in orders:
            key = (order.created_at or now_utc()).date().isoformat()
            buckets[key] = buckets.get(key, 0) + money((order.totals or {}).get("total"))
        rows = [{"date": key, "revenue": value} for key, value in buckets.items()]
        payload = owner_overview_payload()
        top_distributors = sorted(payload.get("businesses", []), key=lambda row: row.get("spend", 0), reverse=True)[:8]
        return api_ok({"data": {"revenue": rows, "top_distributors": top_distributors, "events": payload.get("events", [])[:20]}})
    finally:
        db.close()


@app.get("/api/owner/sessions")
def api_owner_sessions():
    require_owner()
    return api_ok({"data": [{"admin": OWNER_EMAIL, "ip": client_ip(), "since": session.get("owner_login_at") or "", "current": True}]})


@app.post("/api/owner/change-password")
def api_owner_change_password():
    require_owner()
    return api_error("Owner password is managed by environment variables on this deployment.", 400)


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
    require_company_admin()
    db = DBSession()
    try:
        row = db.query(SettingsModel).filter_by(key="store").first()
        return api_ok({"settings": row.value if row else {}})
    finally:
        db.close()


@app.put("/api/admin/settings")
def api_admin_update_settings():
    require_company_admin()
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

@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        if request.path.startswith("/api/"):
            return api_error(error.description or error.name, error.code or 500)
        return error
    print(f"Unhandled error: {error}")
    if request.path.startswith("/api/"):
        return api_error("Server error. Please refresh and try again.", 500)
    raise error


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
