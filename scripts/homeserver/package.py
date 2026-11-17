"""Create an allowlisted source archive, excluding local data and credentials."""

import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def package():
    output = ROOT / "output" / "deployment" / "SmartSpendAI-hp.tar.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [
        ROOT / name
        for name in (
            "Dockerfile.hp",
            "compose.yaml",
            ".dockerignore",
            ".env.example",
            "requirements/homeserver.lock.txt",
            "requirements/server.txt",
            "docs/hp-home-server.md",
            "docs/hp-verification.md",
        )
    ]
    for folder in ("backend", "frontend", "scripts/homeserver"):
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and "__pycache__" not in p.parts
            and p.suffix not in (".pyc", ".db", ".env")
        )
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(files):
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    with tarfile.open(output) as archive:
        names = set(archive.getnames())
        if {".env", ".env.cloud", "config.json", "smartspend_local.db"} & names:
            raise RuntimeError("Private file detected in archive")
    print(output)


if __name__ == "__main__":
    package()
