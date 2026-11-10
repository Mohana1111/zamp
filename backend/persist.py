"""
Database Persistence Layer for AP Data Files.

Supports:
1. MongoDB Atlas (Primary) via env MONGODB_URI (optional MONGODB_DB, default 'zamp_ap').
   Collection: `kv_files` with {_id: path, content: Binary, updated_at: datetime}.
2. PostgreSQL (Secondary fallback) via env DATABASE_URL.
   Table: `kv_files` with (path TEXT PRIMARY KEY, content BYTEA, updated_at TIMESTAMP).
3. Local filesystem (Default fallback if neither is set).

Priority: MONGODB_URI > DATABASE_URL > local.
Lifecycle:
- On startup: Restores data files into backend/data. If database is empty on first boot, seeds it.
- Background worker: Every ~3 seconds, snapshots changed files using SHA-256 hash comparison.
- On shutdown: Flushes pending changes immediately.
- Resilience: Short timeouts (2000ms), down database never blocks startup or crashes the app.
"""

import os
import time
import logging
import hashlib
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("clearpay.persist")

DATA_DIR = Path(__file__).resolve().parent / "data"

# Global state
_PERSISTENCE_MODE: str = "local"  # "database" | "local"
_ACTIVE_BACKEND: str = "local"     # "mongodb" | "postgres" | "local"
_LAST_SAVED_HASHES: Dict[str, str] = {}
_STOP_EVENT = threading.Event()
_BACKGROUND_THREAD: Optional[threading.Thread] = None

