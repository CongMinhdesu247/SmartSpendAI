"""Interactive setup inside the built image; never print credentials."""

import argparse
import getpass
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from pwdlib import PasswordHash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="/setup/.env")
    args = parser.parse_args()
    path = Path(args.path)
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip("'")
    if values.get("SMARTSPEND_DB_PASSWORD"):
        raise SystemExit("Already configured. Edit .env manually; do not regenerate DB passwords.")
    port = input("Host port [8092]: ").strip() or "8092"
    if not port.isdigit() or not 1024 <= int(port) <= 65535:
        raise SystemExit("Port must be between 1024 and 65535.")
    url = (
        input("Actual HTTPS origin (temporary placeholder allowed before tunnel setup): ")
        .strip()
        .rstrip("/")
    )
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise SystemExit("Expected an HTTPS origin without a path or credentials.")
    password = getpass.getpass("New chuso password (12-128 characters): ")
    if not 12 <= len(password) <= 128 or password != getpass.getpass("Repeat password: "):
        raise SystemExit("Password length or confirmation is invalid.")
    api_key = getpass.getpass("Gemini API key (Enter to configure later): ")
    values.update(
        SMARTSPEND_HTTP_PORT=port,
        SMARTSPEND_PUBLIC_URL=url,
        SMARTSPEND_DB_PASSWORD=secrets.token_hex(32),
        SMARTSPEND_DB_ADMIN_PASSWORD=secrets.token_hex(32),
        SMARTSPEND_PASSWORD_HASH=PasswordHash.recommended().hash(password),
        SMARTSPEND_SESSION_SECRET=secrets.token_urlsafe(48),
        GEMINI_API_KEY=api_key,
    )
    if any("\n" in value or "\r" in value for value in values.values()):
        raise SystemExit("Configuration values must be single-line.")
    os.umask(0o077)
    temporary = path.with_suffix(".tmp")
    # Compose single quotes preserve the dollar signs in Argon2 hashes.
    lines = []
    for key, value in values.items():
        escaped = value.replace("'", "\\'")
        lines.append(f"{key}='{escaped}'\n")
    temporary.write_text("".join(lines), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    print("Saved private .env. Login username: chuso. No credentials printed.")


if __name__ == "__main__":
    main()
