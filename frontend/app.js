// Local Lucide SVG sprite; no icon runtime or external font CDN required.
function renderIcon(name, extraClass = "") {
  const cls = extraClass ? `icon ${extraClass}` : "icon";
  return `<svg class="${cls}" aria-hidden="true"><use href="/icons.svg?v=21#${name}"></use></svg>`;
}

// =====================================================================
//  SMARTSPEND PRO - THEME, MONEY INPUTS, SETTINGS & AI/MANUAL PLANNER
// =====================================================================

let allPlans = [];
let currentPlan = null;
let historyFilter = "all"; // "all" | "meal" | "hangout"
let planSearchQuery = "";
let hideCompletedItems = false;
let financeChart = null;
let currentChartType = "doughnut"; // "doughnut" | "bar"
let canEditServerConfig = false;
let plansHaveMore = false,
  plansLoading = false,
  plansEpoch = 0;
const PLAN_PAGE_SIZE = 30;
const pendingPlanItems = new Set();
let planWriteQueue = Promise.resolve();

// =====================================================================
// 0. CHẾ ĐỘ SÁNG / TỐI (DARK MODE)
// =====================================================================
function isDarkTheme() {
  return document.documentElement?.classList?.contains?.("dark") || false;
}

function applyTheme(theme) {
  const dark = theme === "dark";
  document.documentElement?.classList?.toggle?.("dark", dark);
  document.getElementById("themeIconMoon")?.classList?.toggle?.("hidden", dark);
  document.getElementById("themeIconSun")?.classList?.toggle?.("hidden", !dark);
  const meta = document.getElementById("themeColorMeta");
  if (meta && meta.setAttribute) meta.setAttribute("content", dark ? "#090d16" : "#f8fafc");
}

function initTheme() {
  let saved = null;
  try {
    saved = window.localStorage?.getItem?.("smartspend-theme");
  } catch (_) {}
  if (!saved) {
    saved = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  }
  applyTheme(saved);
}

function toggleTheme() {
  const next = isDarkTheme() ? "light" : "dark";
  applyTheme(next);
  try {
    window.localStorage?.setItem?.("smartspend-theme", next);
  } catch (_) {}
  if (currentPlan) renderFinanceChart(currentPlan);
  window.renderDailySpending?.();
  window.renderSixMonthTrends?.();
  window.renderCategoryBreakdown?.();
}

initTheme();

// =====================================================================
// ĐỊNH DẠNG & KIỂM TRA SỐ TIỀN VNĐ
// =====================================================================
function formatVND(amount) {
  const value = Math.round(Number(amount) || 0);
  return value.toLocaleString("vi-VN") + " ₫";
}

function formatAxisMoney(value) {
  const num = Number(value) || 0;
  if (num === 0) return "0";
  const sign = num < 0 ? "-" : "";
  const abs = Math.abs(num);
  if (abs >= 1_000_000_000) {
    return `${sign}${(abs / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}tỷ`;
  }
  if (abs >= 1_000_000) {
    return `${sign}${(abs / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}tr`;
  }
  if (abs >= 1_000) {
    return `${sign}${(abs / 1_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}k`;
  }
  return `${sign}${Math.round(abs)}`;
}
window.formatAxisMoney = formatAxisMoney;

function parseMoneyInput(value) {
  const text = String(value ?? "").trim();
  if (!/^(?:\d+|\d{1,3}(?:\.\d{3})+)$/.test(text)) return NaN;
  const amount = Number(text.replace(/\./g, ""));
  return Number.isSafeInteger(amount) ? amount : NaN;
}

function formatMoneyInputValue(value) {
  if (value === "" || value == null) return "";
  const amount = parseMoneyInput(value);
  return Number.isFinite(amount) ? amount.toLocaleString("vi-VN") : String(value);
}

function validateMoneyInput(input) {
  if (!input.value.trim()) {
    input.setCustomValidity("");
    return;
  }
  const amount = parseMoneyInput(input.value);
  const minimum = Number(input.dataset.moneyMin || 0);
  const maximum = Number(input.dataset.moneyMax || 9000000000000);
  input.setCustomValidity(
    !Number.isFinite(amount)
      ? "Nhập số tiền nguyên, dùng dấu chấm để tách hàng nghìn, ví dụ 1.000.000."
      : amount < minimum || amount > maximum
        ? `Số tiền phải từ ${formatVND(minimum)} đến ${formatVND(maximum)}.`
        : "",
  );
}

function formatMoneyInput(input) {
  const text = input.value;
  if (/^[\d.]+$/.test(text)) {
    const position = input.selectionStart;
    const digits = text.replace(/\./g, "");
    const normalized = digits.replace(/^0+(?=\d)/, "");
    const formatted = normalized.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    input.value = formatted;
    if (position != null && document.activeElement === input) {
      const precedingDigits = Math.max(
        0,
        text.slice(0, position).replace(/\./g, "").length - (digits.length - normalized.length),
      );
      let caret = 0,
        seen = 0;
      while (caret < formatted.length && seen < precedingDigits) {
        if (/\d/.test(formatted[caret])) seen++;
        caret++;
      }
      input.setSelectionRange(caret, caret);
    }
  }
  validateMoneyInput(input);
}

document.addEventListener("input", (event) => {
  const input = event.target;
  if (!input?.matches?.("input[data-money]")) return;
  formatMoneyInput(input);
  if (input.id === "budgetInput") updateBudgetPreview(input.value);
});

document.addEventListener("paste", (event) => {
  const input = event.target;
  if (!input?.matches?.("input[data-money]") || !event.clipboardData) return;
  const text = event.clipboardData.getData("text").trim();
  event.preventDefault();
  input.setRangeText(
    Number.isFinite(parseMoneyInput(text)) ? text.replace(/\./g, "") : text,
    input.selectionStart,
    input.selectionEnd,
    "end",
  );
  if (Number.isFinite(parseMoneyInput(text))) {
    input.dispatchEvent(new Event("input", { bubbles: true }));
  } else {
    validateMoneyInput(input);
  }
});

