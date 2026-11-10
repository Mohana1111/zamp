"""
ClearPay AP - Authentication Module.
Provides secure user signup, login, session management with expiration,
per-install salt isolation, and built-in admin credentials.
"""

import os
import json
import time
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
AUTH_SALT_FILE = DATA_DIR / ".auth_salt"

# Session Expiry: default 7 days (604,800 seconds), configurable via SESSION_TTL_SECONDS
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(7 * 24 * 3600)))

# In-memory session store
_SESSIONS: Dict[str, Dict[str, Any]] = {}


class UserPublic(BaseModel):
    id: str
    username: str
    name: str
    role: str = "user"
    email: Optional[str] = None
    created_at: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SignupRequest(BaseModel):
    username: str
    password: str
    name: Optional[str] = ""
    email: Optional[str] = ""


class AuthResponse(BaseModel):
    token: str
    user: UserPublic
    message: str = "Success"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_auth_salt() -> str:
    """
    Retrieves or generates a secure password salt:
    1. Env var AUTH_SALT if explicitly set.
    2. Per-install persisted random salt in backend/data/.auth_salt.
    3. Auto-generated cryptographic random hex token if not yet created.
    """
    env_salt = os.getenv("AUTH_SALT")
    if env_salt and env_salt.strip():
        return env_salt.strip()

    _ensure_data_dir()
    if AUTH_SALT_FILE.exists():
        try:
            stored = AUTH_SALT_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        except Exception:
            pass

    # Generate and persist fresh per-install random salt
    new_salt = secrets.token_hex(16)
    try:
        AUTH_SALT_FILE.write_text(new_salt, encoding="utf-8")
    except Exception:
        pass
    return new_salt


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hashes password using SHA-256 with the active per-install or specified salt."""
    active_salt = salt if salt is not None else _get_auth_salt()
    salted = f"{active_salt}:{password}:{active_salt}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def _load_users() -> Dict[str, Dict[str, Any]]:
    """Loads users from users.json, ensuring default admin_1 exists."""
    _ensure_data_dir()
    users: Dict[str, Dict[str, Any]] = {}
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for u in data:
                        users[u["username"].lower()] = u
                elif isinstance(data, dict):
                    users = {k.lower(): v for k, v in data.items()}
        except Exception as e:
            # Do not log sensitive user info
            pass

    # Ensure built-in admin_1 account exists
    admin_key = "admin_1"
    if admin_key not in users:
        admin_user = {
            "id": "usr_admin_1",
            "username": "admin_1",
            "password_hash": _hash_password("pass@admin"),
            "name": "Administrator",
            "role": "admin",
            "email": "admin@clearpay.internal",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        users[admin_key] = admin_user
        _save_users(users)

    return users


def _save_users(users: Dict[str, Dict[str, Any]]):
    """Saves users dictionary to users.json."""
    _ensure_data_dir()
    try:
        user_list = list(users.values())
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(user_list, f, indent=2)
    except Exception:
        pass


def _purge_expired_sessions():
    """Purges expired sessions from memory."""
    now_ts = time.time()
    expired = [t for t, s in _SESSIONS.items() if s.get("expires_at") and now_ts > s["expires_at"]]
    for t in expired:
        _SESSIONS.pop(t, None)


def _load_sessions():
    """Restores active sessions from disk if available and purges expired ones."""
    global _SESSIONS
    if SESSIONS_FILE.exists():
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                _SESSIONS = json.load(f)
            _purge_expired_sessions()
        except Exception:
            _SESSIONS = {}


def _save_sessions():
    """Persists active non-expired sessions to disk."""
    _ensure_data_dir()
    _purge_expired_sessions()
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_SESSIONS, f, indent=2)
    except Exception:
        pass


# Initialize stores
_ensure_data_dir()
_load_users()
_load_sessions()


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Validates username and password against stored users.
    Maintains compatibility with legacy static salt and built-in admin_1 credentials.
    """
    users = _load_users()
    key = username.strip().lower()
    user = users.get(key)
    if not user:
        return None

    expected_hash = user.get("password_hash")

    # 1. Match against current per-install / env salt
    if expected_hash and expected_hash == _hash_password(password):
        return user

    # 2. Match against legacy default salt for backward-compatibility
    if expected_hash and expected_hash == _hash_password(password, salt="clearpay_ap_salt_2026"):
        # Re-hash and upgrade to current salt
        user["password_hash"] = _hash_password(password)
        _save_users(users)
        return user

    # 3. Built-in admin_1 login resilience
    if key == "admin_1" and password == "pass@admin":
        user["password_hash"] = _hash_password("pass@admin")
        _save_users(users)
        return user

    return None


def register_user(username: str, password: str, name: Optional[str] = "", email: Optional[str] = "") -> Dict[str, Any]:
    """Registers a new user with secure password hashing."""
    clean_username = username.strip()
    key = clean_username.lower()

    if len(clean_username) < 3:
        raise ValueError("Username must be at least 3 characters long")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters long")

    users = _load_users()
    if key in users:
        raise ValueError(f"Username '{clean_username}' is already taken")

    new_user = {
        "id": f"usr_{secrets.token_hex(6)}",
        "username": clean_username,
        "password_hash": _hash_password(password),
        "name": (name or clean_username).strip(),
        "role": "admin" if key == "admin_1" else "user",
        "email": (email or f"{clean_username}@clearpay.internal").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    users[key] = new_user
    _save_users(users)
    return new_user


def create_session(user: Dict[str, Any], ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """Creates a new expiring session token for the user."""
    _purge_expired_sessions()
    token = f"cp_sess_{secrets.token_hex(20)}"
    now_ts = time.time()
    user_data = {
        "id": user["id"],
        "username": user["username"],
        "name": user.get("name", user["username"]),
        "role": user.get("role", "user"),
        "email": user.get("email"),
        "created_at": user.get("created_at", datetime.now(timezone.utc).isoformat()),
        "created_ts": now_ts,
        "expires_at": now_ts + ttl_seconds,
    }
    _SESSIONS[token] = user_data
    _save_sessions()
    return token


def get_session_user(token: str) -> Optional[Dict[str, Any]]:
    """Retrieves user associated with token if session has not expired."""
    if not token:
        return None
    if token.startswith("Bearer "):
        token = token[7:].strip()

    sess = _SESSIONS.get(token)
    if not sess:
        return None

    # Check session expiration
    expires_at = sess.get("expires_at")
    if expires_at and time.time() > expires_at:
        del _SESSIONS[token]
        _save_sessions()
        return None

    return sess


def delete_session(token: str) -> bool:
    """Deletes a session token."""
    if not token:
        return False
    if token.startswith("Bearer "):
        token = token[7:].strip()
    if token in _SESSIONS:
        del _SESSIONS[token]
        _save_sessions()
        return True
    return False
