/* Same-origin session login, offline cache unlock, and account security controls. */
(() => {
  const rawFetch = window.fetch.bind(window);
  const SEEN = "smartspend-auth-seen";
  const USER_NAME_KEY = "smartspend-auth-username";
  const ACCOUNT_EVENT = "smartspend-active-account";
  const LOGOUT_PENDING = "smartspend-logout-pending";
  const MAX_OFFLINE_AGE_MS = 30 * 86400 * 1000;
  let registerMode = false;
  window.smartspendUserId = null;
  window.smartspendStorageKey = (key) => `${key}:user:${window.smartspendUserId || "locked"}`;

  let resolveReady,
    ready = false,
    checking = false;
  let auth = {
    required: true,
    authenticated: false,
    cloud: false,
    accounts: false,
    can_register: false,
    invite_required: false,
    can_change_password: false,
  };
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
    try {
      if (typeof sessionStorage !== "undefined") {
        sessionStorage.removeItem("smartspend-view");
      }
    } catch (_) {}
    write(SEEN, null);
    write(USER_NAME_KEY, null);
  }
  window.clearSmartSpendCache = clearPrivateCache;

  function gate(message = "") {
    document.documentElement.classList.remove("auth-pending");
    document.documentElement.classList.add("auth-locked");
    document.getElementById("authGate")?.classList.remove("hidden");
    const showAccounts = Boolean(auth.accounts);
    const canReg = Boolean(auth.accounts && auth.can_register);
    if (!canReg && registerMode) {
      registerMode = false;
    }
    document.getElementById("accountFields")?.classList.toggle("hidden", !showAccounts);
    document.getElementById("accountToggle")?.classList.toggle("hidden", !canReg);
    document
      .getElementById("inviteCodeField")
      ?.classList.toggle("hidden", !(registerMode && auth.invite_required));
    const accountName = document.getElementById("accountName");
    if (accountName) accountName.textContent = "";
    const usernameInput = document.getElementById("accessUsername");
    if (usernameInput) usernameInput.required = showAccounts;
    const inviteInput = document.getElementById("accessInviteCode");
    if (inviteInput) inviteInput.required = Boolean(registerMode && auth.invite_required);
    document.getElementById("authLoading")?.classList.add("hidden");
    const error = document.getElementById("authError");
    if (error) {
      error.textContent = message;
      error.classList.toggle("hidden", !message);
    }
  }

  function unlock(data, offline = false) {
    auth = data;
    window.smartspendAuthState = data;
    window.smartspendUserId = data.user?.id || "legacy-owner";
    const accountName = document.getElementById("accountName");
    if (accountName) accountName.textContent = data.user?.username || "chuso";
    write(ACCOUNT_EVENT, window.smartspendUserId);
    if (data.user?.username) write(USER_NAME_KEY, data.user.username);
    window.migrateLegacyExpenseOutbox?.();
    document.documentElement.classList.remove("auth-pending", "auth-locked");
    document.getElementById("authGate")?.classList.add("hidden");
    document.getElementById("authLoading")?.classList.add("hidden");
    document.getElementById("logoutButton")?.classList.toggle("hidden", !data.required);
    document.getElementById("logoutAllButton")?.classList.toggle("hidden", !data.required);
    document
      .getElementById("changePasswordButton")
      ?.classList.toggle("hidden", !data.can_change_password);
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
    headers.set("X-SmartSpend-Tz-Offset", String(new Date().getTimezoneOffset()));
    if (window.smartspendUserId) headers.set("X-SmartSpend-User", window.smartspendUserId);
    const response = await rawFetch(input, { ...options, headers, credentials: "same-origin" });
    if (response.status === 401 && !url.pathname.startsWith("/api/auth/")) {
      clearPrivateCache();
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
        clearPrivateCache();
        gate();
      }
    } catch (error) {
      // Allow offline access only within the 30-day session TTL window
      const lastSeen = read(SEEN);
      const savedUser = read(ACCOUNT_EVENT);
      const pendingLogout = read(LOGOUT_PENDING);
      const seenTs = Number(lastSeen);
      const nowMs = Date.now();
      const withinTtl =
        Boolean(lastSeen) &&
        Number.isFinite(seenTs) &&
        seenTs > 0 &&
        nowMs - seenTs < MAX_OFFLINE_AGE_MS &&
        seenTs <= nowMs + 300000;
      if (withinTtl && savedUser && !savedUser.startsWith("signed-out:") && !pendingLogout) {
        unlock(
          {
            required: true,
            authenticated: true,
            offline: true,
            user: { id: savedUser, username: read(USER_NAME_KEY) || "chuso" },
          },
          true,
        );
      } else {
        if (lastSeen && !withinTtl) {
          clearPrivateCache();
          gate("Phiên ngoại tuyến đã hết hạn (quá 30 ngày). Hãy kết nối mạng để đăng nhập lại.");
        } else {
          gate(error.message || "Cần kết nối Internet để xác nhận tài khoản.");
        }
      }
    } finally {
      checking = false;
    }
  }
  window.retryAccess = checkAccess;

  window.submitAccessLogin = async (event) => {
    event.preventDefault();
    const button = document.getElementById("loginSubmitButton");
    if (button) button.disabled = true;
    try {
      const payload = {
        username: document.getElementById("accessUsername")?.value.trim().toLowerCase() || "chuso",
        password: document.getElementById("accessPassword")?.value || "",
      };
      if (registerMode && auth.invite_required) {
        payload.invite_code = document.getElementById("accessInviteCode")?.value.trim() || "";
      }
      const response = await window.fetch(registerMode ? "/api/auth/register" : "/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Chưa đăng nhập được. Hãy thử lại.",
        );
      const pwd = document.getElementById("accessPassword");
      if (pwd) pwd.value = "";
      write(LOGOUT_PENDING, null);
      location.reload();
    } catch (error) {
      gate(error.message || "Chưa kết nối được máy chủ. Hãy thử lại.");
    } finally {
      if (button) button.disabled = false;
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

  window.logoutAllDevices = async () => {
    if (window.hasPendingExpenses?.()) {
      window.showToast?.("Hãy đồng bộ hoặc bỏ các khoản đang chờ trước khi đăng xuất.", true);
      return;
    }
    try {
      const response = await window.fetch("/api/auth/logout-all", { method: "POST" });
      if (!response.ok && response.status !== 401) {
        throw new Error("Chưa thu hồi được các phiên đăng nhập. Hãy thử lại.");
      }
      write(LOGOUT_PENDING, null);
      write(ACCOUNT_EVENT, "signed-out:" + Date.now());
      clearPrivateCache();
      auth.authenticated = false;
      window.smartspendUserId = null;
      location.reload();
    } catch (error) {
      window.showToast?.(error.message, true);
    }
  };

  window.toggleAccessMode = () => {
    if (!auth.can_register) return;
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
    document.getElementById("registerHint")?.classList.toggle("hidden", !registerMode);
    document
      .getElementById("inviteCodeField")
      ?.classList.toggle("hidden", !(registerMode && auth.invite_required));
    const inviteInput = document.getElementById("accessInviteCode");
    if (inviteInput) inviteInput.required = Boolean(registerMode && auth.invite_required);
    const password = document.getElementById("accessPassword");
    if (password) {
      password.autocomplete = registerMode ? "new-password" : "current-password";
      password.minLength = registerMode ? 12 : 1;
      password.value = "";
    }
    document.getElementById("authError")?.classList.add("hidden");
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

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("authForm")?.addEventListener("submit", window.submitAccessLogin);
    document.getElementById("accountToggle")?.addEventListener("click", window.toggleAccessMode);
    document.getElementById("authRetryButton")?.addEventListener("click", checkAccess);
    checkAccess();
  });
  window.addEventListener("online", checkAccess);
})();
