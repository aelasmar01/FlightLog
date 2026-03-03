from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from flightlog.models import NormalizedEvent, RedactionReport
from flightlog.pack_writer import create_pack
from flightlog.signing import sign_pack, verify_pack


def _event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id="e1",
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        source="test",
        type="model.request",
        session_id="s",
        run_id="r",
        payload={"text": "hello"},
    )


def test_sign_and_verify_then_tamper_fails(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    create_pack(pack_dir, [_event()], {}, RedactionReport())

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_key_path = tmp_path / "private.pem"
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    public_key_path = tmp_path / "public.pem"
    public_key_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    signature_path = sign_pack(
        pack_path=pack_dir,
        private_key_path=private_key_path,
        signature_path=None,
    )
    assert signature_path.exists()

    ok, errors = verify_pack(
        pack_path=pack_dir,
        public_key_path=public_key_path,
        signature_path=None,
    )
    assert ok, errors

    timeline = pack_dir / "timeline.jsonl"
    timeline.write_text(timeline.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    ok2, errors2 = verify_pack(
        pack_path=pack_dir,
        public_key_path=public_key_path,
        signature_path=None,
    )
    assert not ok2
    assert errors2