document.addEventListener("beforeinput", (event) => {
  const input = event.target;
  if (!input?.matches?.("input[data-money]") || input.selectionStart !== input.selectionEnd) return;
  const position = input.selectionStart;
  if (event.inputType === "deleteContentBackward" && input.value[position - 1] === ".") {
    event.preventDefault();
    input.setRangeText("", Math.max(0, position - 2), position, "end");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  } else if (event.inputType === "deleteContentForward" && input.value[position] === ".") {
    event.preventDefault();
    input.setRangeText("", position, position + 2, "end");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
});

// =====================================================================
// THÔNG BÁO TOAST & HTML ESCAPING
// =====================================================================
function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(message, isError = false) {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `px-4 py-3 rounded-xl text-xs sm:text-sm font-semibold flex items-center gap-2.5 transition-all duration-300 ${
    isError ? "text-rose-600" : ""
  }`;
  toast.innerHTML = `
    ${renderIcon(isError ? "triangle-alert" : "check")}
    <span>${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 300);
  }, 3800);
}

function actionToast(message, label, action) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "action-toast";
  const text = document.createElement("span");
  text.textContent = message;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "text-action";
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await action();
      toast.remove();
    } catch (error) {
      button.disabled = false;
      showToast(error.message, true);
    }
  });
  toast.append(text, button);
  container.append(toast);
  setTimeout(() => toast.remove(), 10000);
}

// =====================================================================
// 1. QUẢN LÝ CẤU HÌNH HỆ THỐNG (/api/config)
// =====================================================================
async function loadConfigStatus() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return;
    const data = await res.json();

    canEditServerConfig = data.can_edit_config === true;
    document
      .querySelectorAll("[data-server-config]")
      .forEach((control) => control.classList.toggle("hidden", !canEditServerConfig));
    if (!canEditServerConfig) {
      if (!document.getElementById("settingsModal")?.classList.contains("hidden"))
        hideModal("settingsModal");
      return;
    }

    renderDbStatusBadge(data.db_status, data.has_api_key);

    const apiKeyInput = document.getElementById("configApiKeyInput");
    const dbUrlInput = document.getElementById("configDbUrlInput");
    const cloudUrlInput = document.getElementById("configCloudUrlInput");
    const allowLanInput = document.getElementById("configAllowLanInput");
    if (apiKeyInput) {
      apiKeyInput.value = "";
      apiKeyInput.placeholder = data.has_api_key
        ? `Đã lưu (${data.gemini_api_key_masked || "ẩn"}) — để trống để giữ nguyên`
        : "AIzaSy…";
      apiKeyInput.disabled = !data.can_edit_config;
    }
    if (dbUrlInput) {
      dbUrlInput.value = "";
      dbUrlInput.placeholder = data.has_database_url
        ? "Đã cấu hình PostgreSQL — để trống để giữ nguyên"
        : "postgresql://…";
      dbUrlInput.disabled = !data.can_edit_config;
    }
    if (cloudUrlInput) {
      cloudUrlInput.value = data.cloud_url || "";
      cloudUrlInput.disabled = !data.can_edit_config;
    }
    if (allowLanInput) {
      allowLanInput.checked = Boolean(data.allow_lan);
      allowLanInput.disabled = !data.can_edit_config;
    }

    document
      .getElementById("saveConfigSubmitBtn")
      ?.classList.toggle("hidden", !data.can_edit_config);
    document
      .getElementById("configClearOptions")
      ?.classList.toggle("hidden", !data.can_edit_config);
    const clearApi = document.getElementById("clearApiKeyInput");
    const clearDb = document.getElementById("clearDbUrlInput");
    const clearCloud = document.getElementById("clearCloudUrlInput");
    if (clearApi) clearApi.checked = false;
    if (clearDb) clearDb.checked = false;
    if (clearCloud) clearCloud.checked = false;

    const statusBox = document.getElementById("configModalStatusBox");
    if (statusBox) {
      const aiNote = data.has_api_key ? "Đã bật Gemini AI" : "Chưa nhập Gemini API Key";
      if (data.db_status?.is_cloud_postgres) {
        statusBox.innerHTML = `<strong>PostgreSQL:</strong> <code>${escapeHtml(
          data.db_status.configured_url_masked,
        )}</code> · <span>${aiNote}</span>`;
      } else {
        statusBox.innerHTML = `<strong>SQLite trên máy:</strong> <code>smartspend_local.db</code> · <span>${aiNote}</span>`;
      }
    }
  } catch (err) {
    console.error("Lỗi tải cấu hình:", err);
  }
}

function renderDbStatusBadge(dbStatus, hasApiKey = true) {
  const badge = document.getElementById("dbStatusBadge");
  const text = document.getElementById("dbStatusText");
  if (!badge || !text) return;

  if (dbStatus && dbStatus.is_cloud_postgres) {
    text.textContent = hasApiKey ? "PostgreSQL · AI" : "PostgreSQL";
  } else {
    text.textContent = hasApiKey ? "SQLite · AI" : "Local SQLite";
  }
}

let modalTrigger = null;

function showModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  if (modal.classList.contains("hidden")) modalTrigger = document.activeElement;
  modal.classList.remove("hidden");
  if (document.body?.style) document.body.style.overflow = "hidden";
  modal.querySelector("input:not([type='hidden']), select, textarea, button")?.focus();
}

function hideModal(id) {
  const modal = document.getElementById(id);
  if (!modal || modal.dataset?.busy === "true") return;
  modal.classList.add("hidden");
  if (document.body?.style) document.body.style.overflow = "";
  if (modalTrigger?.isConnected && modalTrigger.getClientRects?.().length) modalTrigger.focus();
  else document.querySelector('[data-view][aria-current="page"]')?.focus();
}

document.addEventListener("keydown", (event) => {
  const modal = document.querySelector?.('[role="dialog"]:not(.hidden)');
  if (!modal) return;
  if (event.key === "Escape") hideModal(modal.id);
  if (event.key !== "Tab") return;
  const controls = [
    ...modal.querySelectorAll("button, input, select, textarea, summary, a[href]"),
  ].filter((control) => !control.disabled && control.getClientRects().length);
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
});

async function openSettingsModal() {
  await loadConfigStatus();
  if (!canEditServerConfig) return;
  showModal("settingsModal");
}

function closeSettingsModal() {
  hideModal("settingsModal");
}

async function handleSaveConfig(event) {
  event.preventDefault();
  if (window.hasPendingExpenses?.()) {
    showToast("Hãy đồng bộ các giao dịch đang chờ trước khi đổi kết nối dữ liệu.", true);
    return;
  }
  const btn = document.getElementById("saveConfigSubmitBtn");
  const apiKey = document.getElementById("configApiKeyInput").value.trim();
  const dbUrl = document.getElementById("configDbUrlInput").value.trim();
  const cloudUrl = document.getElementById("configCloudUrlInput")?.value.trim() || "";
  const allowLan = Boolean(document.getElementById("configAllowLanInput")?.checked);

  btn.disabled = true;
  btn.textContent = "Đang kiểm tra…";

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gemini_api_key: apiKey || null,
        database_url: dbUrl || null,
        cloud_url: cloudUrl || null,
        allow_lan: allowLan,
        clear_api_key: document.getElementById("clearApiKeyInput").checked,
        clear_database_url: document.getElementById("clearDbUrlInput").checked,
        clear_cloud_url: Boolean(document.getElementById("clearCloudUrlInput")?.checked),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Không thể lưu cấu hình");
    }

    renderDbStatusBadge(data.db_status, data.has_api_key);
    showToast(data.connection?.message || "Đã lưu cấu hình");
    await loadConfigStatus();
    await loadPlansFromDB();
    await window.refreshFinance?.();
    closeSettingsModal();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${renderIcon("check")} Lưu cấu hình`;
  }
}

