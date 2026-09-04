"""Shared AES-256-GCM helpers for encrypting/decrypting the Polymarket private key at rest.

The private key is never stored in plaintext: config.yaml only ever holds a base64
blob (salt + nonce + tag + ciphertext). Decryption requires the password chosen when
the key was encrypted, and AES-GCM's authentication tag makes tampering or a wrong
password detectable rather than silently returning garbage.
"""

import base64
import re

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes

PBKDF2_ITERATIONS = 200_000
SALT_LEN = 16
NONCE_LEN = 12
TAG_LEN = 16
KEY_LEN = 32  # AES-256

PRIVATE_KEY_RE = re.compile(r"0x[0-9a-fA-F]{64}")


def normalize_private_key(key: str) -> str:
    key = key.strip()
    return key if key.startswith("0x") else "0x" + key


def verify_private_key(key: str) -> bool:
    """Checks that a (decrypted) string is a well-formed 32-byte hex private key."""
    return bool(PRIVATE_KEY_RE.fullmatch(normalize_private_key(key)))


def _derive_key(password: str, salt: bytes) -> bytes:
    return PBKDF2(password.encode("utf-8"), salt, dkLen=KEY_LEN, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)


def encrypt_private_key(private_key: str, password: str) -> str:
    """Encrypts private_key with password, returning a base64 string safe for config.yaml."""
    salt = get_random_bytes(SALT_LEN)
    nonce = get_random_bytes(NONCE_LEN)
    key = _derive_key(password, salt)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(private_key.encode("utf-8"))
    return base64.b64encode(salt + nonce + tag + ciphertext).decode("ascii")


def decrypt_private_key(encoded_blob: str, password: str) -> str:
    """Decrypts a blob produced by encrypt_private_key. Raises ValueError on wrong password/corrupt data."""
    try:
        blob = base64.b64decode(encoded_blob, validate=True)
    except Exception as e:
        raise ValueError("Encrypted key is not valid base64.") from e

    if len(blob) < SALT_LEN + NONCE_LEN + TAG_LEN:
        raise ValueError("Encrypted key blob is too short/corrupted.")

    salt = blob[:SALT_LEN]
    nonce = blob[SALT_LEN:SALT_LEN + NONCE_LEN]
    tag = blob[SALT_LEN + NONCE_LEN:SALT_LEN + NONCE_LEN + TAG_LEN]
    ciphertext = blob[SALT_LEN + NONCE_LEN + TAG_LEN:]

    key = _derive_key(password, salt)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    try:
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as e:
        raise ValueError("Wrong password or corrupted/tampered encrypted key.") from e
    return plaintext.decode("utf-8")
