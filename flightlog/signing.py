"""Pack signing and signature verification (Ed25519)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from flightlog.json_utils import canonical_json_dumps
from flightlog.pack_io import open_pack
from flightlog.pack_writer import validate_pack


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private key must be an Ed25519 PEM key")
    return key


def _load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("public key must be an Ed25519 PEM key")
    return key


def _sign_payload(pack_path: Path) -> dict[str, Any]:
    with open_pack(pack_path) as pack_dir:
        manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", {})
    artifact_map = artifacts if isinstance(artifacts, dict) else {}
    return {
        "schema_version": manifest.get("schema_version"),
        "timeline_sha256": manifest.get("timeline_sha256"),
        "artifact_hashes": {k: artifact_map[k] for k in sorted(artifact_map)},
    }


def sign_pack(
    *,
    pack_path: Path,
    private_key_path: Path,
    signature_path: Path | None,
) -> Path:
    valid, errors = validate_pack(pack_path)
    if not valid:
        raise ValueError("Cannot sign invalid pack: " + "; ".join(errors))

    private_key = _load_private_key(private_key_path)
    public_key_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    payload = _sign_payload(pack_path)
    payload_bytes = canonical_json_dumps(payload).encode("utf-8")
    signature = private_key.sign(payload_bytes)

    if signature_path is None:
        if not pack_path.is_dir():
            raise ValueError("--signature is required when signing a zip pack")
        signature_path = pack_path / "signature.json"

    signature_doc = {
        "algorithm": "ed25519",
        "payload": payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
        "public_key_pem": public_key_pem,
    }
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(canonical_json_dumps(signature_doc) + "\n", encoding="utf-8")
    return signature_path


def verify_pack(
    *,
    pack_path: Path,
    public_key_path: Path,
    signature_path: Path | None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    valid, validation_errors = validate_pack(pack_path)
    if not valid:
        errors.extend(validation_errors)
        return False, errors

    if signature_path is None:
        if pack_path.is_dir():
            signature_path = pack_path / "signature.json"
        else:
            errors.append("--signature is required when verifying a zip pack")
            return False, errors

    if not signature_path.exists():
        return False, [f"signature file not found: {signature_path}"]

    signature_doc = json.loads(signature_path.read_text(encoding="utf-8"))
    if not isinstance(signature_doc, dict):
        return False, ["signature file is not a JSON object"]

    if signature_doc.get("algorithm") != "ed25519":
        errors.append("unsupported signature algorithm")

    payload = signature_doc.get("payload")
    if not isinstance(payload, dict):
        errors.append("signature payload missing")
        return False, errors

    recomputed_payload = _sign_payload(pack_path)
    if payload != recomputed_payload:
        errors.append("signed payload does not match current pack hashes")

    signature_base64 = signature_doc.get("signature_base64")
    if not isinstance(signature_base64, str):
        errors.append("signature_base64 missing")
        return False, errors

    try:
        signature = base64.b64decode(signature_base64)
    except Exception:
        errors.append("signature_base64 is invalid")
        return False, errors

    public_key = _load_public_key(public_key_path)

    embedded_key = signature_doc.get("public_key_pem")
    if isinstance(embedded_key, str):
        supplied_public = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        if supplied_public != embedded_key:
            errors.append("provided public key does not match embedded signature key")

    payload_bytes = canonical_json_dumps(payload).encode("utf-8")
    try:
        public_key.verify(signature, payload_bytes)
    except InvalidSignature:
        errors.append("signature verification failed")

    return len(errors) == 0, errors
