import os
import unittest
from unittest.mock import patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.access import AccessSettings, install_access, password_hasher
from backend.api_server import get_config, update_config, network_qr
from backend.finance_models import AccessSession
from migrate_cloud_data import transfer

TEST_PASSWORD = 'Only-for-isolated-tests-12345'
TEST_SECRET = 'test-session-secret-' * 4
ORIGIN = 'https://app.example'


def memory_engine():
    return create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)


class CloudAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = password_hasher.hash(TEST_PASSWORD)

    def setUp(self):
        self.engine = memory_engine()
        database.Base.metadata.create_all(self.engine)
        self.env = patch.dict(os.environ, {'SMARTSPEND_CLOUD': '1', 'SMARTSPEND_PASSWORD_HASH': self.password_hash,
            'SMARTSPEND_SESSION_SECRET': TEST_SECRET, 'SMARTSPEND_PUBLIC_URL': ORIGIN,
            'GEMINI_API_KEY': 'never-return-this-test-key', 'DATABASE_URL': 'postgresql://test:never-return-this-password@db.example/postgres'})
        self.env.start()
        self.database_patch = patch.object(database, 'engine', self.engine)
        self.database_patch.start()
        app = FastAPI()
        self.settings = AccessSettings(True, self.password_hash, TEST_SECRET, ORIGIN)
        self.settings.validate()
        install_access(app, self.settings)
        @app.get('/api/private')
        def private(): return {'private': True}
        @app.post('/api/private')
        def write_private(): return {'saved': True}
        @app.get('/healthz')
        def health(): return {'status': 'ok'}
        app.add_api_route('/api/config', get_config, methods=['GET'])
        app.add_api_route('/api/config', update_config, methods=['POST'])
        app.add_api_route('/api/network-qr', network_qr, methods=['GET'])
        self.client = TestClient(app, base_url=ORIGIN)

    def tearDown(self):
        self.client.close(); self.database_patch.stop(); self.env.stop(); self.engine.dispose()

    def login(self):
        response = self.client.post('/api/auth/login', json={'password': TEST_PASSWORD}, headers={'Origin': ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_anonymous_private_data_is_blocked_and_health_is_public(self):
        for path in ('/api/private', '/api/config', '/api/network-qr'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get('/healthz').status_code, 200)
        self.assertFalse(self.client.get('/api/auth/status').json()['authenticated'])
        spoof = self.client.get('/api/private', headers={'X-Forwarded-For': '127.0.0.1', 'X-Forwarded-Host': 'localhost'})
        self.assertEqual(spoof.status_code, 401)
        self.assertEqual(self.client.get('/api/auth/status', headers={'Host': 'evil.example'}).status_code, 400)

    def test_login_cookie_csrf_and_server_side_logout_revocation(self):
        response = self.login()
        cookie = response.headers['set-cookie'].lower()
        self.assertIn('httponly', cookie); self.assertIn('secure', cookie); self.assertIn('samesite=strict', cookie)
        self.assertEqual(self.client.get('/api/private').status_code, 200)
        stale_cookie = self.client.cookies.get('smartspend_session')
        self.assertEqual(self.client.post('/api/private', headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/private', headers={'Origin': ORIGIN}).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'Origin': ORIGIN}).status_code, 200)
        self.assertEqual(self.client.get('/api/private', headers={'Cookie': 'smartspend_session=' + stale_cookie}).status_code, 401)

    def test_secrets_not_returned_cloud_config_locked_qr_first_party(self):
        self.login()
        response = self.client.get('/api/config')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('never-return-this', response.text)
        self.assertNotIn('gemini_api_key', response.json())
        self.assertNotIn('database_url', response.json())
        self.assertFalse(response.json()['can_edit_config'])
        self.assertEqual(self.client.post('/api/config', json={}, headers={'Origin': ORIGIN}).status_code, 403)
        svg = self.client.get('/api/network-qr')
        self.assertEqual(svg.status_code, 200)
        self.assertIn('image/svg+xml', svg.headers['content-type'])
        self.assertNotIn('api.qrserver.com', svg.text)

    def test_brute_force_limit_and_bad_login_origin(self):
        self.assertEqual(self.client.post('/api/auth/login', json={'password': TEST_PASSWORD}, headers={'Origin': 'https://evil.example'}).status_code, 403)
        for _ in range(8):
            self.assertEqual(self.client.post('/api/auth/login', json={'password': 'wrong'}, headers={'Origin': ORIGIN}).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login', json={'password': TEST_PASSWORD}, headers={'Origin': ORIGIN}).status_code, 429)

    def test_password_version_invalidates_existing_session(self):
        self.login()
        with Session(self.engine) as db:
            row = db.query(AccessSession).first(); row.password_version = 'different-password-version'; db.commit()
        self.assertEqual(self.client.get('/api/private').status_code, 401)

    def test_cloud_never_falls_back_to_ephemeral_sqlite(self):
        with patch.dict(os.environ, {'DATABASE_URL': '', 'SMARTSPEND_CLOUD': '1'}):
            with self.assertRaises(RuntimeError): database.init_db_connection()
        with patch.dict(os.environ, {'SMARTSPEND_PASSWORD_HASH': ''}):
            with self.assertRaises(RuntimeError): AccessSettings.from_environment().validate()


class CloudTransferTests(unittest.TestCase):
    def test_copy_preserves_local_data_ids_and_is_idempotent(self):
        source, target = memory_engine(), memory_engine()
        try:
            database.Base.metadata.create_all(source)
            with Session(source) as db:
                plan = models.Plan(id=14, title='Giữ dữ liệu cũ', plan_type='meal', total_budget=500000, estimated_cost=80000, actual_spent=80000)
                plan.items = [models.PlanItem(id=23, name='Cá', category='grocery', price=80000, is_completed=True)]
                db.add(plan); db.commit()
            report = transfer(source, target, 'test-fingerprint')
            self.assertEqual(report['imported']['plans'], 1)
            with Session(target) as db:
                self.assertEqual(db.get(models.Plan, 14).title, 'Giữ dữ liệu cũ')
                self.assertTrue(db.get(models.PlanItem, 23).is_completed)
            self.assertTrue(transfer(source, target, 'test-fingerprint')['already_imported'])
            with self.assertRaises(ValueError): transfer(source, target, 'another-source')
            with Session(source) as db:
                self.assertEqual(db.get(models.Plan, 14).actual_spent, 80000)
        finally:
            source.dispose(); target.dispose()

    def test_postgres_url_uses_installed_driver_and_encodes_raw_at_password(self):
        normalized = database.normalize_database_url('postgresql://owner:pa@ss#word@pool.example:5432/postgres')
        parsed = make_url(normalized)
        self.assertEqual(parsed.drivername, 'postgresql+psycopg2')
        self.assertEqual(parsed.password, 'pa@ss#word')
        self.assertEqual(parsed.host, 'pool.example')
