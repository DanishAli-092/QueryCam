"""
core/security/auth.py
======================
Security & Audit Module — SDS §3.1 Module 2.

"Manage local offline authentication, hash passwords via bcrypt,
initialize secure session tokens, and enforce account lockouts
(5-minute lock after 3 failed attempts)."

Backs US-01 (Login) and US-02 (Account Lockout). All state lives in
SQLiteMetadataStore (USER table) — this module is pure logic, no SQL.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt

import config
from core.storage.sqlite_store import SQLiteMetadataStore
from dto.entities import User

logger = logging.getLogger("querycam.security.auth")


class AuthResult:
    """Simple result carrier — avoids overloading exceptions for expected outcomes."""

    def __init__(self, success: bool, message: str,
                 user: Optional[User] = None, token: Optional[str] = None) -> None:
        self.success = success
        self.message = message
        self.user = user
        self.token = token


class AuthService:
    """
    Python Auth Logic component (SDS §3.1 Module 2 Components Involved).

    Not named `User` because the SDS Class Diagram's `User` entity is a
    plain data row (authenticate()/reset_attempts() there are thin
    delegations); the actual lockout policy and bcrypt work lives here
    so it can be unit-tested without a live DB connection where needed.
    """

    def __init__(self, store: SQLiteMetadataStore) -> None:
        self.store = store
        self._sessions: dict[str, int] = {}  # token -> user_id, in-memory only

    def register(self, username: str, plaintext_password: str) -> AuthResult:
        if self.store.get_user_by_username(username) is not None:
            return AuthResult(False, "Username already exists.")
        hashed = self._hash_password(plaintext_password)
        user_id = self.store.create_user(username, hashed)
        self.store.log_system_event(user_id, "REGISTER", f"New account created: {username}")
        return AuthResult(True, "Account created.")

    def authenticate(self, username: str, plaintext_password: str) -> AuthResult:
        """
        US-01/US-02 flow, matching SDS §2 Mapping Design to User Stories:
        'compares the hashed input against the users table in SQLite',
        'tracks consecutive failed attempts ... temporarily suspending
        authentication to prevent unauthorized brute-force access.'
        """
        user = self.store.get_user_by_username(username)
        if user is None:
            # Deliberately identical message to "wrong password" — do not
            # leak whether a username exists.
            return AuthResult(False, "Invalid username or password.")

        if user.locked_until is not None:
            locked_until_dt = self._parse_dt(user.locked_until)
            if locked_until_dt > datetime.utcnow():
                remaining = int((locked_until_dt - datetime.utcnow()).total_seconds())
                self.store.log_system_event(user.user_id, "LOGIN_BLOCKED",
                                             f"Attempt during lockout ({remaining}s remaining)")
                return AuthResult(False, f"Account locked. Try again in {remaining}s.")
            else:
                # Lockout window has naturally expired — clear it.
                self.store.reset_attempts(user.user_id)
                user.failed_attempts = 0

        if not self._verify_password(plaintext_password, user.hashed_password):
            new_count = self.store.record_failed_attempt(user.user_id)
            self.store.log_system_event(user.user_id, "LOGIN_FAILED",
                                         f"Failed attempt #{new_count}")
            if new_count >= config.SECURITY.max_failed_attempts:
                locked_until = datetime.utcnow() + timedelta(
                    minutes=config.SECURITY.lockout_duration_minutes
                )
                self.store.set_lockout(user.user_id, locked_until.isoformat())
                self.store.log_system_event(
                    user.user_id, "ACCOUNT_LOCKED",
                    f"Locked for {config.SECURITY.lockout_duration_minutes}min after {new_count} attempts",
                )
                return AuthResult(
                    False,
                    f"Account locked for {config.SECURITY.lockout_duration_minutes} "
                    "minutes after too many failed attempts.",
                )
            return AuthResult(False, "Invalid username or password.")

        # Success path
        self.store.reset_attempts(user.user_id)
        token = self._issue_session_token(user.user_id)
        self.store.log_system_event(user.user_id, "LOGIN", "Successful login")
        return AuthResult(True, "Login successful.", user=user, token=token)

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def resolve_session(self, token: str) -> Optional[int]:
        return self._sessions.get(token)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _issue_session_token(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = user_id
        return token

    @staticmethod
    def _hash_password(plaintext: str) -> str:
        salt = bcrypt.gensalt(rounds=config.SECURITY.bcrypt_rounds)
        return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def _verify_password(plaintext: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            logger.error("Corrupt password hash encountered during verification.")
            return False

    @staticmethod
    def _parse_dt(value) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
