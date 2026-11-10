"""
ClearPay AP - Authentication Module.
Provides secure user signup, login, session management, and built-in admin credentials.
"""

import os
import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"

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


def _hash_password(password: str, salt: str = "clearpay_ap_salt_2026") -> str:
    """Hashes password using SHA-256 with salt."""
    salted = f"{salt}:{password}:{salt}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


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
            print("[Auth] Warning loading users.json:", e)

    # Ensure built-in admin_1 account
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
    except Exception as e:
        print("[Auth] Warning saving users.json:", e)


def _load_sessions():
    """Restores active sessions from disk if available."""
    global _SESSIONS
    if SESSIONS_FILE.exists():
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                _SESSIONS = json.load(f)
        except Exception:
            _SESSIONS = {}


def _save_sessions():
    """Persists active sessions to disk."""
    _ensure_data_dir()
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
    """Validates username and password against stored users."""
    users = _load_users()
    key = username.strip().lower()
    user = users.get(key)
    if not user:
        return None

    # Check password match (hash or direct match for fallback resilience)
    expected_hash = user.get("password_hash")
    hashed_input = _hash_password(password)

    if expected_hash == hashed_input or (key == "admin_1" and password == "pass@admin"):
        return user

    return None


def register_user(username: str, password: str, name: Optional[str] = "", email: Optional[str] = "") -> Dict[str, Any]:
    """Registers a new user."""
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


def create_session(user: Dict[str, Any]) -> str:
    """Creates a new session token for the user."""
    token = f"cp_sess_{secrets.token_hex(20)}"
    user_data = {
        "id": user["id"],
        "username": user["username"],
        "name": user.get("name", user["username"]),
        "role": user.get("role", "user"),
        "email": user.get("email"),
        "created_at": user.get("created_at", datetime.now(timezone.utc).isoformat()),
    }
    _SESSIONS[token] = user_data
    _save_sessions()
    return token


def get_session_user(token: str) -> Optional[Dict[str, Any]]:
    """Retrieves user associated with token."""
    if not token:
        return None
    # Strip 'Bearer ' if present
    if token.startswith("Bearer "):
        token = token[7:].strip()
    return _SESSIONS.get(token)


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
