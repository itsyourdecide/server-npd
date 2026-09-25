import base64
from dataclasses import dataclass

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives.serialization import ssh_key_fingerprint


@dataclass(frozen=True, slots=True)
class ParsedSshPublicKey:
    key_type: str
    public_key: str
    fingerprint: str


def parse_ssh_public_key(value: str) -> ParsedSshPublicKey:

    try:
        key = serialization.load_ssh_public_key(
            value.strip().encode("utf-8")
        )
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise ValueError("invalid SSH public key") from exc

    if isinstance(key, ed25519.Ed25519PublicKey):
        pass

    elif isinstance(key, rsa.RSAPublicKey):
        if key.key_size < 2048:
            raise ValueError("RSA key must be at least 2048 bits")

    else:
        raise ValueError("unsupported SSH public key type")  # noqa: TRY004

    public_key = key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("ascii")

    key_type = public_key.split(" ", 1)[0]

    fingerprint_bytes = ssh_key_fingerprint(
        key,
        hashes.SHA256(),
    )

    fingerprint = (
        "SHA256:"
        + base64.b64encode(fingerprint_bytes)
        .decode("ascii")
        .rstrip("=")
    )

    return ParsedSshPublicKey(
        key_type=key_type,
        public_key=public_key,
        fingerprint=fingerprint,
    )