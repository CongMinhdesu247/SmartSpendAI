"""Disposable browser QA server: python tests/serve_preview.py (port 8767)."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='SmartSpendQA-') as folder:
        os.environ['SMARTSPEND_DATA_DIR'] = folder
        Path(folder, 'config.json').write_text(json.dumps({'gemini_api_key': '', 'database_url': ''}), encoding='utf-8')
        from backend import database, models
        from backend.finance_api import initialize_finance, today
        from backend.finance_models import Category, Budget, Goal, Contribution, RecurringBill, Transaction
        from uuid import uuid4
        database.init_db_connection()
        initialize_finance(database.engine)
        with database.SessionLocal() as db:
            categories = {c.name: c.id for c in db.query(Category)}
            day = today()
            month = day.replace(day=1)
            db.add(Budget(key=f'{day:%Y-%m}:all', month=month, amount=5000000))
            for title, amount, category, kind in [('Ăn sáng', 35000, 'Ăn uống', 'expense'), ('Đi chợ cuối tuần', 245000, 'Đi chợ', 'expense'), ('Cà phê cùng bạn', 55000, 'Đi chơi', 'expense'), ('Lương tháng', 12000000, 'Khác', 'income')]:
                db.add(Transaction(client_id=str(uuid4()), title=title, amount=amount, kind=kind, spent_on=day, category_id=categories[category]))
            goal = Goal(name='Chuyến đi Đà Lạt', target=5000000)
            db.add(goal); db.flush()
            db.add(Contribution(client_id=str(uuid4()), goal_id=goal.id, amount=1500000, saved_on=day))
            db.add(RecurringBill(name='Tiền Internet', amount=220000, category_id=categories['Nhà ở'], next_due=day, frequency='monthly', anchor_day=day.day))
            plan = models.Plan(title='Thực đơn tuần này', plan_type='meal', total_budget=500000, estimated_cost=150000, actual_spent=0, region='TP.HCM', advice='Ưu tiên rau củ theo mùa và tận dụng nguyên liệu đang có.')
            plan.items = [models.PlanItem(category='grocery', time_or_day='Thực phẩm', name='Thịt heo (500g)', details='Chia phần để nấu trong tuần.', price=80000), models.PlanItem(category='grocery', time_or_day='Rau củ', name='Rau củ theo mùa', details='Rau xanh, cà rốt và bí đỏ.', price=70000), models.PlanItem(category='daily_menu', time_or_day='Ngày 1', name='Cơm thịt kho, canh rau', details='Dùng nguyên liệu trong giỏ đi chợ.', price=0)]
            db.add(plan); db.commit()
        import uvicorn
        uvicorn.run('backend.api_server:app', host='127.0.0.1', port=8767)