# Custom test fixtures
_CUSTOM_MONGO_COLL = None
_CUSTOM_PG_CONN_FACTORY = None


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file on disk."""
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def get_tracked_files() -> List[Path]:
    """
    Returns list of files in backend/data to persist:
    - Root .json and .csv files
    - Uploads in data/uploads
    - Invoices in data/sample_invoices
    - Files in data/downloads
    """
    tracked: List[Path] = []
    if not DATA_DIR.exists():
        return tracked

    for p in DATA_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in [".json", ".csv"]:
            tracked.append(p)

    for sub in ["uploads", "sample_invoices", "downloads"]:
        subdir = DATA_DIR / sub
        if subdir.exists() and subdir.is_dir():
            for p in subdir.iterdir():
                if p.is_file() and not p.name.startswith("."):
                    tracked.append(p)

    return tracked


# ===========================================================================
# MongoDB Atlas Implementation (Primary)
# ===========================================================================

def _get_mongo_collection(uri: Optional[str] = None):
    """Establishes or returns MongoDB collection with short timeout."""
    global _CUSTOM_MONGO_COLL
    if _CUSTOM_MONGO_COLL is not None:
        return _CUSTOM_MONGO_COLL

    mongo_uri = (uri or os.getenv("MONGODB_URI", "")).strip()
    if not mongo_uri:
        return None

    try:
        from pymongo import MongoClient
        db_name = os.getenv("MONGODB_DB", "zamp_ap").strip() or "zamp_ap"
        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
            socketTimeoutMS=5000,
        )
        client.admin.command("ping")
        return client[db_name]["kv_files"]
    except Exception as e:
        logger.warning(f"MongoDB connection failed: {e}")
        try:
            client.close()
        except Exception:
            pass
        return None



def restore_from_mongo(coll) -> int:
    """Restores all files from MongoDB `kv_files` collection to disk."""
    global _LAST_SAVED_HASHES
    count = 0
    try:
        cursor = coll.find({})
        for doc in cursor:
            path_str = doc["_id"]
            content = doc.get("content")
            if content is None:
                continue

            bytes_data = bytes(content) if isinstance(content, (bytes, bytearray, memoryview)) else content.encode("utf-8")
            target_path = DATA_DIR / path_str
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "wb") as f:
                f.write(bytes_data)

            _LAST_SAVED_HASHES[path_str] = hashlib.sha256(bytes_data).hexdigest()
            count += 1

        logger.info(f"Restored {count} files from MongoDB persistence.")
        return count
    except Exception as e:
        logger.warning(f"Error restoring files from MongoDB: {e}")
        return 0


def seed_to_mongo(coll) -> int:
    """Seeds MongoDB `kv_files` collection from shipped local files on first boot."""
    global _LAST_SAVED_HASHES
    from bson import Binary
    count = 0
    files = get_tracked_files()

    try:
        for fpath in files:
            rel_path = str(fpath.relative_to(DATA_DIR)).replace("\\", "/")
            with open(fpath, "rb") as f:
                content = f.read()

            f_hash = hashlib.sha256(content).hexdigest()
            now_dt = datetime.now(timezone.utc)
            coll.replace_one(
                {"_id": rel_path},
                {"_id": rel_path, "content": Binary(content), "updated_at": now_dt},
                upsert=True,
            )
            _LAST_SAVED_HASHES[rel_path] = f_hash
            count += 1

        logger.info(f"Seeded {count} initial files into MongoDB persistence.")
        return count
    except Exception as e:
        logger.warning(f"Error seeding MongoDB from local files: {e}")
        return 0


def flush_to_mongo(coll=None) -> int:
    """Scans tracked files on disk. Upserts changed files (by SHA-256) to MongoDB."""
    global _LAST_SAVED_HASHES
    from bson import Binary
    if coll is None:
        coll = _get_mongo_collection()
        if coll is None:
            return 0

    saved_count = 0
    files = get_tracked_files()

    try:
        for fpath in files:
            if not fpath.exists():
                continue
            rel_path = str(fpath.relative_to(DATA_DIR)).replace("\\", "/")
            current_hash = compute_file_sha256(fpath)

            if current_hash and current_hash != _LAST_SAVED_HASHES.get(rel_path):
                with open(fpath, "rb") as f:
                    content = f.read()
                now_dt = datetime.now(timezone.utc)
                coll.replace_one(
                    {"_id": rel_path},
                    {"_id": rel_path, "content": Binary(content), "updated_at": now_dt},
                    upsert=True,
                )
                _LAST_SAVED_HASHES[rel_path] = current_hash
                saved_count += 1

        if saved_count > 0:
            logger.debug(f"Flushed {saved_count} updated files to MongoDB.")
        return saved_count
    except Exception as e:
        logger.warning(f"Error flushing files to MongoDB: {e}")
        return 0


# ===========================================================================
# PostgreSQL Implementation (Secondary Fallback)
# ===========================================================================

def _clean_database_url(url: str) -> str:
    """Normalizes Postgres URL schemes and SSL parameters."""
    if not url:
        return ""
    clean = url.strip()
    if clean.startswith("postgres://"):
        clean = "postgresql://" + clean[len("postgres://"):]
    if "sslmode" not in clean and not any(local_host in clean for local_host in ["localhost", "127.0.0.1"]):
        separator = "&" if "?" in clean else "?"
        clean = f"{clean}{separator}sslmode=require"
    return clean


def _get_pg_connection(db_url: Optional[str] = None):
    """Establishes a connection using psycopg2 or test connection factory."""
    global _CUSTOM_PG_CONN_FACTORY
    if _CUSTOM_PG_CONN_FACTORY is not None:
        return _CUSTOM_PG_CONN_FACTORY()

    url = _clean_database_url(db_url or os.getenv("DATABASE_URL", ""))
    if not url:
        return None

    import psycopg2
    return psycopg2.connect(url, connect_timeout=5)


def _exec(cur, sql: str, params=None):
    """Executes SQL query, automatically translating dialect if running with SQLite test adapter."""
    try:
        conn = cur.connection
        is_sqlite = "sqlite" in type(conn).__module__.lower() or "sqlite" in type(conn).__name__.lower()
    except Exception:
        is_sqlite = False

    if is_sqlite:
        sql = sql.replace("%s", "?").replace("BYTEA NOT NULL", "BLOB NOT NULL").replace("NOW()", "CURRENT_TIMESTAMP")

    if params is not None:
        return cur.execute(sql, params)
    return cur.execute(sql)


def init_pg_schema(conn) -> bool:
    """Creates the kv_files table if not exists."""
    cur = conn.cursor()
    try:
        _exec(cur, """
            CREATE TABLE IF NOT EXISTS kv_files (
                path TEXT PRIMARY KEY,
                content BYTEA NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Error initializing kv_files schema: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            cur.close()
        except Exception:
            pass


def restore_from_pg(conn) -> int:
    """Restores files from Postgres kv_files table to disk."""
    global _LAST_SAVED_HASHES
    count = 0
    cur = conn.cursor()
    try:
        _exec(cur, "SELECT path, content FROM kv_files;")
        rows = cur.fetchall()

        if not rows:
            return 0

        for path_str, content in rows:
            target_path = DATA_DIR / path_str
            target_path.parent.mkdir(parents=True, exist_ok=True)
            bytes_data = bytes(content) if isinstance(content, (bytes, bytearray, memoryview)) else content.encode("utf-8")
            with open(target_path, "wb") as f:
                f.write(bytes_data)

            _LAST_SAVED_HASHES[path_str] = hashlib.sha256(bytes_data).hexdigest()
            count += 1

        logger.info(f"Restored {count} files from PostgreSQL persistence.")
        return count
    except Exception as e:
        logger.warning(f"Error restoring files from PostgreSQL: {e}")
        return 0
    finally:
        try:
            cur.close()
        except Exception:
            pass


def seed_to_pg(conn) -> int:
    """Seeds Postgres kv_files table from shipped local files on first boot."""
    global _LAST_SAVED_HASHES
    count = 0
    files = get_tracked_files()
    cur = conn.cursor()

    try:
        for fpath in files:
            rel_path = str(fpath.relative_to(DATA_DIR)).replace("\\", "/")
            with open(fpath, "rb") as f:
                content = f.read()

            f_hash = hashlib.sha256(content).hexdigest()
            _exec(cur, """
                INSERT INTO kv_files (path, content, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (path) DO UPDATE
                SET content = EXCLUDED.content, updated_at = NOW();
            """, (rel_path, content))
            _LAST_SAVED_HASHES[rel_path] = f_hash
            count += 1
        conn.commit()
        logger.info(f"Seeded {count} initial files into PostgreSQL persistence.")
        return count
    except Exception as e:
        logger.warning(f"Error seeding PostgreSQL from local files: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        try:
            cur.close()
        except Exception:
            pass


def flush_to_pg(conn=None) -> int:
    """Scans tracked files on disk. Upserts changed files (by SHA-256) to Postgres."""
    global _LAST_SAVED_HASHES
    own_conn = False
    if conn is None:
        try:
            conn = _get_pg_connection()
            if not conn:
                return 0
            own_conn = True
        except Exception as e:
            logger.warning(f"Cannot establish connection for flush: {e}")
            return 0

    saved_count = 0
    files = get_tracked_files()
    cur = conn.cursor()

    try:
        for fpath in files:
            if not fpath.exists():
                continue
            rel_path = str(fpath.relative_to(DATA_DIR)).replace("\\", "/")
            current_hash = compute_file_sha256(fpath)

            if current_hash and current_hash != _LAST_SAVED_HASHES.get(rel_path):
                with open(fpath, "rb") as f:
                    content = f.read()
                _exec(cur, """
                    INSERT INTO kv_files (path, content, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (path) DO UPDATE
                    SET content = EXCLUDED.content, updated_at = NOW();
                """, (rel_path, content))
                _LAST_SAVED_HASHES[rel_path] = current_hash
                saved_count += 1

        conn.commit()
        if saved_count > 0:
            logger.debug(f"Flushed {saved_count} updated files to PostgreSQL.")
        return saved_count
    except Exception as e:
        logger.warning(f"Error flushing files to PostgreSQL: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        try:
            cur.close()
        except Exception:
            pass
        if own_conn and conn:
            try:
                conn.close()
            except Exception:
                pass


# ===========================================================================
# Background Sync & Unified Lifecycle Controller
# ===========================================================================

def flush_all_pending() -> int:
    """Flushes changes to the currently active database backend."""
    if _ACTIVE_BACKEND == "mongodb":
        return flush_to_mongo()
    elif _ACTIVE_BACKEND == "postgres":
        return flush_to_pg()
    return 0


def _sync_loop(interval_sec: float = 3.0):
    """Continuous background worker that flushes changes every ~3s."""
    while not _STOP_EVENT.is_set():
        try:
            flush_all_pending()
        except Exception as e:
            logger.warning(f"Persistence background sync warning: {e}")
        _STOP_EVENT.wait(interval_sec)


def start_persistence(mongo_uri: Optional[str] = None, pg_url: Optional[str] = None):
    """
    Initializes persistence layer on application startup with strict priority:
    1. MongoDB Atlas (MONGODB_URI)
    2. PostgreSQL (DATABASE_URL)
    3. Local filesystem fallback
    """
    global _PERSISTENCE_MODE, _ACTIVE_BACKEND, _BACKGROUND_THREAD, _STOP_EVENT

    _STOP_EVENT.clear()

    # Priority 1: MongoDB Atlas
    m_uri = mongo_uri or os.getenv("MONGODB_URI", "").strip()
    if m_uri or _CUSTOM_MONGO_COLL is not None:
        try:
            coll = _get_mongo_collection(m_uri)
            if coll is not None:
                doc_count = coll.count_documents({})
                if doc_count > 0:
                    restore_from_mongo(coll)
                else:
                    seed_to_mongo(coll)

                _ACTIVE_BACKEND = "mongodb"
                _PERSISTENCE_MODE = "database"

                _BACKGROUND_THREAD = threading.Thread(target=_sync_loop, daemon=True, name="mongo-persist-worker")
                _BACKGROUND_THREAD.start()
                logger.info("MongoDB Atlas persistence successfully initialized.")
                return
        except Exception as e:
            logger.warning(f"Failed to start MongoDB persistence (attempting secondary fallback): {e}")

    # Priority 2: PostgreSQL
    p_url = pg_url or os.getenv("DATABASE_URL", "").strip()
    if p_url or _CUSTOM_PG_CONN_FACTORY is not None:
        try:
            conn = _get_pg_connection(p_url)
            if conn:
                init_pg_schema(conn)
                cur = conn.cursor()
                try:
                    _exec(cur, "SELECT COUNT(*) FROM kv_files;")
                    row_count = cur.fetchone()[0]
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass

                if row_count > 0:
                    restore_from_pg(conn)
                else:
                    seed_to_pg(conn)

                conn.close()
                _ACTIVE_BACKEND = "postgres"
                _PERSISTENCE_MODE = "database"

                _BACKGROUND_THREAD = threading.Thread(target=_sync_loop, daemon=True, name="pg-persist-worker")
                _BACKGROUND_THREAD.start()
                logger.info("PostgreSQL database persistence successfully initialized.")
                return
        except Exception as e:
            logger.warning(f"Failed to start PostgreSQL persistence: {e}")

    # Priority 3: Local fallback
    _ACTIVE_BACKEND = "local"
    _PERSISTENCE_MODE = "local"
    logger.info("Using local filesystem persistence (no database configured).")


def stop_persistence():
    """Flushes changes and terminates background thread on shutdown."""
    global _BACKGROUND_THREAD, _PERSISTENCE_MODE, _ACTIVE_BACKEND
    _STOP_EVENT.set()
    try:
        flush_all_pending()
    except Exception:
        pass
    if _BACKGROUND_THREAD and _BACKGROUND_THREAD.is_alive():
        _BACKGROUND_THREAD.join(timeout=2.0)
        _BACKGROUND_THREAD = None
    _PERSISTENCE_MODE = "local"
    _ACTIVE_BACKEND = "local"



def get_persistence_mode() -> str:
    """Returns 'database' if DB persistence is active, otherwise 'local'."""
    return _PERSISTENCE_MODE


def get_persistence_backend() -> str:
    """Returns active backend: 'mongodb', 'postgres', or 'local'."""
    return _ACTIVE_BACKEND


def set_custom_mongo_collection(coll):
    """Sets a custom collection (e.g. mongomock) for unit tests."""
    global _CUSTOM_MONGO_COLL
    _CUSTOM_MONGO_COLL = coll


def set_custom_connection_factory(factory):
    """Sets a custom Postgres / SQLite connection factory for unit tests."""
    global _CUSTOM_PG_CONN_FACTORY
    _CUSTOM_PG_CONN_FACTORY = factory
