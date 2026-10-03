"""Memory-mapped binary index for ``papers.json``.

JSON remains the canonical interchange format. LMDB stores ordered keys for
cursor pagination and MessagePack values for compact, fast record decoding.
Named databases provide point indexes and a small inverted text index.
"""

from __future__ import annotations

import os
import re
import threading
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

import lmdb
import msgpack

from research_graph.models import Paper


_SCHEMA_VERSION = b"1"
_DATABASE_COUNT = 6
_MIN_MAP_SIZE = 64 * 1024 * 1024
_READER_CONDITION = threading.Condition()
_READER_ENVIRONMENTS: dict[Path, lmdb.Environment] = {}
_READER_COUNTS: dict[Path, int] = {}


def _seq_key(seq: int) -> bytes:
    return seq.to_bytes(8, byteorder="big", signed=False)


def _tokens(text: str) -> set[bytes]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return {
        encoded
        for word in words
        if len(word) >= 2 and len(encoded := word.encode("utf-8")) <= 128
    }


def _pack(paper: Paper) -> bytes:
    return msgpack.packb(paper.model_dump(mode="json"), use_bin_type=True)


def _unpack(payload: bytes) -> dict:
    return msgpack.unpackb(payload, raw=False)


def _open(
    path: Path,
    *,
    readonly: bool,
    map_size: int = _MIN_MAP_SIZE,
) -> lmdb.Environment:
    return lmdb.open(
        str(path),
        subdir=False,
        readonly=readonly,
        create=not readonly,
        map_size=map_size,
        max_dbs=_DATABASE_COUNT,
        max_readers=256,
        lock=True,
        readahead=True,
        meminit=False,
        sync=True,
        metasync=True,
    )


@contextmanager
def _reader_environment(path: Path):
    """Share one LMDB Environment per file while allowing parallel txns."""
    key = path.resolve()
    with _READER_CONDITION:
        environment = _READER_ENVIRONMENTS.get(key)
        if environment is None:
            environment = _open(key, readonly=True)
            _READER_ENVIRONMENTS[key] = environment
            _READER_COUNTS[key] = 0
        _READER_COUNTS[key] += 1
    try:
        yield environment
    finally:
        with _READER_CONDITION:
            _READER_COUNTS[key] -= 1
            _READER_CONDITION.notify_all()


def _close_cached_reader(path: Path) -> None:
    """Close the process-local reader before atomically replacing a snapshot."""
    key = path.resolve()
    with _READER_CONDITION:
        while _READER_COUNTS.get(key, 0):
            _READER_CONDITION.wait()
        environment = _READER_ENVIRONMENTS.pop(key, None)
        _READER_COUNTS.pop(key, None)
        if environment is not None:
            environment.close()