// =====================================================================
// 2. MODAL KẾT NỐI IPHONE & MÃ QR (/api/network-info)
// =====================================================================
async function openIphoneModal() {
  showModal("iphoneModal");
  const qrImage = document.getElementById("iphoneQrImg");
  qrImage.removeAttribute("src");
  qrImage.classList.add("hidden");
  try {
    const res = await fetch("/api/network-info");
    if (!res.ok) throw new Error("Không lấy được địa chỉ app");
    const data = await res.json();
    const lanUrl = data.app_url || data.lan_url || window.location.origin;

    document.getElementById("iphoneLanUrlCode").textContent = lanUrl;
    document.getElementById("iphoneConnectionMessage").textContent = data.public_url
      ? "Quét mã QR bằng Camera iPhone. Địa chỉ HTTPS này dùng được qua cả Wi-Fi lẫn 4G/5G."
      : data.allow_lan === false
        ? "Máy tính hiện đang khóa chế độ mạng nội bộ (127.0.0.1). Hãy bật 'Cho phép điện thoại cùng mạng Wi-Fi' trong Cài đặt rồi mở lại app."
        : "Địa chỉ này dùng trong cùng mạng Wi-Fi. Triển khai Cloud nếu muốn mở khi máy tính tắt.";
    document.getElementById("iphoneConnectionNote").textContent = data.public_url
      ? "Mở bằng Safari, đăng nhập và chọn Chia sẻ → Thêm vào Màn hình chính."
      : "Giữ ứng dụng trên máy tính đang chạy khi truy cập qua Wi-Fi nội bộ.";
    try {
      const qr = await fetch("/api/network-qr", { cache: "no-store" });
      if (!qr.ok) throw new Error("Không tải được QR");
      qrImage.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(await qr.text());
      qrImage.classList.remove("hidden");
    } catch (_) {
      document.getElementById("iphoneConnectionNote").textContent =
        "Chưa tải được mã QR. Bạn vẫn có thể sao chép đường link và mở bằng Safari trên iPhone.";
    }
  } catch (err) {
    const fallbackUrl = window.location.origin;
    document.getElementById("iphoneLanUrlCode").textContent = fallbackUrl;
    document.getElementById("iphoneQrImg").removeAttribute("src");
    document.getElementById("iphoneConnectionMessage").textContent =
      "Chưa lấy được địa chỉ app. Hãy kiểm tra kết nối và thử lại.";
  }
}

function closeIphoneModal() {
  hideModal("iphoneModal");
}

function copyIphoneLanUrl() {
  const url = document.getElementById("iphoneLanUrlCode").textContent;
  navigator.clipboard?.writeText?.(url);
  showToast("Đã sao chép địa chỉ ứng dụng");
}

// =====================================================================
// 3. CHUYỂN ĐỔI CHẾ ĐỘ, TẠO KẾ HOẠCH AI & TẠO THỦ CÔNG
// =====================================================================
function switchPlanMode(mode) {
  document.getElementById("planTypeInput").value = mode;
  const mealBtn = document.getElementById("modeMealBtn");
  const hangoutBtn = document.getElementById("modeHangoutBtn");
  const durationInput = document.getElementById("durationInput");
  const styleSelect = document.getElementById("styleModeInput");
  const titleInput = document.getElementById("planTitleInput");
  const prefInput = document.getElementById("preferencesInput");

  mealBtn.setAttribute("aria-pressed", String(mode === "meal"));
  hangoutBtn.setAttribute("aria-pressed", String(mode === "hangout"));
  mealBtn.className = mode === "meal" ? "mode-segment-btn active" : "mode-segment-btn";
  hangoutBtn.className = mode === "hangout" ? "mode-segment-btn active" : "mode-segment-btn";

  if (mode === "meal") {
    durationInput.value = "7 ngày";
    titleInput.placeholder = "Thực đơn tuần";
    prefInput.placeholder = "Khẩu vị, dị ứng…";
    styleSelect.innerHTML = `
      <option value="Nấu ăn tại nhà & mang cơm đi làm">Nấu tại nhà</option>
      <option value="Cơm gia đình tiết kiệm, đủ chất">Cơm gia đình</option>
      <option value="Thực đơn Eat Clean / Giảm cân">Eat Clean</option>
      <option value="Sinh viên / Người ở trọ bận rộn">Nấu nhanh</option>
    `;
  } else {
    durationInput.value = "1 buổi tối";
    titleInput.placeholder = "Hẹn hò cuối tuần";
    prefInput.placeholder = "Địa điểm, hoạt động…";
    styleSelect.innerHTML = `
      <option value="Hẹn hò cặp đôi lãng mạn">Hẹn hò</option>
      <option value="Đi chơi tụ tập nhóm bạn">Nhóm bạn</option>
      <option value="Dã ngoại / Giải trí cuối tuần">Dã ngoại</option>
      <option value="Foodtour ẩm thực đường phố">Ẩm thực</option>
    `;
  }
}

function updateBudgetPreview(val) {
  const badge = document.getElementById("budgetPreviewBadge");
  if (badge) badge.textContent = formatVND(parseMoneyInput(val));
}

function setQuickBudget(amount) {
  const input = document.getElementById("budgetInput");
  input.value = formatMoneyInputValue(amount);
  formatMoneyInput(input);
  updateBudgetPreview(amount);
}

async function readAIResponse(response) {
  try {
    return await response.json();
  } catch (_) {
    throw new Error(
      `Chưa nhận được phản hồi AI hợp lệ (HTTP ${response.status}). Hãy thử lại sau; nếu vẫn lỗi, báo người quản trị kiểm tra log AI và tunnel.`,
    );
  }
}

async function handleGeneratePlan(event) {
  event.preventDefault();

  const planType = document.getElementById("planTypeInput").value;
  const customTitle = document.getElementById("planTitleInput").value.trim();
  const totalBudget = parseMoneyInput(document.getElementById("budgetInput").value);
  const region = document.getElementById("regionInput").value;
  const styleMode = document.getElementById("styleModeInput").value;
  const duration = document.getElementById("durationInput").value.trim();
  const people = document.getElementById("peopleInput").value.trim();
  const notes = document.getElementById("preferencesInput").value.trim();

  const daysOrPeopleCombined = `${duration} cho ${people}`;
  const fullPreferences = [`Hình thức: ${styleMode}`, notes ? `Ghi chú riêng: ${notes}` : ""]
    .filter(Boolean)
    .join(". ");

  const overlay = document.getElementById("aiLoadingOverlay");
  const submitBtn = document.getElementById("generateSubmitBtn");
  overlay.classList.remove("hidden");
  submitBtn.disabled = true;

  try {
    const res = await fetch("/api/plans/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: customTitle || null,
        plan_type: planType,
        total_budget: totalBudget,
        region: region,
        days_or_people: daysOrPeopleCombined,
        preferences: fullPreferences,
        pantry: document.getElementById("pantryInput")?.value.trim() || "",
      }),
    });

    const data = await readAIResponse(res);
    if (!res.ok) {
      if (
        res.status === 400 &&
        typeof data.detail === "string" &&
        (data.detail.toLowerCase().includes("api key") ||
          data.detail.toLowerCase().includes("cấu hình"))
      ) {
        openSettingsModal();
      }
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Dữ liệu chưa hợp lệ. Hãy kiểm tra độ dài và nội dung biểu mẫu.",
      );
    }

    document.getElementById("planTitleInput").value = "";
    showToast("Đã tạo kế hoạch");
    await loadPlansFromDB(data.id);
    scrollToPlanContentOnMobile();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    overlay.classList.add("hidden");
    submitBtn.disabled = false;
  }
}

