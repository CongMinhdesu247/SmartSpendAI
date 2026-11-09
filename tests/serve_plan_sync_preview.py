"""Disposable mobile QA fixture. AI is stubbed; no real credentials or data."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='smartspend-plan-sync-') as folder:
        os.environ.update(SMARTSPEND_DATA_DIR=folder, SMARTSPEND_CLOUD='0', SMARTSPEND_ACCOUNTS='0',
            SMARTSPEND_PASSWORD_HASH='', SMARTSPEND_SESSION_SECRET='disposable-plan-preview-' * 3,
            DATABASE_URL='', GEMINI_API_KEY='')
        os.environ.pop('RENDER_EXTERNAL_URL', None)
        os.environ.pop('SMARTSPEND_PUBLIC_URL', None)
        from backend.api_server import app
        fixture = {'title': 'Kế hoạch kiểm tra đồng bộ', 'plan_type': 'meal', 'total_budget': 500000,
            'estimated_cost': 80000, 'region': 'TP. Hồ Chí Minh', 'advice': 'Dữ liệu kiểm thử, AI giả lập.',
            'items': [{'category': 'grocery', 'time_or_day': 'Đi chợ', 'name': 'Cá (500g)',
                       'details': 'Mục có giá để kiểm tra ghi chi.', 'price': 80000},
                      {'category': 'daily_menu', 'time_or_day': 'Ngày 1', 'name': 'Cá kho và cơm',
                       'details': 'Nguyên liệu đã tính trong giỏ đi chợ.', 'price': 0}]}
        import uvicorn
        with patch('backend.api_server.generate_smart_plan', return_value=fixture):
            uvicorn.run(app, host='127.0.0.1', port=8769)
