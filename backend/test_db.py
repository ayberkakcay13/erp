"""Minimal Supabase PostgreSQL connection test."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).with_name(".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env")
    sys.exit(1)

try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        now = conn.execute(text("SELECT NOW()")).scalar()
    print("✅ Connection successful!")
    print(f"Current time from Supabase: {now}")
except Exception as exc:
    print("❌ Connection failed!")
    print(f"Error: {exc}")
    sys.exit(1)