def write_papers_kv(path: str | Path, papers: Iterable[Paper]) -> Path:
    """Atomically replace *path* with an LMDB + MessagePack snapshot."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _close_cached_reader(target)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary_lock = Path(f"{temporary}-lock")
    temporary.unlink(missing_ok=True)
    temporary_lock.unlink(missing_ok=True)

    records = [(seq, paper, _pack(paper)) for seq, paper in enumerate(papers, start=1)]
    payload_bytes = sum(len(payload) for _, _, payload in records)
    map_size = max(_MIN_MAP_SIZE, payload_bytes * 12)

    environment = _open(temporary, readonly=False, map_size=map_size)
    try:
        papers_db = environment.open_db(b"papers", create=True)
        ids_db = environment.open_db(b"paper_ids", create=True)
        dois_db = environment.open_db(b"dois", create=True)
        years_db = environment.open_db(b"years", create=True, dupsort=True)
        terms_db = environment.open_db(b"terms", create=True, dupsort=True)
        metadata_db = environment.open_db(b"metadata", create=True)

        with environment.begin(write=True) as transaction:
            for seq, paper, payload in records:
                key = _seq_key(seq)
                transaction.put(key, payload, db=papers_db, append=True)
                transaction.put(paper.paper_id.encode("utf-8"), key, db=ids_db)
                if paper.doi:
                    transaction.put(paper.doi.casefold().encode("utf-8"), key, db=dois_db)
                if paper.year is not None:
                    transaction.put(str(paper.year).encode("ascii"), key, db=years_db)
                for term in sorted(_tokens(f"{paper.title}\n{paper.abstract or ''}")):
                    transaction.put(term, key, db=terms_db, dupdata=True)

            transaction.put(b"schema_version", _SCHEMA_VERSION, db=metadata_db)
            transaction.put(b"paper_count", str(len(records)).encode("ascii"), db=metadata_db)
            transaction.put(b"value_encoding", b"messagepack", db=metadata_db)
        environment.sync(True)
    except Exception:
        environment.close()
        temporary.unlink(missing_ok=True)
        temporary_lock.unlink(missing_ok=True)
        raise
    else:
        environment.close()

    os.replace(temporary, target)
    temporary_lock.unlink(missing_ok=True)
    return target


def _query_sequences(transaction, terms_db, query: str) -> list[int]:
    terms = sorted(_tokens(query))
    if not terms:
        return []
    postings: list[set[int]] = []
    with transaction.cursor(db=terms_db) as cursor:
        for term in terms:
            if not cursor.set_key(term):
                return []
            postings.append(
                {int.from_bytes(value, "big") for value in cursor.iternext_dup()}
            )
    return sorted(set.intersection(*postings))


def page_papers(
    path: str | Path,
    *,
    limit: int = 20,
    after: int = 0,
    query: str | None = None,
) -> dict:
    """Return one stable keyset-paginated page from an LMDB snapshot."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be in [1, 200]")
    if after < 0:
        raise ValueError("after must be >= 0")

    with _reader_environment(Path(path)) as environment:
        papers_db = environment.open_db(b"papers")
        terms_db = environment.open_db(b"terms")
        selected: list[tuple[int, bytes]] = []
        with environment.begin() as transaction:
            if query and query.strip():
                sequences = [
                    seq for seq in _query_sequences(transaction, terms_db, query)
                    if seq > after
                ][:limit + 1]
                for seq in sequences:
                    payload = transaction.get(_seq_key(seq), db=papers_db)
                    if payload is not None:
                        selected.append((seq, payload))
            else:
                with transaction.cursor(db=papers_db) as cursor:
                    found = cursor.set_range(_seq_key(after + 1))
                    while found and len(selected) < limit + 1:
                        selected.append(
                            (int.from_bytes(cursor.key(), "big"), bytes(cursor.value()))
                        )
                        found = cursor.next()
    has_more = len(selected) > limit
    page = selected[:limit]
    return {
        "items": [_unpack(payload) for _, payload in page],
        "next_after": page[-1][0] if has_more and page else None,
        "has_more": has_more,
    }


def get_paper_by_doi(path: str | Path, doi: str) -> dict | None:
    """Perform an indexed DOI lookup without scanning the corpus."""
    with _reader_environment(Path(path)) as environment:
        papers_db = environment.open_db(b"papers")
        dois_db = environment.open_db(b"dois")
        with environment.begin() as transaction:
            key = transaction.get(doi.casefold().encode("utf-8"), db=dois_db)
            payload = transaction.get(key, db=papers_db) if key else None
            return _unpack(payload) if payload else None


def index_papers_json(json_path: str | Path, kv_path: str | Path) -> Path:
    """Validate a ``papers.json`` array and build its binary KV snapshot."""
    import json

    raw = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("papers.json must contain a JSON array")
    papers = [Paper.model_validate(item) for item in raw]
    return write_papers_kv(kv_path, papers)


__all__ = ["get_paper_by_doi", "index_papers_json", "page_papers", "write_papers_kv"]
