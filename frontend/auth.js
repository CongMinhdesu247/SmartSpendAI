/* Same-origin session login. The signed session cookie stays HttpOnly. */
(() => {
  const rawFetch = window.fetch.bind(window);
  const SEEN = 'smartspend-auth-seen';
  const LOGOUT_PENDING = 'smartspend-logout-pending';
  let resolveReady, ready = false, checking = false;
  let auth = { required: true, authenticated: false, cloud: false };
  window.smartspendAuthReady = new Promise(resolve => { resolveReady = resolve; });
  function read(key) { try { return localStorage.getItem(key); } catch (_) { return null; } }
  function write(key, value) { try { if (value == null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch (_) {} }
  function clearPrivateCache() {
    try { Object.keys(localStorage).filter(key => key.startsWith('smartspend-cache:')).forEach(key => localStorage.removeItem(key)); } catch (_) {}
    write(SEEN, null);
  }
  function gate(message = '') {
    document.documentElement.classList.remove('auth-pending');
    document.documentElement.classList.add('auth-locked');
    document.getElementById('authGate').classList.remove('hidden');
    document.getElementById('authLoading').classList.add('hidden');
    const error = document.getElementById('authError');
    error.textContent = message;
    error.classList.toggle('hidden', !message);
  }
  function unlock(data, offline = false) {
    auth = data;
    document.documentElement.classList.remove('auth-pending', 'auth-locked');
    document.getElementById('authGate').classList.add('hidden');
    document.getElementById('authLoading').classList.add('hidden');
    document.getElementById('logoutButton').classList.toggle('hidden', !data.required);
    if (!offline && data.required) write(SEEN, String(Date.now()));
    if (!ready) { ready = true; resolveReady(data); }
  }
  window.fetch = async (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : String(input), location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return rawFetch(input, options);
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(options.headers).forEach((value, key) => headers.set(key, value));
    headers.set('X-SmartSpend-Client', '1');
    const response = await rawFetch(input, { ...options, headers, credentials: 'same-origin' });
    if (response.status === 401 && !url.pathname.startsWith('/api/auth/')) {
      write(SEEN, null);
      gate('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    }
    return response;
  };
  async function checkAccess() {
    if (checking) return;
    checking = true;
    try {
      if (read(LOGOUT_PENDING)) {
        const ended = await window.fetch('/api/auth/logout', { method: 'POST' });
        if (!ended.ok && ended.status !== 401) throw new Error('Chưa hoàn tất đăng xuất. Hãy thử lại khi có mạng.');
        write(LOGOUT_PENDING, null);
      }
      const response = await window.fetch('/api/auth/status', { cache: 'no-store' });
      if (!response.ok) throw new Error('Chưa kết nối được máy chủ. Hãy thử lại.');
      const data = await response.json();
      auth = data;
      if (data.authenticated) unlock(data);
      else { write(SEEN, null); gate(); }
    } catch (error) {
      const last = Number(read(SEEN) || 0);
      if (!read(LOGOUT_PENDING) && last && Date.now() - last < 30 * 86400000) {
        unlock({ ...auth, required: true, authenticated: true }, true);
      } else gate(error.message || 'Cần kết nối Internet để đăng nhập lần đầu.');
    } finally { checking = false; }
  }
  window.retryAccess = checkAccess;
  window.submitAccessLogin = async event => {
    event.preventDefault();
    const button = document.getElementById('loginSubmitButton');
    button.disabled = true;
    try {
      const response = await window.fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: document.getElementById('accessPassword').value }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Chưa đăng nhập được. Hãy thử lại.');
      document.getElementById('accessPassword').value = '';
      write(LOGOUT_PENDING, null);
      const wasReady = ready;
      await checkAccess();
      if (wasReady && auth.authenticated) await Promise.all([window.refreshFinance?.(), window.loadPlansFromDB?.()]);
    } catch (error) { gate(error.message || 'Chưa kết nối được máy chủ. Hãy thử lại.'); }
    finally { button.disabled = false; }
  };
  window.logoutAccess = async () => {
    if (window.hasPendingExpenses?.()) {
      window.showToast?.('Hãy đồng bộ hoặc bỏ các khoản đang chờ trước khi đăng xuất.', true);
      return;
    }
    write(LOGOUT_PENDING, '1');
    clearPrivateCache();
    gate();
    try {
      const response = await window.fetch('/api/auth/logout', { method: 'POST' });
      if (!response.ok && response.status !== 401) throw new Error();
      write(LOGOUT_PENDING, null);
    } catch (_) { gate('Đã khóa giao diện trên thiết bị. Kết nối lại để kết thúc phiên trên máy chủ.'); }
    auth.authenticated = false;
  };
  document.addEventListener('DOMContentLoaded', checkAccess);
  window.addEventListener('online', checkAccess);
})();
