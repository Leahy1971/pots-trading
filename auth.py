"""
auth.py
=======
Encrypted credential storage for POTS.
Uses Fernet symmetric encryption (cryptography library).
Credentials are stored in a local file — only unlockable with the master password.

Usage:
    from auth import CredentialStore
    store = CredentialStore()
    store.save(master_password, username, password, app_key)
    creds = store.load(master_password)  # returns dict or None
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# Store credentials alongside the app, or in user home if running in cloud
_DEFAULT_PATH = Path(__file__).parent / ".pots_credentials"
_SALT_PATH    = Path(__file__).parent / ".pots_salt"


def _derive_key(master_password: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from the master password + salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))


class CredentialStore:
    """Save and load encrypted Betfair credentials."""

    def __init__(self, path: Path = _DEFAULT_PATH, salt_path: Path = _SALT_PATH):
        self._path      = path
        self._salt_path = salt_path

    def _get_or_create_salt(self) -> bytes:
        if self._salt_path.exists():
            return self._salt_path.read_bytes()
        salt = os.urandom(16)
        self._salt_path.write_bytes(salt)
        return salt

    def save(
        self,
        master_password: str,
        username: str,
        betfair_password: str,
        app_key: str,
    ) -> None:
        """Encrypt and save credentials to disk."""
        salt  = self._get_or_create_salt()
        key   = _derive_key(master_password, salt)
        f     = Fernet(key)
        data  = json.dumps({
            "username": username,
            "password": betfair_password,
            "app_key":  app_key,
        }).encode()
        self._path.write_bytes(f.encrypt(data))

    def load(self, master_password: str) -> Optional[dict]:
        """Decrypt and return credentials, or None if wrong password / no file."""
        if not self._path.exists():
            return None
        try:
            salt  = self._get_or_create_salt()
            key   = _derive_key(master_password, salt)
            f     = Fernet(key)
            data  = f.decrypt(self._path.read_bytes())
            return json.loads(data.decode())
        except (InvalidToken, Exception):
            return None

    def exists(self) -> bool:
        """Return True if credentials have previously been saved."""
        return self._path.exists()

    def delete(self) -> None:
        """Remove stored credentials."""
        if self._path.exists():
            self._path.unlink()
        if self._salt_path.exists():
            self._salt_path.unlink()
