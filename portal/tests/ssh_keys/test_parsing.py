import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from app.ssh_keys.parsing import parse_ssh_public_key


def public_key_to_openssh(public_key) -> str:
    return public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("ascii")


def calculate_expected_fingerprint(public_key: str) -> str:
    encoded_key = public_key.split(" ", 1)[1]
    key_bytes = base64.b64decode(encoded_key)

    digest = hashlib.sha256(key_bytes).digest()

    encoded_digest = (
        base64.b64encode(digest)
        .decode("ascii")
        .rstrip("=")
    )

    return f"SHA256:{encoded_digest}"


def test_parse_ed25519_public_key() -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = public_key_to_openssh(private_key.public_key())

    parsed = parse_ssh_public_key(public_key)

    assert parsed.key_type == "ssh-ed25519"
    assert parsed.public_key == public_key
    assert parsed.fingerprint.startswith("SHA256:")
    assert parsed.fingerprint == calculate_expected_fingerprint(public_key)


def test_parse_public_key_removes_comment() -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = public_key_to_openssh(private_key.public_key())

    parsed = parse_ssh_public_key(
        f"{public_key} somebody@somewhere"
    )

    assert parsed.public_key == public_key
    assert "somebody@somewhere" not in parsed.public_key


def test_parse_rsa_2048_public_key() -> None:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = public_key_to_openssh(private_key.public_key())

    parsed = parse_ssh_public_key(public_key)

    assert parsed.key_type == "ssh-rsa"
    assert parsed.public_key == public_key
    assert parsed.fingerprint.startswith("SHA256:")


def test_parse_rejects_rsa_key_smaller_than_2048_bits() -> None:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=1024,
    )
    public_key = public_key_to_openssh(private_key.public_key())

    with pytest.raises(
        ValueError,
        match="RSA key must be at least 2048 bits",
    ):
        parse_ssh_public_key(public_key)


def test_parse_rejects_ecdsa_public_key() -> None:
    private_key = ec.generate_private_key(
        ec.SECP256R1()
    )
    public_key = public_key_to_openssh(private_key.public_key())

    with pytest.raises(
        ValueError,
        match="unsupported SSH public key type",
    ):
        parse_ssh_public_key(public_key)


def test_parse_rejects_invalid_public_key() -> None:
    with pytest.raises(
        ValueError,
        match="invalid SSH public key",
    ):
        parse_ssh_public_key("hello")


def test_parse_rejects_empty_public_key() -> None:
    with pytest.raises(
        ValueError,
        match="invalid SSH public key",
    ):
        parse_ssh_public_key("   ")