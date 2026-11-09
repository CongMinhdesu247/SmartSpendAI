"""Local UI fixture stored under ignored output/accounts-preview, never production. Password below is only for this preview."""
import os
import sys
from contextlib import nullcontext
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    preview_dir = Path(__file__).resolve().parents[1] / 'output' / 'accounts-preview'
    preview_dir.mkdir(parents=True, exist_ok=True)
    with nullcontext(str(preview_dir)) as folder:
        os.environ.update(SMARTSPEND_DATA_DIR=folder, SMARTSPEND_CLOUD="0", SMARTSPEND_ACCOUNTS="1",
                          SMARTSPEND_SESSION_SECRET="disposable-preview-secret-" * 3, DATABASE_URL="", GEMINI_API_KEY="")
        os.environ.pop("RENDER_EXTERNAL_URL", None)
        os.environ.pop("SMARTSPEND_PUBLIC_URL", None)
        from backend import database
        from backend.access import password_hasher
        password = "Only-for-isolated-browser-tests-12345"
        os.environ["SMARTSPEND_PASSWORD_HASH"] = password_hasher.hash(password)
        from backend.api_server import app
        from backend.finance_models import Account
        from backend.tenancy import OWNER_ID
        from sqlalchemy.orm import Session
        database._init_sqlite_fallback()
        with Session(database.engine) as db:
            if not db.get(Account, OWNER_ID):
                db.add(Account(id=OWNER_ID, username="chuso", password_hash=os.environ["SMARTSPEND_PASSWORD_HASH"]))
            db.commit()
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8767)
