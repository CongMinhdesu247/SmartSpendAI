/* Same-origin session login. The signed session cookie stays HttpOnly. */
(() => {
  const rawFetch = window.fetch.bind(window);
  const SEEN = "smartspend-auth-seen";
  const ACCOUNT_EVENT = "smartspend-active-account";
  let registerMode = false;
  window.smartspendUserId = null;
  window.smartspendStorageKey = (key) => `${key}:user:${window.smartspendUserId || "locked"}`;
  const LOGOUT_PENDING = "smartspend-logout-pending";
  let resolveReady,
    ready = false,
    checking = false;
  let auth = { required: true, authenticated: false, cloud: false };
  window.smartspendAuthReady = new Promise((resolve) => {
    resolveReady = resolve;
  });
  function read(key) {
    try {
      return localStorage.getItem(key);
    } catch (_) {
      return null;
    }
  }
  function write(key, value) {
    try {
      if (value == null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (_) {}
  }
  function clearPrivateCache() {
    try {
      Object.keys(localStorage)
        .filter((key) => key.startsWith("smartspend-cache:"))
        .forEach((key) => localStorage.removeItem(key));
    } catch (_) {}
    write(SEEN, null);
  }
  function gate(message = "") {
    document.documentElement.classList.remove("auth-pending");
    document.documentElement.classList.add("auth-locked");
    document.getElementById("authGate").classList.remove("hidden");
    document.getElementById("accountFields").classList.toggle("hidden", !auth.accounts);
    document.getElementById("accountToggle").classList.toggle("hidden", !auth.accounts);
    document.getElementById("accountName").textContent = "";
    document.getElementById("accessUsername").required = !!auth.accounts;
    document.getElementById("authLoading").classList.add("hidden");
    const error = document.getElementById("authError");
    error.textContent = message;
    error.classList.toggle("hidden", !message);
  }
  function unlock(data, offline = false) {
    auth = data;
    window.smartspendUserId = data.user?.id || "legacy-owner";
    document.getElementById("accountName").textContent = data.user?.username || "";
    write(ACCOUNT_EVENT, window.smartspendUserId);
    window.migrateLegacyExpenseOutbox?.();
    document.documentElement.classList.remove("auth-pending", "auth-locked");
    document.getElementById("authGate").classList.add("hidden");
    document.getElementById("authLoading").classList.add("hidden");
    document.getElementById("logoutButton").classList.toggle("hidden", !data.required);
    if (!offline && data.required) write(SEEN, String(Date.now()));
    if (!ready) {
      ready = true;
      resolveReady(data);
    }
  }
  window.fetch = async (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : String(input), location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/"))
      return rawFetch(input, options);
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(options.headers).forEach((value, key) => headers.set(key, value));
    headers.set("X-SmartSpend-Client", "1");
    if (window.smartspendUserId) headers.set("X-SmartSpend-User", window.smartspendUserId);
    const response = await rawFetch(input, { ...options, headers, credentials: "same-origin" });
    if (response.status === 401 && !url.pathname.startsWith("/api/auth/")) {
      write(SEEN, null);
      gate("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    }
    if (response.status === 409 && !url.pathname.startsWith("/api/auth/")) {
      const data = await response
        .clone()
        .json()
        .catch(() => ({}));
      if (data.code === "ACCOUNT_CHANGED") {
        gate(data.detail);
        window.smartspendUserId = null;
      }
    }
    return response;
  };
  async function checkAccess() {
    if (checking) return;
    checking = true;
    try {
      const response = await window.fetch("/api/auth/status", { cache: "no-store" });
      if (!response.ok) throw new Error("Chưa kết nối được máy chủ. Hãy thử lại.");
      const data = await response.json();
      auth = data;
      const pending = read(LOGOUT_PENDING);
      if (
        pending &&
        data.authenticated &&
        (pending === data.user?.id || (pending === "1" && data.user?.id === "legacy-owner"))
      ) {
        const ended = await window.fetch("/api/auth/logout", {
          method: "POST",
          headers: { "X-SmartSpend-User": data.user.id },
        });
        if (!ended.ok && ended.status !== 401)
          throw new Error("Chưa hoàn tất đăng xuất. Hãy thử lại khi có mạng.");
        write(LOGOUT_PENDING, null);
        location.reload();
        return;
      }
      write(LOGOUT_PENDING, null);
      if (data.authenticated) unlock(data);
      else {
        write(SEEN, null);
        gate();
      }
    } catch (error) {
      gate(error.message || "Cần kết nối Internet để xác nhận tài khoản.");
    } finally {
      checking = false;
    }
  }
  window.retryAccess = checkAccess;
  window.submitAccessLogin = async (event) => {
    event.preventDefault();
    const button = document.getElementById("loginSubmitButton");
    button.disabled = true;
    try {
      const response = await window.fetch(registerMode ? "/api/auth/register" : "/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("accessUsername").value.trim().toLowerCase() || "chuso",
          password: document.getElementById("accessPassword").value,
        }),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Chưa đăng nhập được. Hãy thử lại.",
        );
      document.getElementById("accessPassword").value = "";
      write(LOGOUT_PENDING, null);
      location.reload();
    } catch (error) {
      gate(error.message || "Chưa kết nối được máy chủ. Hãy thử lại.");
    } finally {
      button.disabled = false;
    }
  };
  window.logoutAccess = async () => {
    if (window.hasPendingExpenses?.()) {
      window.showToast?.("Hãy đồng bộ hoặc bỏ các khoản đang chờ trước khi đăng xuất.", true);
      return;
    }
    write(LOGOUT_PENDING, window.smartspendUserId || "legacy-owner");
    write(ACCOUNT_EVENT, "signed-out:" + Date.now());
    clearPrivateCache();
    gate();
    try {
      const response = await window.fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok && response.status !== 401) throw new Error();
      write(LOGOUT_PENDING, null);
    } catch (_) {
      gate("Đã khóa giao diện trên thiết bị. Kết nối lại để kết thúc phiên trên máy chủ.");
    }
    auth.authenticated = false;
    window.smartspendUserId = null;
    location.reload();
  };
  window.toggleAccessMode = () => {
    registerMode = !registerMode;
    document.getElementById("authTitle").textContent = registerMode
      ? "Tạo sổ riêng"
      : "Mở SmartSpend";
    document.getElementById("loginSubmitButton").textContent = registerMode
      ? "Tạo tài khoản"
      : "Đăng nhập";
    document.getElementById("accountToggle").textContent = registerMode
      ? "Đã có tài khoản? Đăng nhập"
      : "Chưa có tài khoản? Tạo sổ riêng";
    document.getElementById("registerHint").classList.toggle("hidden", !registerMode);
    const password = document.getElementById("accessPassword");
    password.autocomplete = registerMode ? "new-password" : "current-password";
    password.minLength = registerMode ? 12 : 1;
    password.value = "";
    document.getElementById("authError").classList.add("hidden");
  };
  window.addEventListener("storage", (event) => {
    if (
      event.key === ACCOUNT_EVENT &&
      window.smartspendUserId &&
      event.newValue !== window.smartspendUserId
    ) {
      gate("Tài khoản đã thay đổi ở tab khác. Đang tải lại…");
      location.reload();
    }
  });
  document.addEventListener("DOMContentLoaded", checkAccess);
  window.addEventListener("online", checkAccess);
})();
