"""Isolated login UI QA; fixture password is not a production credential."""
import os
import runpy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pwdlib import PasswordHash

if __name__ == '__main__':
    os.environ['SMARTSPEND_CLOUD'] = '0'
    os.environ['SMARTSPEND_PASSWORD_HASH'] = PasswordHash.recommended().hash('Only-for-isolated-browser-tests-12345')
    os.environ['SMARTSPEND_SESSION_SECRET'] = 'isolated-browser-test-secret-' * 3
    runpy.run_path(str(Path(__file__).with_name('serve_preview.py')), run_name='__main__')
