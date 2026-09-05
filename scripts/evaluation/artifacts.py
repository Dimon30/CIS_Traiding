"""Reproducible artifact and manifest helpers for evaluation protocol v3."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .contracts import (
    ARTIFACT_SCHEMA_VERSION,
    ELIGIBILITY_VERSION,
    EVALUATION_PROTOCOL_VERSION,
    MATCHED_RANDOM_VERSION,
    POLICY_VERSION,
    TARGET_CONTRACT_VERSION,
    UNCERTAINTY_VERSION,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_metadata() -> dict[str, object]:
    def run(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    try:
        commit = run("rev-parse", "HEAD")
        status = run("status", "--porcelain")
        diff = subprocess.check_output(
            ["git", "diff", "--binary", "HEAD"], stderr=subprocess.DEVNULL
        )
        diff_digest = hashlib.sha256()
        diff_digest.update(diff)
        diff_digest.update(status.encode("utf-8"))
        return {
            "git_commit": commit,
            "git_dirty": bool(status),
            "git_diff_sha256": diff_digest.hexdigest() if status else None,
        }
    except Exception:
        return {"git_commit": None, "git_dirty": None, "git_diff_sha256": None}


def dependency_versions() -> dict[str, str | None]:
    names = ["numpy", "pandas", "scikit-learn", "scipy", "catboost", "dbfread"]
    result: dict[str, str | None] = {"python": sys.version.split()[0]}
    for name in names:
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def build_manifest(
    *,
    run_id: str,
    command: list[str],
    config: Mapping[str, Any],
    input_paths: list[Path],
    universe_ids: Mapping[str, str],
    extra: Mapping[str, Any] | None = None,
    git_state: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    inputs = [
        {"path": path.as_posix(), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted(input_paths)
    ]
    git = dict(git_state) if git_state is not None else git_metadata()
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "target_contract_version": TARGET_CONTRACT_VERSION,
        "eligibility_version": ELIGIBILITY_VERSION,
        "policy_version": POLICY_VERSION,
        "matched_random_version": MATCHED_RANDOM_VERSION,
        "uncertainty_version": UNCERTAINTY_VERSION,
        "command": command,
        "config": dict(config),
        "inputs": inputs,
        "universe_ids": dict(universe_ids),
        "dependencies": dependency_versions(),
        **git,
        "canonical_eligible": git["git_dirty"] is False,
        **dict(extra or {}),
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    temporary.replace(path)


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    compression = "gzip" if path.suffix == ".gz" else None
    frame.to_csv(temporary, index=False, compression=compression)
    temporary.replace(path)


def validate_protocol_compatibility(manifests: list[Mapping[str, Any]]) -> None:
    versions = {
        (
            item.get("evaluation_protocol_version", "legacy"),
            item.get("artifact_schema_version", item.get("evaluation_schema_version", 1)),
            item.get("target_contract_version", "legacy"),
            item.get("eligibility_version", "legacy"),
            item.get("policy_version", "legacy"),
            item.get("matched_random_version", "legacy"),
            item.get("uncertainty_version", "legacy"),
        )
        for item in manifests
    }
    if len(versions) > 1:
        raise ValueError(f"Incompatible evaluation protocols: {sorted(versions, key=str)}")
