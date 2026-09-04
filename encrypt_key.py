import getpass
import sys

from key_crypto import encrypt_private_key, normalize_private_key, verify_private_key
from masked_input import masked_input


def main():
    private_key = masked_input("Enter your Polymarket private key (shown as *): ").strip()
    if not private_key:
        sys.exit("No private key entered.")
    if not verify_private_key(private_key):
        sys.exit("That doesn't look like a valid private key: expected 64 hex characters (optionally 0x-prefixed).")
    private_key = normalize_private_key(private_key)

    password = getpass.getpass("Choose a password to encrypt it with (input hidden): ")
    if not password:
        sys.exit("Password cannot be empty.")
    if getpass.getpass("Confirm password: ") != password:
        sys.exit("Passwords do not match.")

    encoded = encrypt_private_key(private_key, password)

    print("\nAdd this to config.yaml:\n")
    print("polymarket:")
    print(f"  encrypted_private_key: {encoded}")
    print(
        "\nconfig.yaml is already git-ignored. Remember your password \u2014 it is not stored "
        "anywhere and cannot be recovered if lost."
    )


if __name__ == "__main__":
    main()
