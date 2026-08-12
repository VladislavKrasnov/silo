from __future__ import annotations

import base64
import binascii
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MASTER_KEY_BYTES: int = 32
NONCE_BYTES: int = 12


class SecretDecryptionError(Exception):
    pass


def load_or_create_master_key(key_path: Path, environment_variable: str = "ORCHESTRATOR_MASTER_KEY") -> bytes:
    encoded_from_environment = (os.getenv(environment_variable) or "").strip()
    if encoded_from_environment:
        try:
            key_material = base64.urlsafe_b64decode(encoded_from_environment)
        except (binascii.Error, ValueError) as error:
            raise ValueError(f"{environment_variable} is not valid base64") from error
        if len(key_material) != MASTER_KEY_BYTES:
            raise ValueError(f"{environment_variable} must decode to {MASTER_KEY_BYTES} bytes")
        return key_material

    if key_path.exists():
        key_material = base64.urlsafe_b64decode(key_path.read_bytes().strip())
        if len(key_material) != MASTER_KEY_BYTES:
            raise ValueError(f"{key_path} does not contain a {MASTER_KEY_BYTES}-byte key")
        return key_material

    key_material = secrets.token_bytes(MASTER_KEY_BYTES)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as key_file:
        key_file.write(base64.urlsafe_b64encode(key_material))
    return key_material


class SecretCipher:
    __slots__ = ("_aead",)

    def __init__(self, master_key: bytes):
        if len(master_key) != MASTER_KEY_BYTES:
            raise ValueError(f"master key must be {MASTER_KEY_BYTES} bytes")
        self._aead = AESGCM(master_key)

    def encrypt(self, plaintext: str, context: str) -> bytes:
        nonce = secrets.token_bytes(NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))

    def decrypt(self, payload: bytes, context: str) -> str:
        if len(payload) <= NONCE_BYTES:
            raise SecretDecryptionError("ciphertext payload is truncated")
        try:
            plaintext = self._aead.decrypt(
                payload[:NONCE_BYTES], payload[NONCE_BYTES:], context.encode("utf-8")
            )
        except InvalidTag as error:
            raise SecretDecryptionError("ciphertext failed authentication") from error
        return plaintext.decode("utf-8")
