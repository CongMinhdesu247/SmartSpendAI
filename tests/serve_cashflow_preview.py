"""Isolated chart QA: expense -> income -> above budget -> income recovery."""

import os
import sys
import tempfile
from pathlib import Path
from datetime import date
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="smartspend-chart-") as folder:
        os.environ.update(
            SMARTSPEND_DATA_DIR=folder,
            SMARTSPEND_CLOUD="0",
            SMARTSPEND_ACCOUNTS="1",
            SMARTSPEND_SESSION_SECRET="isolated-chart-secret-" * 4,
            DATABASE_URL="",
            GEMINI_API_KEY="",
        )
        os.environ.pop("RENDER_EXTERNAL_URL", None)
        os.environ.pop("SMARTSPEND_PUBLIC_URL", None)
        from backend.access import password_hasher

        os.environ["SMARTSPEND_PASSWORD_HASH"] = password_hasher.hash(
            "Only-for-isolated-browser-tests-12345"
        )
        from backend import database
        from backend.api_server import app
        from backend.finance_api import initialize_finance
        from backend.finance_models import Account, Category, Transaction, Budget
        from backend.tenancy import OWNER_ID
        from sqlalchemy.orm import Session

        database._init_sqlite_fallback()
        initialize_finance(database.engine)
        today = date.today()
        with Session(database.engine) as db:
            db.add(
                Account(
                    id=OWNER_ID,
                    username="chuso",
                    password_hash=os.environ["SMARTSPEND_PASSWORD_HASH"],
                )
            )
            category = db.query(Category).first()
            for day, kind, amount in [
                (1, "expense", 700000),
                (2, "income", 200000),
                (3, "expense", 600000),
                (4, "income", 300000),
            ]:
                db.add(
                    Transaction(
                        client_id=str(uuid4()),
                        title="Giao dịch thử biểu đồ",
                        kind=kind,
                        amount=amount,
                        category_id=category.id,
                        spent_on=date(today.year, today.month, day),
                    )
                )
            db.add(Budget(key=f"{today:%Y-%m}:all", month=today.replace(day=1), amount=1000000))
            db.commit()
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=8768)
