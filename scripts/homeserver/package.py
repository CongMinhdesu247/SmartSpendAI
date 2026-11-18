"""Create an allowlisted source archive with LF-normalized Linux scripts, excluding credentials."""

import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LF_EXTENSIONS = {".sh", ".yml", ".yaml", ".conf", ".Caddyfile"}


def _needs_lf(rel_posix: str, path: Path) -> bool:
    return (
        path.suffix in LF_EXTENSIONS
        or path.name.startswith("Dockerfile")
        or path.name.endswith("Caddyfile")
        or rel_posix.startswith("scripts/homeserver/")
    )


def package():
    output = ROOT / "output" / "deployment" / "SmartSpendAI-hp.tar.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    required_files = [
        ROOT / name
        for name in (
            "Dockerfile.hp",
            "compose.yaml",
            ".dockerignore",
            ".env.example",
            "requirements/homeserver.lock.txt",
            "requirements/server.txt",
            "docs/guides/hp-home-server.md",
            "docs/reports/hp-verification.md",
        )
    ]
    optional_files = [
        ROOT / name
        for name in (
            "SERVER_CONTEXT.md",
            "docs/reports/project-audit-and-improvements.md",
        )
        if (ROOT / name).is_file()
    ]
    files = [*required_files, *optional_files]
    for folder in ("backend", "frontend", "scripts/homeserver", "deploy/local-server"):
        folder_path = ROOT / folder
        if not folder_path.is_dir():
            continue
        files.extend(
            p
            for p in folder_path.rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and "__pycache__" not in p.parts
            and not p.name.endswith((".pyc", ".db", ".db-wal", ".db-shm", ".env"))
        )

    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(set(files)):
            rel = path.relative_to(ROOT).as_posix()
            if _needs_lf(rel, path) and path.suffix != ".ps1":
                raw = path.read_bytes().replace(b"\r\n", b"\n")
                info = archive.gettarinfo(str(path), arcname=rel)
                info.size = len(raw)
                if path.suffix == ".sh":
                    info.mode = 0o755
                archive.addfile(info, io.BytesIO(raw))
            else:
                archive.add(path, arcname=rel, recursive=False)

    with tarfile.open(output) as archive:
        names = set(archive.getnames())
        if {".env", ".env.cloud", "config.json", "smartspend_local.db"} & names:
            raise RuntimeError("Private file detected in archive")
    print(output)


if __name__ == "__main__":
    package()
