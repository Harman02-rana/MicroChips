import json
import os
import re
import secrets
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
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
from supabase import create_client, Client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client | None = None
if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)


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
        raise RuntimeError(
            "Database is not configured. Set either DATABASE_URL with the real password "
            "or set SUPABASE_DB_PASSWORD in .env."
        )

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
LOCAL_DATABASE_URL = f"sqlite:///{(Path(__file__).resolve().parent / 'instance' / 'local_store.sqlite3').as_posix()}"
DATABASE_LABEL = "postgresql"


def create_app_engine(database_url):
    if database_url.startswith("sqlite"):
        Path(__file__).resolve().parent.joinpath("instance").mkdir(exist_ok=True)
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
    password_hash  = Column(Text, nullable=False)
    name           = Column(String(255), nullable=True)
    account_type   = Column(String(10), default="B2C")
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
    category   = Column(String(50), default="General") # Problem, Experience, Project, General
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
    ]
    with engine.begin() as connection:
        for statement in ddl_statements:
            try:
                connection.execute(text(statement))
            except SQLAlchemyError:
                pass


def initialize_database():
    global engine, DBSession, DATABASE_LABEL
    try:
        Base.metadata.create_all(engine)
        ensure_compatible_schema()
        ensure_sqlite_schema()
    except SQLAlchemyError:
        if os.getenv("APP_ENV") == "production":
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
OWNER_EMAIL              = (os.getenv("OWNER_EMAIL", ADMIN_EMAIL)).strip().lower()
OWNER_PASSWORD           = os.getenv("OWNER_PASSWORD", ADMIN_PASSWORD)
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
        return {k: u.get(k) for k in ("id", "name", "email", "phone", "account_type", "company_name", "gstin", "created_at")}
    return {
        "id":           str_id(u.id),
        "name":         u.name or "",
        "email":        u.email,
        "phone":        u.phone or "",
        "account_type": u.account_type or "B2C",
        "company_name": u.company_name or "",
        "gstin":        u.gstin or "",
        "created_at":   u.created_at.isoformat() if u.created_at else "",
    }

def auth_redirect_url(user):
    return url_for("admin_page") if (user.account_type or "B2C") == "B2B" else "/"

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

def post_to_dict(p: CommunityPostModel, db) -> dict:
    reply_count = db.query(CommunityReplyModel).filter_by(post_id=p.id).count()
    return {
        "id":         str_id(p.id),
        "user_id":    str_id(p.user_id),
        "user_name":  p.user_name or "Anonymous",
        "title":      p.title,
        "content":    p.content,
        "category":   p.category or "General",
        "likes":      p.likes or 0,
        "liked_by":   p.liked_by or [],
        "reply_count": reply_count,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }

def reply_to_dict(r: CommunityReplyModel) -> dict:
    return {
        "id":         str_id(r.id),
        "post_id":    str_id(r.post_id),
        "user_id":    str_id(r.user_id),
        "user_name":  r.user_name or "Anonymous",
        "content":    r.content,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


# ── Session / auth helpers ────────────────────────────────────────────────────

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = DBSession()
    try:
        return db.query(UserModel).filter_by(id=user_id).first()
    finally:
        db.close()

def require_user():
    user = current_user()
    if not user:
        abort(make_response(api_error("Please login first.", 401)[0], 401))
    return user

def require_admin():
    if not session.get("admin_logged_in"):
        abort(make_response(api_error("Admin login required.", 401)[0], 401))

def require_owner():
    if not session.get("owner_logged_in"):
        abort(make_response(api_error("Owner login required.", 401)[0], 401))


# ── Response helpers ──────────────────────────────────────────────────────────

def api_ok(payload=None, status=200):
    return jsonify({"ok": True, **(payload or {})}), status

def api_error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


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
        products = db.query(ProductModel).all()
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
        products = db.query(ProductModel).order_by(ProductModel.created_at.desc()).all()
        orders = db.query(OrderModel).order_by(OrderModel.created_at.desc()).all()
        events = db.query(EventModel).order_by(EventModel.created_at.desc()).limit(120).all()
        analytics = analytics_payload()

        customers = [u for u in users if (u.account_type or "B2C") != "B2B"]
        businesses = [u for u in users if (u.account_type or "B2C") == "B2B"]

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
            business_rows.append({
                **user_to_dict(user),
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
                "announcement": "Precision components, clear specs, fast order approval.",
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
    return render_template("admin.html", store_mode=DATABASE_LABEL, admin_email=ADMIN_EMAIL)

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
    if not session.get("owner_logged_in"):
        return redirect(url_for("owner_login_page"))
    return render_template("owner_admin.html", store_mode=DATABASE_LABEL, owner_email=OWNER_EMAIL)

@app.get("/owner/login")
def owner_login_page():
    if session.get("owner_logged_in"):
        return redirect(url_for("owner_page"))
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
    data       = request.get_json(silent=True) or {}
    name       = (data.get("name") or "").strip()
    email      = normalize_email(data.get("email"))
    phone      = (data.get("phone") or "").strip()
    password   = data.get("password") or ""
    account_type = normalize_account_type(data.get("account_type"))
    company_name = (data.get("company_name") or "").strip()
    gstin = (data.get("gstin") or "").strip()

    business_address = (data.get("business_address") or "").strip()

    if not name or not email or not password:
        return api_error("Name, email and password are required.")
    if len(password) < 6:
        return api_error("Password must be at least 6 characters.")
    if account_type == "B2B":
        if not company_name:
            return api_error("Business Name is required for business accounts.")
        if not phone:
            return api_error("Contact Number is required for business accounts.")
        if not business_address:
            return api_error("Business Address is required for business accounts.")
        if not gstin or not re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", gstin):
            return api_error("Invalid GST format. Please enter a valid 15-character GSTIN.")
        
        otp = (data.get("otp") or "").strip()
        if not otp or phone_otps.get(phone) != otp:
            return api_error("Invalid or missing phone OTP.")
        phone_otps.pop(phone, None)

    db = DBSession()
    try:
        if db.query(UserModel).filter_by(email=email).first():
            return api_error("This email already has an account.")
        if phone and db.query(UserModel).filter_by(phone=phone).first():
            return api_error("This phone number is already registered.")

        user_id = None
        if supabase:
            # Use Supabase Auth
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "name": name,
                        "account_type": account_type
                    }
                }
            })
            if not auth_response.user:
                return api_error("Failed to sign up with Supabase.")
            user_id = auth_response.user.id

        user = UserModel(
            id             = user_id if user_id else uuid.uuid4(),
            email          = email,
            phone          = phone or None,
            password_hash  = generate_password_hash(password),
            name           = name,
            account_type   = account_type,
            company_name   = company_name if account_type == "B2B" else None,
            gstin          = gstin if account_type == "B2B" else None,
            email_verified = False,
            phone_verified = bool(phone) and account_type == "B2B",
            last_login     = now_utc(),
        )
        db.add(user)
        if account_type == "B2B":
            business = BusinessProfileModel(
                id               = user.id,
                business_name    = company_name,
                business_address = business_address,
                contact_number   = phone,
                gst_number       = gstin,
                approval_status  = "Pending"
            )
            db.add(business)
        db.commit()
        db.refresh(user)
        session["user_id"] = str_id(user.id)
        if (user.account_type or "B2C") == "B2B":
            session["admin_logged_in"] = True
        else:
            session.pop("admin_logged_in", None)
        return api_ok({"user": public_user(user), "redirect_url": auth_redirect_url(user)}, 201)
    except Exception as e:
        db.rollback()
        return api_error(f"Error during signup: {str(e)}", 409)
    finally:
        db.close()


@app.post("/api/auth/login")
def api_login_direct():
    """Password login for customer and business accounts."""
    data     = request.get_json(silent=True) or {}
    email    = normalize_email(data.get("email"))
    password = data.get("password") or ""
    account_type = normalize_account_type(data.get("account_type"))
    db = DBSession()
    try:
        if supabase:
            try:
                auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if not auth_response.user:
                    return api_error("Invalid email or password.", 401)
            except Exception:
                return api_error("Invalid email or password.", 401)

        user = db.query(UserModel).filter_by(email=email).first()
        if not user:
            return api_error("Invalid email or password.", 401)
            
        if not supabase and not check_password_hash(user.password_hash, password):
            return api_error("Invalid email or password.", 401)

        if (user.account_type or "B2C") != account_type:
            return api_error(f"This email is registered as {(user.account_type or 'B2C')}. Switch portal and try again.", 401)
        
        if account_type == "B2B":
            business = db.query(BusinessProfileModel).filter_by(id=user.id).first()
            if business and business.approval_status != "Approved":
                return api_error("Your business account is pending approval.", 403)

        user.last_login = now_utc()
        db.commit()
        db.refresh(user)
        session["user_id"] = str_id(user.id)
        if (user.account_type or "B2C") == "B2B":
            session["admin_logged_in"] = True
        else:
            session.pop("admin_logged_in", None)
        return api_ok({"user": public_user(user), "redirect_url": auth_redirect_url(user)})
    finally:
        db.close()


@app.post("/api/auth/logout")
def api_logout():
    session.pop("user_id", None)
    session.pop("admin_logged_in", None)
    return api_ok()