function openManualPlanEditor() {
  if (!window.openFinanceEditor) return;
  const body = `
    <div class="editor-field">
      <label for="manualPlanType">Loại kế hoạch</label>
      <select id="manualPlanType" name="manualPlanType">
        <option value="meal">Thực đơn</option>
        <option value="hangout">Đi chơi</option>
      </select>
    </div>
    ${window.formField("Tên kế hoạch", "manualPlanTitle", "text", "", 'required maxlength="255" placeholder="Đi chợ cuối tuần"')}
    ${window.formField("Ngân sách (VNĐ)", "manualPlanBudget", "number", 500000, 'min="10000" max="2000000000" required')}
    ${window.formField("Khu vực", "manualPlanRegion", "text", "Hà Nội", 'required maxlength="120"')}
    <div class="editor-field">
      <label for="manualPlanAdvice">Ghi chú</label>
      <textarea id="manualPlanAdvice" name="manualPlanAdvice" rows="2" maxlength="5000" placeholder="Mua đồ tươi buổi sáng…"></textarea>
    </div>
  `;
  window.openFinanceEditor(
    "Tạo kế hoạch thủ công",
    body,
    async (form) => {
      const budget = parseMoneyInput(form.get("manualPlanBudget"));
      const res = await fetch("/api/plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.get("manualPlanTitle").trim(),
          plan_type: form.get("manualPlanType"),
          total_budget: budget,
          region: form.get("manualPlanRegion").trim() || "Hà Nội",
          advice: form.get("manualPlanAdvice").trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Chưa tạo được kế hoạch");
      await loadPlansFromDB(data.id);
      showToast("Đã tạo kế hoạch");
      scrollToPlanContentOnMobile();
    },
    "Tạo kế hoạch",
  );
}

function openEditActivePlan() {
  if (!currentPlan || !window.openFinanceEditor) return;
  const plan = currentPlan;
  const body = `
    ${window.formField("Tên kế hoạch", "editPlanTitle", "text", plan.title, 'required maxlength="255"')}
    ${window.formField("Ngân sách (VNĐ)", "editPlanBudget", "number", plan.total_budget, 'min="10000" max="2000000000" required')}
    ${window.formField("Khu vực", "editPlanRegion", "text", plan.region, 'required maxlength="120"')}
    <div class="editor-field">
      <label for="editPlanAdvice">Mẹo / Ghi chú</label>
      <textarea id="editPlanAdvice" name="editPlanAdvice" rows="3" maxlength="5000">${escapeHtml(plan.advice || "")}</textarea>
    </div>
  `;
  window.openFinanceEditor(
    "Sửa kế hoạch",
    body,
    async (form) => {
      const res = await fetch(`/api/plans/${plan.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.get("editPlanTitle").trim(),
          total_budget: parseMoneyInput(form.get("editPlanBudget")),
          region: form.get("editPlanRegion").trim(),
          advice: form.get("editPlanAdvice").trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Chưa lưu được thay đổi");
      applyUpdatedPlanFromServer(data);
      showToast("Đã lưu");
    },
    "Lưu",
  );
}

function openAddPlanItem(defaultCategory = "grocery") {
  if (!currentPlan || !window.openFinanceEditor) return;
  const plan = currentPlan;
  const cat = plan.plan_type === "hangout" ? "activity" : defaultCategory;
  const placeholderTime =
    cat === "daily_menu" ? "Ngày 1" : cat === "activity" ? "18:00 - 20:00" : "Thịt cá";
  const body = `
    ${window.formField("Tên mục", "newItemName", "text", "", 'required maxlength="255" placeholder="Thịt bò 300g"')}
    ${window.formField("Nhóm / Thời gian", "newItemTime", "text", "", `maxlength="120" placeholder="${placeholderTime}"`)}
    ${window.formField("Chi phí dự kiến (VNĐ)", "newItemPrice", "number", cat === "daily_menu" ? 0 : "", 'min="0" max="2000000000" required placeholder="45.000"')}
    <div class="editor-field">
      <label for="newItemDetails">Ghi chú</label>
      <textarea id="newItemDetails" name="newItemDetails" rows="2" maxlength="5000"></textarea>
    </div>
  `;
  window.openFinanceEditor(
    cat === "daily_menu"
      ? "Thêm thực đơn ngày"
      : cat === "activity"
        ? "Thêm chặng"
        : "Thêm món đi chợ",
    body,
    async (form) => {
      const res = await fetch(`/api/plans/${plan.id}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: cat,
          name: form.get("newItemName").trim(),
          time_or_day: form.get("newItemTime").trim(),
          price: parseMoneyInput(form.get("newItemPrice") || "0"),
          details: form.get("newItemDetails").trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Chưa thêm được hạng mục");
      if (data.plan) applyUpdatedPlanFromServer(data.plan);
      showToast("Đã thêm mục");
    },
    "Thêm",
  );
}

function openEditPlanItem(itemId) {
  const item = currentPlan?.items?.find((i) => i.id === itemId);
  if (!item || !window.openFinanceEditor) return;
  const body = `
    ${window.formField("Tên hạng mục", "editItemName", "text", item.name, 'required maxlength="255"')}
    ${window.formField("Nhóm / Ngày / Khung giờ", "editItemTime", "text", item.time_or_day || "", 'maxlength="120"')}
    ${window.formField("Chi phí dự kiến (VNĐ)", "editItemPrice", "number", item.price, 'min="0" max="2000000000" required')}
    <div class="editor-field">
      <label for="editItemDetails">Chi tiết</label>
      <textarea id="editItemDetails" name="editItemDetails" rows="3" maxlength="5000">${escapeHtml(item.details || "")}</textarea>
    </div>
  `;
  window.openFinanceEditor(
    "Chỉnh sửa hạng mục",
    body,
    async (form) => {
      const res = await fetch(`/api/items/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("editItemName").trim(),
          time_or_day: form.get("editItemTime").trim(),
          price: parseMoneyInput(form.get("editItemPrice") || "0"),
          details: form.get("editItemDetails").trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Chưa lưu được hạng mục");
      if (data.plan) {
        applyUpdatedPlanFromServer(data.plan);
        await window.refreshFinance?.();
      }
      showToast("Đã cập nhật hạng mục");
    },
    "Lưu thay đổi",
  );
}

async function deletePlanItemById(itemId) {
  try {
    const res = await fetch(`/api/items/${itemId}`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Không thể xóa hạng mục");
    if (data.plan) {
      applyUpdatedPlanFromServer(data.plan);
      await window.refreshFinance?.();
    }
    showToast("Đã xóa hạng mục khỏi kế hoạch");
  } catch (err) {
    showToast(err.message, true);
  }
}

// =====================================================================
// 4. LỊCH SỬ KẾ HOẠCH (/api/plans)
// =====================================================================
async function loadPlansFromDB(targetPlanId = null, append = false) {
  if (append && (plansLoading || !plansHaveMore)) return;
  const epoch = ++plansEpoch;
  plansLoading = true;
  const moreButton = document.getElementById("morePlansButton");
  if (moreButton) moreButton.disabled = true;
  try {
    const params = new URLSearchParams({ limit: PLAN_PAGE_SIZE });
    if (historyFilter !== "all") params.set("plan_type", historyFilter);
    if (append && allPlans.length) params.set("before_id", allPlans.at(-1).id);
    const res = await fetch(`/api/plans?${params}`);
    if (!res.ok) throw new Error("Không tải được kế hoạch");
    const page = await res.json();
    if (epoch !== plansEpoch) return;
    plansHaveMore = page.length === PLAN_PAGE_SIZE;
    allPlans = append
      ? [...allPlans, ...page.filter((p) => !allPlans.some((old) => old.id === p.id))]
      : page;

    renderPlansHistoryList();
    if (append) return;

    if (targetPlanId) {
      const target = allPlans.find((p) => p.id === targetPlanId);
      if (target) {
        selectActivePlan(target);
        return;
      }
      const detail = await fetch(`/api/plans/${targetPlanId}`);
      if (detail.ok) {
        const targetDetail = await detail.json();
        if (epoch !== plansEpoch) return;
        selectActivePlan(targetDetail);
        return;
      }
    }

    if (currentPlan) {
      const refreshed = allPlans.find((p) => p.id === currentPlan.id);
      if (refreshed) {
        selectActivePlan(refreshed);
        return;
      }
    }

    if (allPlans.length > 0) {
      selectActivePlan(allPlans[0]);
    } else {
      clearDashboardToEmpty();
    }
  } catch (err) {
    if (epoch !== plansEpoch) return;
    document.getElementById("plansHistoryList").innerHTML =
      `<p class="empty-copy">Chưa tải được danh sách kế hoạch. Nhấn Làm mới khi có kết nối.</p>`;
  } finally {
    if (epoch === plansEpoch) {
      plansLoading = false;
      if (moreButton) {
        moreButton.disabled = false;
        moreButton.classList.toggle("hidden", !plansHaveMore);
      }
    }
  }
}

function setHistoryFilter(filterType) {
  historyFilter = filterType;
  for (const [suffix, value] of [
    ["All", "all"],
    ["Meal", "meal"],
    ["Hangout", "hangout"],
  ]) {
    const el = document.getElementById(`historyFilter${suffix}`);
    if (el) {
      el.setAttribute("aria-pressed", String(filterType === value));
      el.className = filterType === value ? "filter-chip active" : "filter-chip";
    }
  }
  loadPlansFromDB();
}

function normalizePlanText(text) {
  return String(text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
}

function renderPlansHistoryList() {
  const container = document.getElementById("plansHistoryList");
  const qNorm = normalizePlanText(planSearchQuery.trim());
  const filtered = (
    historyFilter === "all" ? allPlans : allPlans.filter((p) => p.plan_type === historyFilter)
  ).filter((p) => {
    if (!qNorm) return true;
    return normalizePlanText(`${p.title} ${p.region || ""}`).includes(qNorm);
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div class="empty-copy">${
      qNorm ? "Không tìm thấy kế hoạch khớp từ khóa." : "Chưa có kế hoạch nào trong nhóm này."
    }</div>`;
    return;
  }

  container.innerHTML = filtered
    .map((plan) => {
      const isSelected = currentPlan && currentPlan.id === plan.id;
      const icon = renderIcon(plan.plan_type === "meal" ? "utensils" : "coffee");
      const dateStr = plan.created_at ? new Date(plan.created_at).toLocaleDateString("vi-VN") : "";

      return `
        <div
          role="button"
          tabindex="0"
          aria-pressed="${Boolean(isSelected)}"
          data-action="select-plan"
          data-plan-id="${plan.id}"
          class="plan-history-card"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <span>${icon}</span>
              <h4 class="truncate">${escapeHtml(plan.title)}</h4>
            </div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[11px] muted">
              <span>Ngân sách: <strong class="text-strong">${formatVND(plan.total_budget)}</strong></span>
              <span>Đã chi: <strong class="text-strong">${formatVND(plan.actual_spent)}</strong></span>
              <span>${escapeHtml(plan.region)}${dateStr ? ` · ${dateStr}` : ""}</span>
            </div>
          </div>

          <button
            type="button"
            data-action="delete-plan"
            data-plan-id="${plan.id}"
            class="icon-button"
            aria-label="Xóa kế hoạch: ${escapeHtml(plan.title)}"
            title="Chuyển kế hoạch vào thùng rác"
          >
            ${renderIcon("trash-2")}
          </button>
        </div>
      `;
    })
    .join("");
}

function scrollToPlanContentOnMobile() {
  if (typeof window.innerWidth === "number" && window.innerWidth < 1024) {
    document
      .getElementById("planWorkspaceMain")
      ?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }
}

function selectPlanById(planId) {
  const found = allPlans.find((p) => p.id === planId);
  if (found) {
    selectActivePlan(found);
    scrollToPlanContentOnMobile();
  }
}

// =====================================================================
// 5. HIỂN THỊ CHI TIẾT KẾ HOẠCH, CHART.JS & CHECKLIST
// =====================================================================
function clearDashboardToEmpty() {
  currentPlan = null;
  document.getElementById("emptyDashboardState").classList.remove("hidden");
  document.getElementById("planDashboardContent").classList.add("hidden");

  document.getElementById("statTotalBudget").textContent = "0 ₫";
  document.getElementById("statEstimatedCost").textContent = "0 ₫";
  document.getElementById("statActualSpent").textContent = "0 ₫";
  document.getElementById("statRemaining").textContent = "0 ₫";
}

function selectActivePlan(plan) {
  currentPlan = plan;
  document.getElementById("emptyDashboardState").classList.add("hidden");
  document.getElementById("planDashboardContent").classList.remove("hidden");

  renderPlansHistoryList();
  renderStatCardsAndProgress(plan);
  renderFinanceChart(plan);
  renderInteractiveChecklist(plan);
}

function formatConciseAdviceItems(rawText) {
  const cleaned = String(rawText || "").trim();
  if (!cleaned) return [];
  const parts = cleaned
    .split(/\r?\n|[•·▪]|(?<=[.!?])\s+/)
    .map((line) => line.replace(/^[-*•\d.)\s]+/, "").trim())
    .filter((line) => line.length > 3);
  return parts.slice(0, 3).map((line) => {
    const words = line.split(/\s+/);
    return words.length > 12 ? `${words.slice(0, 11).join(" ")}…` : line;
  });
}

function renderStatCardsAndProgress(plan) {
  const remaining = plan.total_budget - plan.actual_spent;
  const legacyNotice = document.getElementById("legacyPlanNotice");
  legacyNotice.classList.toggle("hidden", !plan.unrecorded_legacy_spent);
  legacyNotice.textContent = plan.unrecorded_legacy_spent
    ? `Số liệu cũ: ${formatVND(plan.unrecorded_legacy_spent)}.`
    : "";

  document.getElementById("statTotalBudget").textContent = formatVND(plan.total_budget);
  document.getElementById("statEstimatedCost").textContent = formatVND(plan.estimated_cost);
  document.getElementById("statActualSpent").textContent = formatVND(plan.actual_spent);

  const remEl = document.getElementById("statRemaining");
  remEl.textContent = formatVND(remaining);
  remEl.className = remaining < 0 ? "is-negative" : "";

  const typeBadge = document.getElementById("activePlanTypeBadge");
  typeBadge.textContent = plan.plan_type === "meal" ? "Thực đơn" : "Đi chơi";

  document.getElementById("activePlanRegionBadge").textContent = plan.region;
  document.getElementById("activePlanDateBadge").textContent = plan.created_at
    ? new Date(plan.created_at).toLocaleDateString("vi-VN")
    : "Hôm nay";
  document.getElementById("activePlanTitle").textContent = plan.title;

  const adviceBullets = formatConciseAdviceItems(plan.advice);
  const adviceEl = document.getElementById("activePlanAdvice");
  const adviceWrap = document.getElementById("planAdviceDisclosure");
  adviceWrap?.classList?.toggle?.("hidden", adviceBullets.length === 0);
  if (adviceEl) {
    adviceEl.innerHTML = adviceBullets.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  }

  const baseBudget = Math.max(1, plan.total_budget);
  const estPct = Math.min(100, Math.round((plan.estimated_cost / baseBudget) * 100));
  const actPct = Math.round((plan.actual_spent / baseBudget) * 100);

  document.getElementById("barActualLabel").textContent = formatVND(plan.actual_spent);
  document.getElementById("barEstimatedLabel").textContent = formatVND(plan.estimated_cost);
  document.getElementById("barPercentLabel").textContent = `${actPct}%`;
  document.getElementById("barEstimatedFill").style.width = `${estPct}%`;
  document.getElementById("barActualFill").style.width = `${Math.min(100, actPct)}%`;
}

function switchChartType(type) {
  currentChartType = type;
  const doughnutBtn = document.getElementById("chartTypeDoughnutBtn");
  const barBtn = document.getElementById("chartTypeBarBtn");
  doughnutBtn.setAttribute("aria-pressed", String(type === "doughnut"));
  barBtn.setAttribute("aria-pressed", String(type === "bar"));
  doughnutBtn.className = type === "doughnut" ? "filter-chip active" : "filter-chip";
  barBtn.className = type === "bar" ? "filter-chip active" : "filter-chip";

  if (currentPlan) {
    renderFinanceChart(currentPlan);
  }
}

function renderFinanceChart(plan) {
  const canvas = document.getElementById("financeChartCanvas");
  if (!canvas || typeof Chart === "undefined") return;

  if (financeChart) {
    financeChart.destroy();
    financeChart = null;
  }

  const dark = isDarkTheme();
  const labelColor = dark ? "#cbd5e1" : "#475569";
  const tickColor = dark ? "#94a3b8" : "#64748b";
  const borderBg = dark ? "#131c2e" : "#ffffff";

  const actualSpent = Math.max(0, plan.actual_spent || 0);
  const unspentPlanned = Math.max(
    0,
    (plan.items || [])
      .filter((i) => !i.payment)
      .reduce((acc, item) => acc + (Number(item.price) || 0), 0),
  );
  const remainingFree = Math.max(0, plan.total_budget - (actualSpent + unspentPlanned));

  if (currentChartType === "doughnut") {
    financeChart = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: ["Đã chi", "Chưa chi", "Còn lại"],
        datasets: [
          {
            data: [actualSpent, unspentPlanned, remainingFree],
            backgroundColor: ["#6366f1", "#38bdf8", dark ? "#24324b" : "#e2e8f0"],
            borderColor: borderBg,
            borderWidth: 3,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "64%",
        plugins: {
          legend: {
            position: "right",
            labels: {
              color: labelColor,
              font: { size: 11 },
              padding: 14,
            },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${formatVND(ctx.raw)}`,
            },
          },
        },
      },
    });
  } else {
    financeChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: ["Ngân sách", "Dự kiến", "Đã chi", "Còn lại"],
        datasets: [
          {
            label: "Số tiền (VNĐ)",
            data: [
              plan.total_budget,
              plan.estimated_cost,
              actualSpent,
              Math.max(0, plan.total_budget - actualSpent),
            ],
            backgroundColor: ["#818cf8", "#38bdf8", "#6366f1", "#10b981"],
            borderRadius: 8,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${formatVND(ctx.raw)}`,
            },
          },
        },
        scales: {
          x: {
            ticks: { color: tickColor, font: { size: 11 } },
            grid: { display: false },
          },
          y: {
            ticks: {
              color: tickColor,
              font: { size: 11 },
              callback: (val) => formatAxisMoney(val),
            },
            grid: { color: dark ? "rgba(148, 163, 184, 0.12)" : "rgba(148, 163, 184, 0.16)" },
          },
        },
      },
    });
  }
}

function toggleHideCompleted() {
  hideCompletedItems = !hideCompletedItems;
  document.querySelectorAll('[data-action="toggle-hide-completed"]').forEach((btn) => {
    btn.setAttribute("aria-pressed", String(hideCompletedItems));
    btn.classList.toggle("active-toggle", hideCompletedItems);
    const defaultLabel = btn.dataset.defaultLabel || "Ẩn đã xong";
    const span = btn.querySelector("span");
    if (span) span.textContent = hideCompletedItems ? "Hiện tất cả" : defaultLabel;
    const useEl = btn.querySelector("use");
    if (useEl) {
      useEl.setAttribute("href", `/icons.svg?v=21#${hideCompletedItems ? "eye" : "eye-off"}`);
    }
  });
  if (currentPlan) renderInteractiveChecklist(currentPlan);
}

function copyActivePlanText() {
  if (!currentPlan) return;
  const plan = currentPlan;
  const items = plan.items || [];
  const lines = [
    `📋 ${plan.title.toUpperCase()} (${plan.region})`,
    `Ngân sách: ${formatVND(plan.total_budget)} · Dự kiến: ${formatVND(plan.estimated_cost)} · Đã chi: ${formatVND(plan.actual_spent)}`,
    "",
  ];
  if (plan.plan_type === "meal") {
    const grocery = items.filter((i) => i.category === "grocery");
    const menus = items.filter((i) => i.category === "daily_menu");
    if (grocery.length) {
      lines.push("🛒 DANH SÁCH ĐI CHỢ:");
      grocery.forEach((i) => {
        lines.push(
          `[${i.is_completed ? "x" : " "}] ${i.name}${i.price ? ` — ${formatVND(i.price)}` : ""}`,
        );
      });
      lines.push("");
    }
    if (menus.length) {
      lines.push("🍽️ THỰC ĐƠN THEO NGÀY:");
      menus.forEach((i) => {
        lines.push(`• ${i.time_or_day ? `${i.time_or_day}: ` : ""}${i.name}`);
      });
    }
  } else {
    lines.push("✨ LỊCH TRÌNH HOẠT ĐỘNG:");
    items.forEach((i) => {
      lines.push(
        `[${i.is_completed ? "x" : " "}] ${i.time_or_day ? `${i.time_or_day} · ` : ""}${i.name}${i.price ? ` (${formatVND(i.price)})` : ""}`,
      );
    });
  }
  if (plan.advice) {
    lines.push("", `💡 Gợi ý: ${plan.advice}`);
  }
  navigator.clipboard?.writeText?.(lines.join("\n"));
  showToast("Đã sao chép kế hoạch để gửi Zalo / Ghi chú!");
}

function renderInteractiveChecklist(plan) {
  const items = plan.items || [];
  const mealSections = document.getElementById("mealPlanSections");
  const hangoutSection = document.getElementById("hangoutPlanSection");

  if (plan.plan_type === "meal") {
    mealSections.classList.remove("hidden");
    hangoutSection.classList.add("hidden");

    const groceryItems = items.filter((i) => i.category === "grocery");
    const visibleGrocery = hideCompletedItems
      ? groceryItems.filter((i) => !i.is_completed)
      : groceryItems;
    const dailyMenuItems = items.filter((i) => i.category === "daily_menu");

    document.getElementById("groceryCountBadge").textContent = `${
      groceryItems.filter((i) => i.is_completed).length
    }/${groceryItems.length} đã mua`;
    document.getElementById("dailyMenuCountBadge").textContent = `${dailyMenuItems.length} ngày`;

    document.getElementById("groceryChecklistContainer").innerHTML =
      groceryItems.length === 0
        ? `<div class="empty-copy">Chưa có nguyên liệu nào. Nhấn "Thêm nguyên liệu" để bổ sung.</div>`
        : visibleGrocery.length > 0
          ? visibleGrocery.map((item) => renderSingleItemCard(item)).join("")
          : `<div class="empty-copy">Tất cả ${groceryItems.length} nguyên liệu đã mua xong! Nhấn "Hiện tất cả" để xem lại.</div>`;

    document.getElementById("dailyMenuChecklistContainer").innerHTML =
      dailyMenuItems.length > 0
        ? dailyMenuItems.map((item) => renderSingleItemCard(item)).join("")
        : `<div class="empty-copy">Chưa có thực đơn ngày nào.</div>`;
  } else {
    mealSections.classList.add("hidden");
    hangoutSection.classList.remove("hidden");

    const visibleActivities = hideCompletedItems ? items.filter((i) => !i.is_completed) : items;

    document.getElementById("activityCountBadge").textContent = `${
      items.filter((i) => i.is_completed).length
    }/${items.length} hoàn thành`;

    document.getElementById("activityChecklistContainer").innerHTML =
      items.length === 0
        ? `<div class="empty-copy">Chưa có hoạt động nào. Nhấn "Thêm hoạt động" để bắt đầu.</div>`
        : visibleActivities.length > 0
          ? visibleActivities.map((item) => renderSingleItemCard(item)).join("")
          : `<div class="empty-copy">Đã hoàn thành toàn bộ lịch trình! Nhấn "Hiện tất cả" để xem lại.</div>`;
  }
}

function renderSingleItemCard(item) {
  const isDone = Boolean(item.is_completed);
  const busy = pendingPlanItems.has(item.id);

  return `
    <div id="item-card-${item.id}" class="checklist-card ${isDone ? "is-done" : ""}">
      <div class="flex items-start gap-3 flex-1 min-w-0">
        <input
          type="checkbox"
          data-action="toggle-plan-item"
          data-item-id="${item.id}"
          aria-label="Hoàn thành: ${escapeHtml(item.name)}"
          ${isDone ? "checked" : ""} ${busy ? "disabled" : ""}
          class="mt-1 w-5 h-5 rounded accent-indigo-600 cursor-pointer flex-shrink-0"
          title="Tích để ghi chi theo giá của mục; bỏ tích để hủy khoản chi tự động"
        />
        <div class="flex-1 min-w-0">
          <div class="flex flex-wrap items-center gap-2 mb-1">
            ${
              item.time_or_day
                ? `<span class="plan-meta-pill">${escapeHtml(item.time_or_day)}</span>`
                : ""
            }
            <h4 class="text-sm font-semibold ${isDone ? "line-through muted" : "text-strong"}">
              ${escapeHtml(item.name)}
            </h4>
          </div>
          ${
            item.details
              ? `<p class="text-xs muted leading-relaxed whitespace-pre-line">${escapeHtml(item.details)}</p>`
              : ""
          }
        </div>
      </div>

      <div class="plan-item-actions">
        <div class="checklist-price-box">
          <input
            type="text"
            inputmode="numeric"
            data-money
            data-action="update-item-price"
            data-item-id="${item.id}"
            aria-label="Chi phí dự kiến: ${escapeHtml(item.name)}"
            value="${formatMoneyInputValue(item.price)}"
            data-money-min="0"
            data-money-max="2000000000"
            ${busy ? "disabled" : ""}
            title="Sửa giá ước tính của hạng mục"
          />
          <span class="text-[11px] font-semibold muted">₫</span>
        </div>

        <button
          type="button"
          class="ui-button ${item.payment ? "quiet" : "soft"} small"
          data-action="record-plan-payment"
          data-item-id="${item.id}"
          title="${item.payment ? `Đã ghi ${formatVND(item.payment.amount)}` : "Ghi khoản thanh toán thực tế"}"
        >
          ${renderIcon(item.payment ? "check" : "receipt")}
          ${item.payment ? "Đã ghi chi" : "Ghi chi"}
        </button>

        <details class="item-menu">
          <summary aria-label="Tùy chọn hạng mục ${escapeHtml(item.name)}">${renderIcon("ellipsis")}</summary>
          <div>
            <button type="button" data-action="edit-plan-item" data-item-id="${item.id}">
              ${renderIcon("pencil")} Sửa nội dung
            </button>
            ${
              !item.payment
                ? `<button type="button" data-action="replace-plan-item" data-item-id="${item.id}">
                    ${renderIcon("refresh-cw")} Đổi gợi ý khác
                  </button>`
                : ""
            }
            <button type="button" class="danger-item" data-action="delete-plan-item" data-item-id="${item.id}">
              ${renderIcon("trash-2")} Xóa mục này
            </button>
          </div>
        </details>
      </div>
    </div>
  `;
}

// =====================================================================
// 6. ĐỒNG BỘ CHECKLIST & XÓA KẾ HOẠCH AN TOÀN
// =====================================================================
async function toggleItemCompleted(itemId, isCompleted) {
  return savePlanItem(itemId, { is_completed: isCompleted });
}

async function updateItemPrice(itemId, rawValue) {
  const newPrice = parseMoneyInput(rawValue);
  if (!Number.isInteger(newPrice) || newPrice < 0 || newPrice > 2000000000) {
    renderInteractiveChecklist(currentPlan);
    showToast("Giá phải là số nguyên từ 0 đến 2 tỷ đồng.", true);
    return;
  }
  return savePlanItem(itemId, { price: newPrice });
}

function savePlanItem(itemId, payload) {
  if (pendingPlanItems.has(itemId)) return planWriteQueue;
  pendingPlanItems.add(itemId);
  document
    .querySelectorAll(`#item-card-${itemId} input, #item-card-${itemId} button`)
    .forEach((c) => (c.disabled = true));
  const operation = async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const res = await fetch(`/api/items/${itemId}`, {
        method: "PATCH",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Không thể lưu hạng mục");
      }

      if (data.plan) {
        applyUpdatedPlanFromServer(data.plan);
        await window.refreshFinance?.();
      }
    } catch (err) {
      showToast(
        err.name === "AbortError"
          ? "Chưa xác nhận được thay đổi. Hãy kết nối và làm mới kế hoạch."
          : err.message,
        true,
      );
      if (currentPlan) renderInteractiveChecklist(currentPlan);
    } finally {
      clearTimeout(timer);
      pendingPlanItems.delete(itemId);
      document
        .querySelectorAll(`#item-card-${itemId} input, #item-card-${itemId} button`)
        .forEach((c) => (c.disabled = false));
    }
  };
  planWriteQueue = planWriteQueue.then(operation, operation);
  return planWriteQueue;
}

