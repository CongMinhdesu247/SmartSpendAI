"""Prepare a secret-free source ZIP and private environment files for hosting."""

import argparse
import getpass
import os
from pathlib import Path
import secrets
import zipfile

from sqlalchemy.engine import make_url

from backend.access import password_hasher
from backend.database import load_config, normalize_database_url

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env.cloud"
OUTPUT = ROOT / "output" / "deployment"


def read_env(path=ENV_FILE):
    if not path.exists():
        return {}
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def prepare(interactive_password: bool = False):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    db_url = make_url(normalize_database_url(cfg.get("database_url", "")))
    if not db_url.drivername.startswith("postgresql"):
        raise ValueError("Cần cấu hình PostgreSQL trước khi chuẩn bị cloud")
    if db_url.query.get("sslmode") in (None, "disable", "allow", "prefer"):
        db_url = db_url.update_query_dict({"sslmode": "require"})
    values = read_env()
    if not values.get("SMARTSPEND_PASSWORD_HASH"):
        if interactive_password:
            password = getpass.getpass("Nhap mat khau chuso (toi thieu 12 ky tu): ").strip()
            if len(password) < 12 or password != getpass.getpass("Nhap lai mat khau: ").strip():
                raise ValueError("Mật khẩu xác nhận chưa khớp hoặc ngắn hơn 12 ký tự")
        else:
            password = secrets.token_urlsafe(18)
            print("Mat khau chuso moi (chi hien 1 lan, khong luu file plaintext):", password)
        values["SMARTSPEND_PASSWORD_HASH"] = password_hasher.hash(password)
    values.update(
        {
            "SMARTSPEND_CLOUD": "1",
            "DATABASE_URL": db_url.render_as_string(hide_password=False),
            "GEMINI_API_KEY": cfg.get("gemini_api_key", ""),
        }
    )
    values.setdefault("SMARTSPEND_ALLOW_REGISTRATION", "0")
    values.setdefault("SMARTSPEND_SESSION_SECRET", secrets.token_urlsafe(48))
    ENV_FILE.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8"
    )
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass
    files = [
        ROOT / name
        for name in ("Dockerfile", ".dockerignore", "requirements/server.txt", "render.yaml")
    ]
    for folder in ("backend", "frontend"):
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    archive = OUTPUT / "SmartSpend-cloud-source.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        assert not any(
            name.endswith((".db", ".env", "config.json")) or name.startswith("output/")
            for name in bundle.namelist()
        )
        for name in bundle.namelist():
            content = bundle.read(name)
            if any(value.encode() in content for value in values.values() if len(value) > 12):
                raise ValueError("Source ZIP chứa cấu hình riêng tư; dừng đóng gói")
    print("Da chuan bi source ZIP: output/deployment/SmartSpend-cloud-source.zip")
    print("Bien moi truong rieng tu: .env.cloud (khong commit/tai len kho ma nguon)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-password", action="store_true")
    cli_args = parser.parse_args()
    try:
        prepare(interactive_password=cli_args.prompt_password)
    except Exception as error:
        print("Chua chuan bi duoc cloud:", type(error).__name__)
        raise SystemExit(1)
