"""Git workspace snapshots and the ownership guard (read-only Git commands only)."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PRIVATE_PREFIX = ".chat-decisions/"
CACHE_TOKENS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache")


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    head: str
    files: dict[str, str]  # path -> content digest of every dirty/untracked file

    def to_json(self) -> dict:
        return {"head": self.head, "files": self.files, "digest": self.digest()}

    def digest(self) -> str:
        body = "\n".join(f"{p}\0{d}" for p, d in sorted(self.files.items()))
        return hashlib.sha256(f"{self.head}\n{body}".encode("utf-8")).hexdigest()

    @staticmethod
    def from_json(data: dict) -> "Snapshot":
        return Snapshot(data["head"], dict(data["files"]))


def _git(root: Path, *argv: str) -> bytes:
    try:
        done = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", *argv], stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=120,
                              env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.SubprocessError) as exc:
        raise SnapshotError(f"git indisponível: {exc}") from exc
    if done.returncode != 0:
        raise SnapshotError(done.stderr.decode("utf-8", "replace").strip() or f"git {argv[0]} falhou")
    return done.stdout


def take_snapshot(root: Path) -> Snapshot:
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    files: dict[str, str] = {}
    index = 0
    while index < len(raw):
        entry = raw[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2].decode(), entry[3:].decode("utf-8", "replace")
        if "R" in code or "C" in code:
            index += 1  # the original path follows as a separate NUL field
        if path.startswith(PRIVATE_PREFIX):
            continue
        target = root / path
        files[path] = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "<absent>"
    return Snapshot(head, files)


def changed_paths(before: Snapshot, after: Snapshot) -> list[str]:
    """Files whose content differs between snapshots (a clean file counts as '<clean>')."""
    names = set(before.files) | set(after.files)
    return sorted(n for n in names if before.files.get(n, "<clean>") != after.files.get(n, "<clean>"))


def ownership_violations(role: str, changed: list[str], patterns: tuple[str, ...], head_changed: bool) -> list[str]:
    """Only Code may change project files, and only inside its exclusive globs.

    Other roles may touch only paths their config explicitly allows (e.g. QA caches).
    """
    problems = []
    if head_changed:
        problems.append("HEAD mudou: commit/checkout não é autorizado")
    # Independent of config validation: read-only roles get no patterns at all, QA only cache globs.
    if role == "code":
        allowed = patterns
    elif role == "qa":
        allowed = tuple(p for p in patterns if any(token in p for token in CACHE_TOKENS))
    else:
        allowed = ()
    for path in changed:
        if not any(fnmatch.fnmatch(path, pattern) for pattern in allowed):
            problems.append(f"{role} alterou fora do ownership: {path}")
    return problems


Snapshotter = Callable[[Path], Snapshot]
