"""Content-addressed cache of clean, un-enriched asset results (JSON, never pickle)."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import zlib
from pathlib import Path

SCHEMA = 1
ENTRY_LIMIT = 32_000_000
BYTE_LIMIT = 256_000_000
COUNT_LIMIT = 10_000


def blob_sha(path: Path) -> str:
    """Git SHA-1 blob ID of actual bytes, with no Git/LFS/line-ending filters."""
    size = path.stat().st_size
    digest = hashlib.sha1(f"blob {size}\0".encode("ascii"))
    seen = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            seen += len(chunk)
    if seen != size:
        raise OSError(f"asset changed size while hashing: {path.name}")
    return digest.hexdigest()


def decoder_fingerprint() -> str:
    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ("asset_cache.py", "ue_repo_digest.py", "bp_reader.py", "data_reader.py", "map_reader.py", "enum_values.py"):
        digest.update(name.encode("utf-8"))
        digest.update((here / name).read_bytes())
    import bp_reader
    digest.update(bp_reader.UASSET_READ_COMMIT.encode("ascii"))
    digest.update(str(sys.version_info[:2]).encode("ascii"))
    return digest.hexdigest()


def clean(value) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("markdown"), str):
        return False
    summary = value.get("summary")
    return (isinstance(summary, dict) and summary.get("parse_status") == "ok" and
            not summary.get("issues") and not summary.get("newer_format") and
            summary.get("nodes_ok") == summary.get("nodes_total") and
            summary.get("level_bp_status", "ok") == "ok")


class AssetCache:
    def __init__(self, directory: Path, repo: Path, version: str, *, fingerprint=None, log=print):
        self.root = directory.expanduser().resolve() / "asset-results-v1"
        self.repo = repo.resolve()
        self.version = version
        self.fingerprint = fingerprint or decoder_fingerprint()
        self.log = log
        self.stats = {"hits": 0, "misses": 0, "writes": 0, "errors": 0}

    def warn(self, error):
        self.stats["errors"] += 1
        if self.stats["errors"] <= 3:
            self.log(f"[cache] {type(error).__name__}: {error}; decoding normally")

    def safe(self, path):
        for part in (self.root, path.parent, path):
            if part.is_symlink() or (part.exists() and
                    getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
                raise ValueError("linked cache directory or entry")
        if path.parent.parent != self.root:
            raise ValueError("cache entry outside namespace")

    def key(self, stage: str, item):
        try:
            if stage not in ("bp", "data", "map"):
                raise ValueError("unknown asset-cache stage")
            paths = [Path(item[0])]
            parameters = [item[1]]
            if stage == "data":
                parameters.append(item[2])
            elif stage == "map":
                paths += [Path(path) for path in item[2]]
            blobs = [blob_sha(path) for path in paths]
            # External actor identity/order matters (including the decoder's cap).
            external = [path.resolve().relative_to(self.repo).as_posix() for path in paths[1:]]
            identity = {"schema": SCHEMA, "tool": self.version, "decoder": self.fingerprint,
                        "stage": stage, "parameters": parameters, "blobs": blobs, "external": external}
            raw = json.dumps(identity, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            name = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
            return identity, paths, self.root / name[:2] / (name + ".json.gz")
        except (OSError, ValueError) as error:
            self.warn(error)
            return None

    def load(self, key):
        self.stats["misses"] += 1
        if key is None:
            return None
        identity, _, path = key
        try:
            self.safe(path)
            with gzip.open(path, "rb") as source:
                data = source.read(ENTRY_LIMIT + 1)
            if len(data) > ENTRY_LIMIT:
                raise ValueError("cache entry exceeds read limit")
            entry = json.loads(data.decode("utf-8"))
            value = entry["value"]
            if entry["identity"] != identity:
                raise ValueError("cache identity mismatch")
            encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            if hashlib.sha256(encoded).hexdigest() != entry["checksum"]:
                raise ValueError("cache checksum mismatch")
            if not clean(value):
                raise ValueError("cache result is not clean")
            os.utime(path)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError, EOFError, zlib.error) as error:
            self.warn(error)
            return None
        self.stats["misses"] -= 1
        self.stats["hits"] += 1
        return value

    def store(self, key, value):
        if key is None or not clean(value):
            return
        identity, paths, destination = key
        try:
            self.safe(destination)
            if [blob_sha(path) for path in paths] != identity["blobs"]:
                raise ValueError("asset changed during decoding; cache write skipped")
            value = {k: v for k, v in value.items() if k != "seconds"} if isinstance(value, dict) else value
            encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            entry = {"identity": identity, "value": value, "checksum": hashlib.sha256(encoded).hexdigest()}
            # Preserve result field order so fresh/warm digest.json bytes agree.
            raw = json.dumps(entry, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > ENTRY_LIMIT:
                return
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.safe(destination)
            fd, temporary = tempfile.mkstemp(prefix=".asset-", dir=destination.parent)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(gzip.compress(raw, mtime=0))
                Path(temporary).replace(destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
            self.stats["writes"] += 1
        except (OSError, ValueError, TypeError) as error:
            self.warn(error)

    def prune(self, byte_limit=BYTE_LIMIT, count_limit=COUNT_LIMIT):
        """Delete only our regular, content-addressed entries, never input/output trees."""
        try:
            files = []
            if not self.root.exists():
                return
            for shard in self.root.iterdir():
                if not re.fullmatch(r"[A-Za-z0-9_-]{2}", shard.name):
                    continue
                try:
                    self.safe(shard / "check")
                except ValueError:
                    continue
                if not shard.is_dir():
                    continue
                for path in shard.glob("*.json.gz"):
                    name = path.name.removesuffix(".json.gz")
                    if re.fullmatch(r"[A-Za-z0-9_-]{43}", name) and shard.name == name[:2]:
                        try:
                            self.safe(path)
                        except ValueError:
                            continue
                        info = path.stat()
                        if stat.S_ISREG(info.st_mode):
                            files.append((info.st_mtime_ns, path, info.st_size))
            size = sum(row[2] for row in files)
            count = len(files)
            for _, path, length in sorted(files):
                if size <= byte_limit and count <= count_limit:
                    break
                self.safe(path)
                path.unlink(missing_ok=True)
                size -= length
                count -= 1
        except (OSError, ValueError) as error:
            self.warn(error)
