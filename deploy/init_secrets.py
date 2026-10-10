"""Create local Compose secrets without replacing existing values."""

import os
import secrets
from pathlib import Path


def main() -> None:
    directory = Path(__file__).resolve().parents[1] / "credentials"
    directory.mkdir(mode=0o700, exist_ok=True)
    for name in ("postgres.pwd", "collector-token.txt", "shadow-worker.pwd", "pgadmin.pwd"):
        path = directory / name
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(secrets.token_urlsafe(48) + "\n")
        print(f"Created {path.name}")
    # Optional provider keys are supplied by the operator. An empty file keeps Compose
    # startable; the news service then runs without FRED.
    for name in ("fred-api.key",):
        path = directory / name
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            print(f"Created empty {path.name}; add the key to enable it")
        except FileExistsError:
            continue


if __name__ == "__main__":
    main()
