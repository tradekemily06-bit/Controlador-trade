from __future__ import annotations

import getpass

from security.local_auth import LocalAuth


def main() -> None:
    password = getpass.getpass("Password (12-256 chars): ")
    print(LocalAuth.hash_password(password))


if __name__ == "__main__":
    main()
