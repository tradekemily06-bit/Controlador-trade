from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass

_HASH_PREFIX = "scrypt"
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_SESSION_BYTES = 32
_SESSION_TTL_SECONDS = 8 * 60 * 60
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_FAILURES = 8


@dataclass(frozen=True)
class AuthSession:
    token_hash: str
    username: str
    csrf_token: str
    expires_at: float


class LocalAuth:
    """Server-side local authentication for a single deployment instance.

    Passwords are never stored in plaintext. Session state stays on the server;
    the browser receives only an opaque HttpOnly session cookie. Production
    requires an explicit password hash and session secret from the environment.
    """

    def __init__(self) -> None:
        self.enabled = (
            os.environ.get("CONTROLADOR_ENV", "development").strip().lower() == "production"
            or os.environ.get("CONTROLADOR_AUTH_REQUIRED", "").strip().lower() in {"1", "true", "yes"}
        )
        self.username = os.environ.get("CONTROLADOR_AUTH_USERNAME", "admin").strip()
        self.password_hash = os.environ.get("CONTROLADOR_AUTH_PASSWORD_HASH", "").strip()
        self.session_secret = os.environ.get("CONTROLADOR_SESSION_SECRET", "")
        self._sessions: dict[str, AuthSession] = {}
        self._login_failures: dict[str, list[float]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password_hash and self.session_secret)

    @property
    def ready(self) -> bool:
        return not self.enabled or self.configured

    @staticmethod
    def hash_password(password: str) -> str:
        if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
            raise ValueError("password must contain 12-256 characters")
        salt = secrets.token_bytes(_SALT_BYTES)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
        return "$".join(
            (_HASH_PREFIX, str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P),
             base64.urlsafe_b64encode(salt).decode("ascii"), base64.urlsafe_b64encode(digest).decode("ascii"))
        )

    @staticmethod
    def verify_password(password: str, encoded: str) -> bool:
        try:
            prefix, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
            if prefix != _HASH_PREFIX:
                return False
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
            actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p))
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    def _failure_key(self, client_key: str) -> str:
        return hmac.new(self.session_secret.encode("utf-8"), client_key.encode("utf-8"), hashlib.sha256).hexdigest()

    def _login_allowed(self, client_key: str, now: float) -> bool:
        key = self._failure_key(client_key)
        failures = [t for t in self._login_failures.get(key, []) if t > now - _LOGIN_WINDOW_SECONDS]
        self._login_failures[key] = failures
        return len(failures) < _LOGIN_MAX_FAILURES

    def _record_failure(self, client_key: str, now: float) -> None:
        key = self._failure_key(client_key)
        self._login_failures.setdefault(key, []).append(now)

    def login(self, username: str, password: str, client_key: str) -> AuthSession | None:
        if not self.ready or not self.enabled:
            return None
        now = time.time()
        if not self._login_allowed(client_key, now):
            return None
        valid = (
            isinstance(username, str)
            and hmac.compare_digest(username, self.username)
            and isinstance(password, str)
            and self.verify_password(password, self.password_hash)
        )
        if not valid:
            self._record_failure(client_key, now)
            return None
        raw_token = secrets.token_urlsafe(_SESSION_BYTES)
        token_hash = hmac.new(self.session_secret.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256).hexdigest()
        session = AuthSession(token_hash, self.username, secrets.token_urlsafe(32), now + _SESSION_TTL_SECONDS)
        self._sessions[token_hash] = session
        return AuthSession(raw_token, session.username, session.csrf_token, session.expires_at)

    def authenticate(self, raw_token: str) -> AuthSession | None:
        if not self.enabled:
            return AuthSession("", self.username, "", time.time() + _SESSION_TTL_SECONDS)
        if not self.configured or not raw_token:
            return None
        token_hash = hmac.new(self.session_secret.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256).hexdigest()
        session = self._sessions.get(token_hash)
        if session is None or session.expires_at <= time.time():
            self._sessions.pop(token_hash, None)
            return None
        return session

    def logout(self, raw_token: str) -> None:
        if raw_token and self.session_secret:
            token_hash = hmac.new(self.session_secret.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256).hexdigest()
            self._sessions.pop(token_hash, None)

    def csrf_valid(self, session: AuthSession, supplied: str) -> bool:
        return bool(supplied) and hmac.compare_digest(session.csrf_token, supplied)


def password_hash_from_environment() -> str:
    """Expose only the hash-generation interface; never print or persist plaintext."""
    password = os.environ.get("CONTROLADOR_BOOTSTRAP_PASSWORD", "")
    if not password:
        raise RuntimeError("CONTROLADOR_BOOTSTRAP_PASSWORD is not set")
    return LocalAuth.hash_password(password)