@app.get("/api/auth/me")
def api_me():
    return api_ok({"user": public_user(current_user())})


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

    if len(new_password) < 6:
        return api_error("Password must be at least 6 characters.")
    if new_password != confirm_password:
        return api_error("New passwords do not match.")
    if not check_password_hash(user.password_hash, current_password):
        return api_error("Current password is incorrect.", 401)

    db = DBSession()
    try:
        row = db.query(UserModel).filter_by(id=user.id).first()
        if not row:
            return api_error("User not found.", 404)
        row.password_hash = generate_password_hash(new_password)
        row.updated_at = now_utc()
        db.commit()
        return api_ok({"message": "Password changed."})
    finally:
        db.close()


@app.delete("/api/auth/me")
def api_delete_me():
    user = require_user()
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    confirm = (data.get("confirm") or "").strip()

    if confirm != "DELETE":
        return api_error("Type DELETE to confirm account deletion.")
    if not check_password_hash(user.password_hash, password):
        return api_error("Password is incorrect.", 401)

    db = DBSession()
    try:
        row = db.query(UserModel).filter_by(id=user.id).first()
        if row:
            db.delete(row)
            db.commit()
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
    db = DBSession()
    try:
        product = db.query(ProductModel).filter_by(id=product_id, is_active=True).first()
        if not product:
            return api_error("Product not found.", 404)
        # Track view
        product.views = (product.views or 0) + 1
        db.add(EventModel(type="view", product_id=product.id,
                          user_id=session.get("user_id")))
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
    category = (data.get("category") or "General").strip()
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


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Events
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/events")
def api_event():
    data       = request.get_json(silent=True) or {}
    event_type = data.get("type")
    if event_type not in {"view", "cart_add", "checkout_open", "payment_selected"}:
        return api_error("Unsupported event type.")
    db = DBSession()
    try:
        product_id = data.get("product_id")
        event = EventModel(
            type       = event_type,
            product_id = product_id,
            user_id    = session.get("user_id"),
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

@app.post("/api/orders")
def api_create_order():
    user = require_user()
    data = request.get_json(silent=True) or {}
    raw_items = data.get("items") or []
    if not raw_items:
        return api_error("Cart is empty.")

    db = DBSession()
    try:
        items = []
        for entry in raw_items:
            pid      = entry.get("product_id") or entry.get("id")
            quantity = max(1, int(entry.get("quantity") or 1))
            product  = db.query(ProductModel).filter_by(id=pid, is_active=True).first()
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
        return api_ok()
    return api_error("Invalid admin credentials.", 401)


@app.post("/api/admin/logout")
def api_admin_logout():
    session.pop("admin_logged_in", None)
    return api_ok()

@app.post("/api/owner/login")
def api_owner_login():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email"))
    password = data.get("password") or ""
    if email == OWNER_EMAIL and password == OWNER_PASSWORD:
        session["owner_logged_in"] = True
        return api_ok({"redirect_url": url_for("owner_page")})
    return api_error("Invalid owner credentials.", 401)

@app.post("/api/owner/logout")
def api_owner_logout():
    session.pop("owner_logged_in", None)
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
        approved       = db.query(OrderModel).filter_by(status="Approved").all()
        revenue        = sum(float((o.totals or {}).get("total") or 0) for o in approved)
        smtp_ok, smtp_missing = smtp_config_status()
        return api_ok({
            "cards": {
                "users":            users_count,
                "products":         real_products,
                "orders":           total_orders,
                "pending_orders":   pending_orders,
                "approved_revenue": money(revenue),
                "sample_mode":      real_products == 0,
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
        products = db.query(ProductModel).order_by(ProductModel.created_at.desc()).all()
        return api_ok({
            "products":   [product_to_dict(p) for p in products],
            "next_image": next_product_image_path(),
        })
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
        if not business:
            return api_error("Business not found.", 404)
        
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        if status in {"Pending", "Approved", "Rejected"}:
            business.approval_status = status
            db.commit()
            
            # Optionally sync back to UserModel if you want
            user = db.query(UserModel).filter_by(id=business.id).first()
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
        updated = {
            **current,
            "store_name":   (data.get("store_name") or current.get("store_name") or "Microchip Cart").strip(),
            "support_email": normalize_email(data.get("support_email") or current.get("support_email") or ADMIN_NOTIFICATION_EMAIL),
            "announcement": (data.get("announcement") or current.get("announcement") or "").strip(),
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
    app.run(
        debug  = os.getenv("APP_ENV") != "production",
        host   = "127.0.0.1",
        port   = int(os.getenv("PORT", "5000")),
        use_reloader=False,
    )