function applyUpdatedPlanFromServer(updatedPlan) {
  const idx = allPlans.findIndex((p) => p.id === updatedPlan.id);
  if (idx !== -1) {
    allPlans[idx] = updatedPlan;
  }
  if (currentPlan && currentPlan.id !== updatedPlan.id) {
    renderPlansHistoryList();
    return;
  }
  currentPlan = updatedPlan;
  renderPlansHistoryList();
  renderStatCardsAndProgress(updatedPlan);
  renderFinanceChart(updatedPlan);
  renderInteractiveChecklist(updatedPlan);
}

async function refreshActivePlan() {
  if (!currentPlan) return;
  try {
    const res = await fetch(`/api/plans/${currentPlan.id}`);
    if (!res.ok) return;
    const freshPlan = await res.json();
    applyUpdatedPlanFromServer(freshPlan);
    showToast("Đã đồng bộ kế hoạch mới nhất");
  } catch (err) {
    showToast("Không thể làm mới kế hoạch", true);
  }
}

async function performPlanDeletion(planId, deleteAutoPayments = false) {
  const params = deleteAutoPayments ? "?delete_auto_payments=true" : "";
  const res = await fetch(`/api/plans/${planId}${params}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error("Không thể xóa kế hoạch");
  }
  const deleted = await res.json();
  if (currentPlan && currentPlan.id === planId) {
    currentPlan = null;
  }
  await Promise.all([loadPlansFromDB(), window.refreshFinance?.()]);
  actionToast("Đã chuyển kế hoạch vào thùng rác", "Hoàn tác", async () => {
    const response = await fetch(`/api/plans/trash/${deleted.undo_id}/restore`, {
      method: "POST",
    });
    if (!response.ok) throw new Error("Chưa khôi phục được kế hoạch");
    const restored = await response.json();
    await loadPlansFromDB(restored.id);
    await window.refreshFinance?.();
  });
}

function deletePlanById(planId) {
  if (!planId) return;
  const target = allPlans.find((p) => p.id === planId);
  const title = target ? target.title : `#${planId}`;
  const hasPayments = target?.items?.some((i) => i.payment);

  if (window.openFinanceEditor) {
    window.openFinanceEditor(
      "Xóa kế hoạch",
      `<p class="small">Bạn muốn chuyển kế hoạch <strong>${escapeHtml(title)}</strong> vào thùng rác?</p>
       ${
         hasPayments
           ? `<label class="config-option mt-3">
               <input type="checkbox" name="deleteAutoPayments" value="1" />
               <span>Đồng thời hủy các khoản chi tự động do tích chọn trong kế hoạch này</span>
             </label>`
           : `<p class="muted small mt-2">Bạn có thể khôi phục lại bất cứ lúc nào từ Kho lưu trữ &amp; Thùng rác.</p>`
       }`,
      async (form) => {
        await performPlanDeletion(planId, Boolean(form.get("deleteAutoPayments")));
      },
      "Chuyển vào thùng rác",
    );
    return;
  }
  performPlanDeletion(planId, false).catch((err) => showToast(err.message, true));
}

// =====================================================================
// 7. SỰ KIỆN ỦY QUYỀN (ZERO INLINE EVENT HANDLERS)
// =====================================================================
let deferredInstallPrompt = null;
window.addEventListener?.("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  document.getElementById("nativePwaInstallBtn")?.classList?.remove?.("hidden");
});

