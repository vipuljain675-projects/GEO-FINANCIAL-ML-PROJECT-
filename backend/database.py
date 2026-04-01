import os
import sqlite3
from typing import Generator

import certifi
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)


MONGODB_URI = (os.getenv("MONGODB_URI") or "").strip() or None
DATABASE_URL = (os.getenv("DATABASE_URL", "sqlite:///./strategic_shield.db") or "").strip()

_client = None
_db = None


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _sqlite_path() -> str:
    if DATABASE_URL.startswith("sqlite:///./"):
        return os.path.join(_project_root(), DATABASE_URL.replace("sqlite:///./", "", 1))
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.replace("sqlite:///", "/", 1)
    return os.path.join(_project_root(), "strategic_shield.db")


def get_client() -> MongoClient:
    global _client
    if _client is None:
        if not MONGODB_URI:
            raise RuntimeError("MONGODB_URI is not configured")
        _client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
    return _client


def get_database():
    global _db
    if _db is None:
        client = get_client()
        _db = client.get_default_database()
        if _db is None:
            _db = client["strategic_shield"]
    return _db


def ensure_indexes(db=None) -> None:
    if db is None:
        db = get_database()
    db["users"].create_index("email", unique=True)
    db["portfolios"].create_index([("user_id", ASCENDING), ("ticker", ASCENDING)], unique=True)
    db["live_event_cache"].create_index("cache_key", unique=True)
    db["live_event_cache"].create_index("fetched_at")


def migrate_sqlite_to_mongo(db=None) -> dict:
    if db is None:
        db = get_database()
    sqlite_path = _sqlite_path()
    if not os.path.exists(sqlite_path):
        return {"migrated": False, "reason": "sqlite_missing"}

    if db["users"].count_documents({}) > 0 or db["portfolios"].count_documents({}) > 0:
        return {"migrated": False, "reason": "mongo_already_populated"}

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        user_rows = conn.execute("SELECT id, email, hashed_password, full_name FROM users").fetchall()
        portfolio_rows = conn.execute(
            "SELECT ticker, quantity, purchase_price, purchase_date, user_id FROM portfolios"
        ).fetchall()
    finally:
        conn.close()

    if not user_rows and not portfolio_rows:
        return {"migrated": False, "reason": "sqlite_empty"}

    id_map = {}
    inserted_users = 0
    inserted_portfolios = 0

    for row in user_rows:
        payload = {
            "email": row["email"],
            "hashed_password": row["hashed_password"],
            "full_name": row["full_name"] or row["email"].split("@")[0],
            "legacy_sqlite_id": row["id"],
        }
        result = db["users"].update_one({"email": payload["email"]}, {"$set": payload}, upsert=True)
        user_doc = db["users"].find_one({"email": payload["email"]}, {"_id": 1})
        id_map[row["id"]] = str(user_doc["_id"])
        if result.upserted_id is not None:
            inserted_users += 1

    for row in portfolio_rows:
        mapped_user_id = id_map.get(row["user_id"])
        if not mapped_user_id:
            continue
        payload = {
            "user_id": mapped_user_id,
            "ticker": (row["ticker"] or "").upper(),
            "quantity": float(row["quantity"] or 0),
            "purchase_price": float(row["purchase_price"]) if row["purchase_price"] is not None else None,
            "purchase_date": row["purchase_date"],
            "legacy_sqlite_user_id": row["user_id"],
        }
        result = db["portfolios"].update_one(
            {"user_id": mapped_user_id, "ticker": payload["ticker"]},
            {"$set": payload},
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted_portfolios += 1

    return {
        "migrated": True,
        "users": inserted_users,
        "portfolios": inserted_portfolios,
    }


def initialize_database():
    db = get_database()
    ensure_indexes(db)
    migrate_sqlite_to_mongo(db)
    return db


def get_db() -> Generator:
    yield get_database()
