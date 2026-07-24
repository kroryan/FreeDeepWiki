"""Durable embedding storage (Fase 0 storage / Fase 6/7 embeddings persistence).

The vector index currently lives only in the adalflow ``<owner>_<repo>.pkl``
binary cache: lose/delete it and the repo must be re-embedded from scratch
(cost + API spend). This module stores each chunk (text + vector + metadata)
in SQLite so the index is reconstructable from a durable, inspectable source.
The FAISS runtime index is materialized from these rows at load time (Fase
6/7 wires the backfill); for now this provides the write/read API the
backfill will target.

Vectors are stored as raw float32 little-endian BLOBs (the same layout FAISS
expects), not JSON, so round-tripping a few thousand vectors stays cheap.
"""

from __future__ import annotations

import json
import logging
import struct
from typing import Optional

from api.storage import connect, repo_db_path

logger = logging.getLogger(__name__)


def _db(owner: Optional[str], repo: Optional[str], repo_type: Optional[str]):
    return connect(repo_db_path(owner, repo, repo_type))


def _vec_to_blob(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def upsert_chunk(owner: Optional[str], repo: Optional[str], repo_type: Optional[str],
                 file_path: str, chunk_order: int, text: str,
                 vector: Optional[list[float]] = None,
                 meta: Optional[dict] = None) -> int:
    """Insert (or replace) one chunk row. Returns the row id. If ``vector``
    is None the row records text+meta only (e.g. a chunk awaiting embedding)."""
    with _db(owner, repo, repo_type) as conn:
        cur = conn.execute(
            "INSERT INTO embeddings (file_path, chunk_order, text, vector, meta_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                file_path, chunk_order, text,
                _vec_to_blob(vector) if vector else None,
                json.dumps(meta) if meta else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def load_all(owner: Optional[str], repo: Optional[str], repo_type: Optional[str]) -> list[dict]:
    """Return every chunk row (file_path, chunk_order, text, vector, meta).
    Used by the runtime to rebuild the FAISS index from the durable store."""
    with _db(owner, repo, repo_type) as conn:
        rows = conn.execute(
            "SELECT file_path, chunk_order, text, vector, meta_json FROM embeddings "
            "ORDER BY id ASC"
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "file_path": r["file_path"],
            "chunk_order": r["chunk_order"],
            "text": r["text"],
            "vector": _blob_to_vec(r["vector"]) if r["vector"] else None,
            "meta": json.loads(r["meta_json"]) if r["meta_json"] else None,
        })
    return out


def count(owner: Optional[str], repo: Optional[str], repo_type: Optional[str]) -> int:
    with _db(owner, repo, repo_type) as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM embeddings").fetchone()["c"])


def wipe(owner: Optional[str], repo: Optional[str], repo_type: Optional[str]) -> None:
    with _db(owner, repo, repo_type) as conn:
        conn.execute("DELETE FROM embeddings")
        conn.commit()
