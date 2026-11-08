"""Run: python -m unittest discover -s tests -v. Never uses configured databases."""
import unittest
import tempfile
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, create_mock_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.api_server import app
from backend.finance_api import initialize_finance


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        database.Base.metadata.create_all(self.engine)
        initialize_finance(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        def dependency():
            with self.sessions() as session:
                yield session
        app.dependency_overrides[database.get_db] = dependency
        self.client = TestClient(app)
        self.categories = self.client.get('/api/finance/categories').json()
        self.category = self.categories[0]['id']

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def post(self, path, payload):
        response = self.client.post('/api/finance' + path, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def expense(self, **values):
        payload = dict(client_id=str(uuid4()), title='Ăn sáng', amount=35000, kind='expense', spent_on='2026-11-08', category_id=self.category, note='')
        payload.update(values)
        return payload

    def test_ledger_month_filter_edit_undo_and_large_money(self):
        payload = self.expense()
        row = self.post('/transactions', payload)
        self.assertEqual(self.post('/transactions', payload)['id'], row['id'])
        self.assertEqual(self.client.post('/api/finance/transactions', json={**payload, 'amount': 36000}).status_code, 409)
        self.post('/transactions', self.expense(title='Lương', kind='income', amount=9_000_000_000_000))
        self.post('/transactions', self.expense(spent_on='2026-10-31', amount=12000))
        overview = self.client.get('/api/finance/overview?month=2026-11').json()
        self.assertEqual((overview['expense'], overview['income']), (35000, 9_000_000_000_000))
        self.assertEqual(self.client.put('/api/finance/budgets/2026-11', json={'amount': 100000}).status_code, 200)
        self.assertEqual(self.client.get('/api/finance/overview?month=2026-11').json()['remaining'], 65000)
        edited = {**payload, 'amount': 42000}
        self.assertEqual(self.client.put(f"/api/finance/transactions/{row['id']}", json=edited).status_code, 200)
        self.assertEqual(self.client.get('/api/finance/transactions?month=2026-11&q=%').json()['total'], 0)
        self.assertEqual(self.client.get('/api/finance/transactions?month=2026-11&q=Ăn').json()['total'], 1)
        self.assertEqual(self.client.get('/api/finance/transactions?month=2026-11&q=an%20sang').json()['total'], 1)
        self.client.delete(f"/api/finance/transactions/{row['id']}")
        self.assertEqual(self.client.get('/api/finance/overview?month=2026-11').json()['expense'], 0)
        self.post(f"/transactions/{row['id']}/restore", {})
        self.assertEqual(self.client.get('/api/finance/overview?month=2026-11').json()['expense'], 42000)

    def test_validation_and_category_archive(self):
        for values in ({'amount': 0}, {'amount': -1}, {'amount': 1.2}, {'amount': True}, {'title': '  '}, {'category_id': 99999}, {'spent_on': '2026-02-30'}):
            self.assertGreaterEqual(self.client.post('/api/finance/transactions', json=self.expense(**values)).status_code, 400)
        for month in ('2026-13', '26-1', '2026-11-01', ''):
            self.assertEqual(self.client.get('/api/finance/overview', params={'month': month}).status_code, 422)
        custom = self.post('/categories', {'name': 'Thú cưng', 'color': 'teal'})
        self.assertEqual(self.client.post('/api/finance/categories', json={'name': 'THÚ CƯNG'}).status_code, 409)
        self.client.delete(f"/api/finance/categories/{custom['id']}")
        self.assertEqual(self.client.post('/api/finance/transactions', json=self.expense(category_id=custom['id'])).status_code, 409)
        self.assertEqual(self.post('/categories', {'name': 'Thú cưng'})['id'], custom['id'])

    def test_recurring_month_end_duplicate_payment_and_edit(self):
        bill = self.post('/recurring', {'name': 'Internet', 'amount': 200000, 'category_id': self.category, 'frequency': 'monthly', 'next_due': '2027-01-31'})
        payment = {'due_on': '2027-01-31', 'spent_on': '2027-01-30'}
        first = self.post(f"/recurring/{bill['id']}/pay", payment)
        self.assertEqual(self.post(f"/recurring/{bill['id']}/pay", payment)['id'], first['id'])
        self.assertEqual(self.client.get('/api/finance/recurring').json()[0]['next_due'], '2027-02-28')
        self.post(f"/recurring/{bill['id']}/pay", {'due_on': '2027-02-28', 'spent_on': '2027-02-28'})
        self.assertEqual(self.client.get('/api/finance/recurring').json()[0]['next_due'], '2027-03-31')
        update = {key: first[key] for key in ('client_id', 'title', 'amount', 'kind', 'spent_on', 'category_id', 'note', 'source_item_id')}
        update['amount'] = 210000
        self.assertEqual(self.client.put(f"/api/finance/transactions/{first['id']}", json=update).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/finance/categories/{self.category}').status_code, 409)

    def test_goals_preferences_and_idempotent_contributions(self):
        goal = self.post('/goals', {'name': 'Du lịch', 'target': 5000000, 'deadline': '2027-03-01'})
        contribution = {'client_id': str(uuid4()), 'amount': 500000, 'saved_on': '2026-11-08'}
        saved = self.post(f"/goals/{goal['id']}/contributions", contribution)
        self.assertEqual(self.post(f"/goals/{goal['id']}/contributions", contribution)['id'], saved['id'])
        self.assertEqual(self.client.get('/api/finance/goals').json()[0]['saved'], 500000)
        self.assertEqual(self.client.get('/api/finance/overview?month=2026-11').json()['expense'], 0)
        self.client.delete(f"/api/finance/contributions/{saved['id']}")
        self.assertEqual(self.client.get('/api/finance/goals').json()[0]['saved'], 0)
        self.client.put('/api/finance/preferences', json={'people': '3 người', 'tastes': 'Ít cay', 'avoid': 'Tôm'})
        self.assertEqual(self.client.get('/api/finance/preferences').json()['avoid'], 'Tôm')

    def make_plan(self):
        with self.sessions() as db:
            plan = models.Plan(title='Tuần này', plan_type='meal', total_budget=500000, estimated_cost=80000, actual_spent=80000, region='TP.HCM')
            plan.items = [models.PlanItem(name='Cá', category='grocery', time_or_day='Đi chợ', price=80000, is_completed=True)]
            db.add(plan); db.commit()
            return plan.id, plan.items[0].id

    def test_completion_is_not_payment_copy_and_delete_preserve_ledger(self):
        plan_id, item_id = self.make_plan()
        original = self.client.get(f'/api/plans/{plan_id}').json()
        self.assertTrue(original['items'][0]['is_completed'])
        self.assertEqual(original['actual_spent'], 0)
        transaction = self.post('/transactions', self.expense(title='Mua cá', amount=85000, source_item_id=item_id))
        self.assertEqual(self.client.get(f'/api/plans/{plan_id}').json()['actual_spent'], 85000)
        self.client.patch(f'/api/items/{item_id}', json={'is_completed': False, 'price': 90000})
        self.assertEqual(self.client.get(f'/api/plans/{plan_id}').json()['actual_spent'], 85000)
        copied = self.client.post(f'/api/plans/{plan_id}/copy').json()
        self.assertEqual(copied['actual_spent'], 0)
        self.assertFalse(copied['items'][0]['is_completed'])
        self.assertIsNone(copied['items'][0]['payment'])
        archive = self.client.delete(f'/api/plans/{plan_id}').json()
        kept = self.client.get(f"/api/finance/transactions/{transaction['id']}").json()
        self.assertEqual(kept['amount'], 85000)
        self.assertIsNone(kept['source_item_id'])
        restored = self.client.post(f"/api/plans/trash/{archive['undo_id']}/restore").json()
        self.assertEqual(restored['actual_spent'], 85000)
        self.assertEqual(self.client.get('/api/finance/overview?month=2026-11').json()['expense'], 85000)
        repeated = self.client.post(f"/api/plans/trash/{archive['undo_id']}/restore").json()
        self.assertEqual(repeated['id'], restored['id'])

    def test_ai_preferences_pantry_replacement_and_paid_guard(self):
        self.client.put('/api/finance/preferences', json={'tastes': 'Cá', 'avoid': 'Tôm', 'people': '2 người'})
        result = {'title': 'AI', 'plan_type': 'meal', 'total_budget': 500000, 'estimated_cost': 10000, 'region': 'TP.HCM', 'advice': 'Giá ước tính', 'items': [{'category': 'grocery', 'name': 'Rau', 'time_or_day': 'Đi chợ', 'details': '', 'price': 10000}]}
        with patch('backend.api_server.generate_smart_plan', return_value=result) as generate:
            response = self.client.post('/api/plans/generate', json={'pantry': 'Gạo', 'preferences': 'Nấu nhanh'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn('Gạo', generate.call_args.kwargs['preferences'])
            self.assertIn('Tôm', generate.call_args.kwargs['preferences'])
        item_id = response.json()['items'][0]['id']
        with patch('backend.api_server.suggest_replacement', return_value={'name': 'Rau cải', 'details': '1 bó', 'price': 12000}):
            self.assertEqual(self.client.post(f'/api/items/{item_id}/replace', json={}).status_code, 200)
        self.post('/transactions', self.expense(source_item_id=item_id))
        self.assertEqual(self.client.post(f'/api/items/{item_id}/replace', json={}).status_code, 409)

    def test_additive_schema_and_seed_are_repeatable(self):
        plan_id, _ = self.make_plan()
        before = [c['name'] for c in inspect(self.engine).get_columns('plans')]
        database.Base.metadata.create_all(self.engine)
        initialize_finance(self.engine)
        self.assertEqual(before, [c['name'] for c in inspect(self.engine).get_columns('plans')])
        self.assertEqual(len(self.client.get('/api/finance/categories').json()), 9)
        self.assertEqual(self.client.get(f'/api/plans/{plan_id}').json()['title'], 'Tuần này')

    def test_populated_legacy_sqlite_upgrade_creates_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'legacy.db')
            url = f'sqlite:///{path.as_posix()}'
            legacy = create_engine(url)
            models.Plan.__table__.create(legacy)
            models.PlanItem.__table__.create(legacy)
            with legacy.begin() as connection:
                connection.execute(models.Plan.__table__.insert().values(id=1, title='Giữ nguyên', plan_type='meal', total_budget=500000, estimated_cost=80000, actual_spent=80000, region='Hà Nội'))
                connection.execute(models.PlanItem.__table__.insert().values(id=1, plan_id=1, category='grocery', name='Cá', price=80000, is_completed=True))
            columns = [column['name'] for column in inspect(legacy).get_columns('plans')]
            legacy.dispose()
            with patch.object(database, 'DEFAULT_SQLITE_URL', url), patch.object(database, 'engine', None), patch.object(database, 'SessionLocal', None):
                database._init_sqlite_fallback()
                initialize_finance(database.engine)
                self.assertEqual(columns, [column['name'] for column in inspect(database.engine).get_columns('plans')])
                database.engine.dispose()
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute('select title, actual_spent from plans').fetchone(), ('Giữ nguyên', 80000))
                self.assertEqual(connection.execute('select price, is_completed from plan_items').fetchone(), (80000, 1))
                self.assertEqual(connection.execute('select count(*) from spend_transactions').fetchone()[0], 0)
            with closing(sqlite3.connect(Path(folder, 'legacy.before_finance_v1.db'))) as backup:
                self.assertEqual(backup.execute('select title from plans').fetchone()[0], 'Giữ nguyên')
                self.assertNotIn('spend_transactions', [row[0] for row in backup.execute("select name from sqlite_master where type='table'")])

    def test_postgres_schema_compiles_with_rls_and_integer_money(self):
        statements = []
        mock = create_mock_engine('postgresql://', lambda sql, *args, **kwargs: statements.append(str(sql.compile(dialect=mock.dialect))))
        database.Base.metadata.create_all(mock, checkfirst=False)
        sql = '\n'.join(statements)
        for name in database.Base.metadata.tables:
            if name.startswith('spend_'):
                self.assertIn(f'ALTER TABLE {name} ENABLE ROW LEVEL SECURITY', sql)
        self.assertIn('amount BIGINT', sql)
        self.assertNotIn('ALTER TABLE plans', sql)

    def test_large_linked_payment_does_not_overflow_legacy_plan_column(self):
        plan_id, item_id = self.make_plan()
        self.post('/transactions', self.expense(amount=9_000_000_000_000, source_item_id=item_id))
        changed = self.client.patch(f'/api/items/{item_id}', json={'is_completed': False})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()['plan']['actual_spent'], 9_000_000_000_000)


if __name__ == '__main__':
    unittest.main()
