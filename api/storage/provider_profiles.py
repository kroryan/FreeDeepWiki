"""Provider profiles (Fase 0 storage / Fase 4 provider profiles).

A named, durable profile bundling a provider + its (eventually encrypted) API
key + endpoint, so a user configures a provider once and reuses it across
repos and restarts instead of pasting the key into the UI every time. Lives
in ``profile.db`` (cross-repo) because a provider profile is not repo-scoped.

The api_key column is ``api_key_enc`` and is intended to hold AES-encrypted
ciphertext once Fase 4.1 lands ``api.security.encrypt_secret``. Until then it
stores the key as given -- the local-first, zero-key path has no master key
to encrypt with, matching the existing .env-based key handling.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.storage import connect, profile_db_path

logger = logging.getLogger(__name__)


def _db():
    return connect(profile_db_path())


def upsert(name: str, provider: str, api_key: Optional[str] = None,
           api_endpoint: Optional[str] = None,
           api_key_enc: Optional[str] = None) -> int:
    """Create or update a profile by name. ``api_key_enc`` takes precedence
    over ``api_key`` so the Fase 4.1 encryption layer can pass ciphertext
    directly without a decrypt/re-encrypt round-trip."""
    key_val = api_key_enc if api_key_enc is not None else api_key
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO provider_profiles (name, provider, api_key_enc, api_endpoint) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "provider=excluded.provider, api_key_enc=excluded.api_key_enc, "
            "api_endpoint=excluded.api_endpoint, updated_at=datetime('now')",
            (name, provider, key_val, api_endpoint),
        )
        conn.commit()
        return int(cur.lastrowid)


def get(name: str) -> Optional[dict]:
    with _db() as conn:
        row = conn.execute(
            "SELECT id, name, provider, api_key_enc, api_endpoint, "
            "created_at, updated_at FROM provider_profiles WHERE name = ?",
            (name,),
        ).fetchone()
        return dict(row) if row else None


def list_all() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT name, provider, api_endpoint, updated_at FROM provider_profiles "
            "ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


def delete(name: str) -> bool:
    with _db() as conn:
        cur = conn.execute("DELETE FROM provider_profiles WHERE name = ?", (name,))
        conn.commit()
        return cur.rowcount > 0