async function triggerNativePwaInstall() {
  if (!deferredInstallPrompt) return;
  try {
    await deferredInstallPrompt.prompt();
    deferredInstallPrompt = null;
    document.getElementById("nativePwaInstallBtn")?.classList?.add?.("hidden");
  } catch (_) {}
}

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("planGeneratorForm")?.addEventListener("submit", handleGeneratePlan);
  document.getElementById("settingsForm")?.addEventListener("submit", handleSaveConfig);
  document.getElementById("planChartDisclosure")?.addEventListener?.("toggle", (e) => {
    if (e.target?.open) financeChart?.resize?.();
  });
  document.getElementById("planSearchInput")?.addEventListener("input", (e) => {
    planSearchQuery = e.target.value || "";
    renderPlansHistoryList();
  });

  await window.smartspendAuthReady;
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  await loadConfigStatus();
  await loadPlansFromDB();
});

document.addEventListener("click", (event) => {
  if (event.target?.classList?.contains?.("modal-backdrop") && event.target.id) {
    hideModal(event.target.id);
    return;
  }
  const openMenus = document.querySelectorAll?.("details.item-menu[open]") || [];
  openMenus.forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });

  const actionEl = event.target?.closest?.("[data-action]");
  if (!actionEl) return;
  const action = actionEl.dataset.action;

  switch (action) {
    case "toggle-theme":
      toggleTheme();
      break;
    case "open-command-palette":
      window.openCommandPalette?.();
      break;
    case "close-command-palette":
      hideModal("commandPaletteModal");
      break;
    case "install-native-pwa":
      triggerNativePwaInstall();
      break;
    case "open-shortcuts-modal":
      showModal("shortcutsModal");
      break;
    case "close-shortcuts-modal":
      hideModal("shortcutsModal");
      break;
    case "toggle-hide-completed":
      toggleHideCompleted();
      break;
    case "copy-plan-text":
      actionEl.closest("details")?.removeAttribute("open");
      copyActivePlanText();
      break;
    case "open-settings-modal":
      openSettingsModal();
      break;
    case "close-settings-modal":
      closeSettingsModal();
      break;
    case "open-iphone-modal":
      openIphoneModal();
      break;
    case "close-iphone-modal":
      closeIphoneModal();
      break;
    case "copy-iphone-url":
      copyIphoneLanUrl();
      break;
    case "switch-plan-mode":
      switchPlanMode(actionEl.dataset.mode);
      break;
    case "quick-budget":
      setQuickBudget(Number(actionEl.dataset.amount));
      break;
    case "open-manual-plan-editor":
      openManualPlanEditor();
      break;
    case "reload-plans":
      loadPlansFromDB();
      break;
    case "load-more-plans":
      loadPlansFromDB(null, true);
      break;
    case "filter-plans":
      setHistoryFilter(actionEl.dataset.filter);
      break;
    case "select-plan":
      if (!event.target.closest('[data-action="delete-plan"]')) {
        selectPlanById(Number(actionEl.dataset.planId));
      }
      break;
    case "delete-plan":
      event.stopPropagation();
      deletePlanById(Number(actionEl.dataset.planId));
      break;
    case "edit-active-plan":
      actionEl.closest("details")?.removeAttribute("open");
      openEditActivePlan();
      break;
    case "copy-active-plan":
      actionEl.closest("details")?.removeAttribute("open");
      window.copyActivePlan?.();
      break;
    case "refresh-active-plan":
      actionEl.closest("details")?.removeAttribute("open");
      refreshActivePlan();
      break;
    case "delete-active-plan":
      actionEl.closest("details")?.removeAttribute("open");
      if (currentPlan?.id) deletePlanById(currentPlan.id);
      break;
    case "switch-chart-type":
      switchChartType(actionEl.dataset.chartType);
      break;
    case "open-add-plan-item":
      openAddPlanItem(actionEl.dataset.itemCategory);
      break;
    case "record-plan-payment":
      window.recordPlanPayment?.(Number(actionEl.dataset.itemId));
      break;
    case "edit-plan-item":
      actionEl.closest("details")?.removeAttribute("open");
      openEditPlanItem(Number(actionEl.dataset.itemId));
      break;
    case "replace-plan-item":
      actionEl.closest("details")?.removeAttribute("open");
      window.openPlanReplacement?.(Number(actionEl.dataset.itemId));
      break;
    case "delete-plan-item":
      actionEl.closest("details")?.removeAttribute("open");
      deletePlanItemById(Number(actionEl.dataset.itemId));
      break;
    default:
      break;
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!target?.dataset?.action) return;
  if (target.dataset.action === "toggle-plan-item") {
    toggleItemCompleted(Number(target.dataset.itemId), target.checked);
  } else if (target.dataset.action === "update-item-price") {
    updateItemPrice(Number(target.dataset.itemId), target.value);
  }
});

document.addEventListener("keydown", (event) => {
  const card = event.target?.closest?.('[data-action="select-plan"]');
  if (card && event.target === card && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    selectPlanById(Number(card.dataset.planId));
  }
});
