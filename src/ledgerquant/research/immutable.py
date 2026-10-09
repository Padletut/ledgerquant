"""Write one complete, non-overwriting research artifact directory."""

import os
from pathlib import Path
import shutil
import tempfile

from .contracts import ContractError


def publish_directory(output_dir: Path, files: dict[str, bytes]) -> None:
    if output_dir.exists():
        raise ContractError(f"artifact output already exists: {output_dir}")
    if not files or any(Path(name).name != name for name in files):
        raise ContractError("artifact filenames must be simple basenames")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        for name, payload in files.items():
            (temporary / name).write_bytes(payload)
        if output_dir.exists():
            raise ContractError(f"artifact output already exists: {output_dir}")
        os.rename(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
