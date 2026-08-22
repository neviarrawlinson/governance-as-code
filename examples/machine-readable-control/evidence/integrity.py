import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


VERIFIED = "VERIFIED"
MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class IntegrityVerification:
    status: str
    components: dict[str, str]
    mismatched_components: list[str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_source_integrity(
    control_path: Path, environment_path: Path, validator_path: Path
) -> dict[str, str]:
    return build_source_integrity_from_bytes(
        control_path.read_bytes(),
        environment_path.read_bytes(),
        validator_path.read_bytes(),
    )


def build_source_integrity_from_bytes(
    control_bytes: bytes, environment_bytes: bytes, validator_bytes: bytes
) -> dict[str, str]:
    return {
        "algorithm": "SHA-256",
        "control_sha256": hashlib.sha256(control_bytes).hexdigest(),
        "environment_sha256": hashlib.sha256(environment_bytes).hexdigest(),
        "validator_sha256": hashlib.sha256(validator_bytes).hexdigest(),
    }


def write_detached_checksum(evidence_path: Path) -> Path:
    checksum_path = evidence_path.with_suffix(evidence_path.suffix + ".sha256")
    checksum_path.write_text(
        f"{sha256_file(evidence_path)}  {evidence_path.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    return checksum_path


def get_repository_commit(repository_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repository_root.resolve().as_posix()}",
                "-C",
                str(repository_root),
                "rev-parse",
                "HEAD",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit if re.fullmatch(r"[0-9a-fA-F]{40,64}", commit) else None


def _safe_sha256_file(path: Path) -> str | None:
    try:
        return sha256_file(path)
    except OSError:
        return None


def _read_detached_checksum(checksum_path: Path, evidence_name: str) -> str | None:
    try:
        checksum_text = checksum_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    match = re.fullmatch(
        rf"([0-9a-f]{{64}})  {re.escape(evidence_name)}\n", checksum_text
    )
    return match.group(1) if match else None


def _valid_integrity_metadata(integrity: object) -> bool:
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "SHA-256":
        return False
    return all(
        isinstance(integrity.get(field), str)
        and re.fullmatch(r"[0-9a-f]{64}", integrity[field]) is not None
        for field in ("control_sha256", "environment_sha256", "validator_sha256")
    )


def verify_evidence(
    evidence_path: Path,
    checksum_path: Path,
    control_path: Path,
    environment_path: Path,
    validator_path: Path,
) -> IntegrityVerification:
    artifact_checksum = _safe_sha256_file(evidence_path)
    expected_artifact_checksum = _read_detached_checksum(
        checksum_path, evidence_path.name
    )
    artifact_status = (
        VERIFIED
        if artifact_checksum is not None
        and expected_artifact_checksum is not None
        and artifact_checksum == expected_artifact_checksum
        else MISMATCH
    )

    try:
        with evidence_path.open(encoding="utf-8") as evidence_file:
            evidence = json.load(evidence_file)
        evidence_structure_status = VERIFIED if isinstance(evidence, dict) else MISMATCH
    except (OSError, UnicodeError, json.JSONDecodeError):
        evidence = {}
        evidence_structure_status = MISMATCH

    expected_integrity = evidence.get("integrity")
    metadata_status = (
        VERIFIED if _valid_integrity_metadata(expected_integrity) else MISMATCH
    )
    expected_integrity = expected_integrity if isinstance(expected_integrity, dict) else {}

    source_checks = (
        ("control_definition", control_path, "control_sha256"),
        ("environment_data", environment_path, "environment_sha256"),
        ("validator_implementation", validator_path, "validator_sha256"),
    )
    components = {
        "evidence_artifact": artifact_status,
        "evidence_structure": evidence_structure_status,
        "integrity_metadata": metadata_status,
    }
    for component, source_path, digest_field in source_checks:
        current_digest = _safe_sha256_file(source_path)
        expected_digest = expected_integrity.get(digest_field)
        components[component] = (
            VERIFIED
            if current_digest is not None
            and isinstance(expected_digest, str)
            and current_digest == expected_digest
            else MISMATCH
        )
    mismatched_components = [
        component for component, status in components.items() if status == MISMATCH
    ]
    return IntegrityVerification(
        status=MISMATCH if mismatched_components else VERIFIED,
        components=components,
        mismatched_components=mismatched_components,
    )
