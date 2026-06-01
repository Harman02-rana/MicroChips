## database.py

import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Boolean,
    Numeric,
    Integer,
    DateTime,
    Text,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")


def clean_env(value):
    return (value or "").strip().strip('"').strip("'")


def build_database_url():
    database_url = clean_env(os.getenv("DATABASE_URL"))

    if database_url:
        return database_url

    host = clean_env(os.getenv("SUPABASE_DB_HOST"))
    port = clean_env(os.getenv("SUPABASE_DB_PORT")) or "5432"
    dbname = clean_env(os.getenv("SUPABASE_DB_NAME")) or "postgres"
    user = clean_env(os.getenv("SUPABASE_DB_USER")) or "postgres"
    password = clean_env(os.getenv("SUPABASE_DB_PASSWORD"))

    if not password:
        raise RuntimeError(
            "SUPABASE_DB_PASSWORD not found in .env"
        )

    return (
        f"postgresql://{quote(user)}:"
        f"{quote(password, safe='')}"
        f"@{host}:{port}/{dbname}"
        f"?sslmode=require"
    )


DATABASE_URL = build_database_url()

print("Database URL Loaded Successfully")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    connect_args={"connect_timeout": 10},
)

Session = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass

# --- Models ---

class User(Base):
    __tablename__ = "users"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email         = Column(String(255), unique=True, nullable=False)
    phone         = Column(String(20), unique=True)
    password_hash = Column(Text, nullable=True)
    full_name     = Column(String(255))
    is_admin      = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Product(Base):
    __tablename__ = "products"
    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        = Column(String(255), nullable=False)
    slug        = Column(String(255), unique=True, nullable=False)
    description = Column(Text)
    price       = Column(Numeric(10, 2), nullable=False)
    stock       = Column(Integer, default=0)
    image_url   = Column(Text)
    specs       = Column(JSON)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Order(Base):
    __tablename__ = "orders"
    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(UUID(as_uuid=True))
    status         = Column(String(50), default="pending")
    total          = Column(Numeric(10, 2), nullable=False)
    items          = Column(JSON, nullable=False)
    shipping_address = Column(JSON)
    invoice_number = Column(String(50))
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Review(Base):
    __tablename__ = "reviews"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True))
    user_id    = Column(UUID(as_uuid=True))
    rating     = Column(Integer)
    comment    = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def get_db():
    """Call this inside every route that needs DB access."""
    db = Session()
    try:
        yield db
    finally:
        db.close()
