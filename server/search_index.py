"""Persistent literal substring search using stdlib SQLite FTS5 trigrams.

Index completed, immutable digest generations once. Query parameters are literal
strings, never FTS syntax. Short queries/older SQLite use instr on indexed text.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

VERSION = 1
MAX_FILE_BYTES = 2_000_000
MAX_INDEX_BYTES = 64_000_000
MAX_INDEX_FILES = 10_000
MAX_INDEX_LINES = 200_000
BUILD_LOCK = threading.Lock()


def linked(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def text_files(base: Path, extensions: set[str]):
    """Walk only contained, regular text files; do not traverse links or .git."""
    root = base.resolve()
    if not base.is_dir():
        return
    def walk_error(error):
        raise error

    for folder, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
        parent = Path(folder)
        dirs[:] = sorted(name for name in dirs if name.lower() != ".git" and not linked(parent / name))
        for name in sorted(files):
            path = parent / name
            if name.lower() == ".git" or linked(path) or not path.is_file():
                continue
            if path.suffix.lower() not in extensions and path.name not in extensions:
                continue
            if root in path.resolve().parents:
                yield path


def _table(connection) -> bool:
    try:
        connection.execute("CREATE VIRTUAL TABLE lines USING fts5(path UNINDEXED, number UNINDEXED, "
                           "text UNINDEXED, source UNINDEXED, folded, tokenize='trigram case_sensitive 1')")
        return True
    except sqlite3.OperationalError as exc:
        if "no such module" not in str(exc) and "no such tokenizer" not in str(exc):
            raise
        connection.execute("CREATE TABLE lines(path TEXT, number INTEGER, text TEXT, source INTEGER, folded TEXT)")
        return False


def ensure_index(directory: Path, source_ext: set[str]) -> Path:
    database = directory / "search.sqlite"
    generation = f"{VERSION}:{sqlite3.sqlite_version}:{directory.name}:{(directory / 'cache.json').stat().st_mtime_ns}"
    with BUILD_LOCK:
        if database.is_file():
            try:
                with closing(sqlite3.connect(database)) as connection:
                    if connection.execute("SELECT value FROM meta WHERE key='generation'").fetchone() == (generation,):
                        return database
            except sqlite3.DatabaseError:
                pass  # incomplete/old/corrupted indexes are rebuilt from completed files
        fd, temporary = tempfile.mkstemp(prefix=".search-", suffix=".sqlite", dir=directory)
        os.close(fd)
        temporary = Path(temporary)
        try:
            with closing(sqlite3.connect(temporary)) as connection:
                fts = _table(connection)
                connection.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
                omitted = used_bytes = count = row_count = 0
                capped = False

                def records(label, text, source):
                    nonlocal row_count, capped
                    for number, line in enumerate(text.splitlines(), 1):
                        if not line.strip():
                            continue
                        if row_count >= MAX_INDEX_LINES:
                            capped = True
                            return
                        row_count += 1
                        yield label, number, line, source, line.lower()

                for source, base, extensions in ((0, directory / "digest", {".md"}),
                                                  (1, directory / "repo", source_ext)):
                    for path in text_files(base, extensions):
                        if count >= MAX_INDEX_FILES or used_bytes >= MAX_INDEX_BYTES:
                            capped = True
                            break
                        count += 1
                        size = path.stat().st_size
                        if size > MAX_FILE_BYTES or used_bytes + size > MAX_INDEX_BYTES:
                            omitted += 1
                            continue
                        try:
                            text = path.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            omitted += 1
                            continue
                        used_bytes += size
                        label = ("repo:" if source else "") + path.relative_to(base).as_posix()
                        connection.executemany("INSERT INTO lines VALUES(?,?,?,?,?)", records(label, text, source))
                        if capped:
                            break
                    if capped:
                        break
                warning = (f"Search coverage: omitted {omitted} oversized/unreadable files. " if omitted else "")
                if capped:
                    warning += f"Search coverage limited to {MAX_INDEX_FILES} files / {MAX_INDEX_BYTES} bytes / {MAX_INDEX_LINES} lines. "
                if not fts:
                    warning += "Search acceleration unavailable; using cached literal scan. "
                connection.executemany("INSERT INTO meta VALUES(?,?)",
                                       [("generation", generation), ("fts", str(int(fts))), ("warning", warning)])
                connection.commit()
            temporary.replace(database)
        finally:
            temporary.unlink(missing_ok=True)
    return database


def search(directory: Path, source_ext: set[str], query: str, include_source: bool, limit: int):
    if not query.strip() or len(query) > 256 or "\0" in query:
        raise ValueError("query must contain 1–256 characters of nonblank literal text")
    database = ensure_index(directory, source_ext)
    with closing(sqlite3.connect(database, timeout=5)) as connection:
        deadline = time.monotonic() + 5
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        meta = dict(connection.execute("SELECT key,value FROM meta"))
        query = query.lower()
        if meta["fts"] == "1" and len(query) >= 3:
            where, parameter = "lines MATCH ?", '"' + query.replace('"', '""') + '"'
        else:
            where, parameter = "instr(folded, ?) > 0", query
        try:
            rows = connection.execute(f"SELECT path,number,text FROM lines WHERE {where} AND source <= ? "
                                      "ORDER BY path,number LIMIT ?", (parameter, int(include_source), limit + 1)).fetchall()
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise ValueError("search exceeded 5s; narrow the query") from None
            raise
        return rows[:limit], len(rows) > limit, meta["warning"]
