"""Create the two local Compose secrets without replacing existing values."""

import os
import secrets
from pathlib import Path


def main() -> None:
    directory = Path(__file__).resolve().parents[1] / "credentials"
    directory.mkdir(mode=0o700, exist_ok=True)
    for name in ("postgres.pwd", "collector-token.txt"):
        path = directory / name
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(secrets.token_urlsafe(48) + "\n")
        print(f"Created {path.name}")


if __name__ == "__main__":
    main()
