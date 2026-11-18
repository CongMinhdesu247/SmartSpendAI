/* Personal ledger workspace: Smart Quick-Add, Insights, Archive, Backup/Import & Offline Queue. */
const FINANCE_COLORS = {
  orange: "#c46b2a",
  green: "#16a36b",
  violet: "#8b5cf6",
  sky: "#0284c7",
  indigo: "#6366f1",
  pink: "#db5b91",
  teal: "#0d9488",
  blue: "#3b82f6",
  slate: "#64748b",
};
const FINANCE_VIEWS = {
  spending: ["Sổ chi tiêu", "Theo dõi dòng tiền, ngân sách và sức khỏe tài chính theo tháng."],
  plans: ["Kế hoạch & AI", "Thực đơn đi chợ gộp, lịch trình đi chơi và quản lý hạng mục."],
  recurring: ["Khoản định kỳ", "Theo dõi lịch hóa đơn cố định và xác nhận thanh toán đúng hạn."],
  goals: ["Mục tiêu tiết kiệm", "Theo dõi tiến độ tích lũy cho từng mục tiêu tài chính."],
  account: ["Tài khoản & Hệ thống", "Cài đặt AI, sao lưu dữ liệu, thùng rác và bảo mật phiên."],
};
let lastPlanningView = "plans";
const OUTBOX_KEY = "smartspend-outbox-v2";
function expenseOutboxKey() {
  return window.smartspendStorageKey(OUTBOX_KEY);
}
let financeState = {
  categories: [],
  overview: null,
  trends: null,
  transactions: [],
  total: 0,
  bills: [],
  goals: [],
  preferences: {},
};
let financeMonth = localISODate().slice(0, 7);
let financeDayFilter = null;
let spendingChartMode = "daily";
let activeHomePanel = null;
let currentCoachFocus = "";
let financeOffset = 0,
  financeEpoch = 0,
  financeEditorSave = null,
  financeSearchTimer;
let categoryDoughnutChart = null;
let sixMonthTrendsChart = null;
let aiCoachMonthCache = {};
let cmdSelectedIndex = 0;
let financeCached = false,
  financeSyncing = false,
  financePreferencesLoaded = false;

function localISODate(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
function financeUUID() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (Number(c) ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(c) / 4)))).toString(
      16,
    ),
  );
}
function displayDate(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}
function formatMonthLabel(monthValue) {
  if (!monthValue || !monthValue.includes("-")) return "";
  const [year, month] = monthValue.split("-");
  return `Tháng ${Number(month)}/${year}`;
}
function syncMonthDisplay() {
  const disp = document.getElementById("financeMonthDisplay");
  if (disp) disp.textContent = formatMonthLabel(financeMonth);
}
function compactMoneyTick(value) {
  if (typeof window !== "undefined" && typeof window.formatAxisMoney === "function") {
    return window.formatAxisMoney(value);
  }
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
function financeCategory(id) {
  return financeState.categories.find((c) => c.id === Number(id));
}
function colorFor(category) {
  return FINANCE_COLORS[category?.color] || FINANCE_COLORS.indigo;
}
function financeEmpty(message, action = "") {
  return `<div class="finance-empty">${renderIcon("receipt")}<p>${escapeHtml(message)}</p>${action}</div>`;
}

// =====================================================================
// PHÂN TÍCH NGÔN NGỮ TỰ NHIÊN CỤC BỘ (SMART QUICK-ADD 0ms LATENCY)
// =====================================================================
const CATEGORY_KEYWORDS = [
  [
    "Ăn uống",
    [
      "phở",
      "bún",
      "cơm",
      "mì",
      "bánh mì",
      "ăn sáng",
      "ăn trưa",
      "ăn tối",
      "ăn vặt",
      "cà phê",
      "cafe",
      "coffee",
      "trà sữa",
      "nước",
      "lẩu",
      "nướng",
    ],
  ],
  [
    "Đi chợ",
    [
      "đi chợ",
      "siêu thị",
      "thịt",
      "cá",
      "rau",
      "trứng",
      "gạo",
      "trái cây",
      "hoa quả",
      "sữa",
      "bách hóa",
    ],
  ],
  [
    "Di chuyển",
    [
      "xăng",
      "gửi xe",
      "grab",
      "be",
      "taxi",
      "xe buýt",
      "vé xe",
      "vé tàu",
      "vé máy bay",
      "bảo dưỡng",
    ],
  ],
  [
    "Nhà ở",
    [
      "tiền nhà",
      "thuê nhà",
      "tiền phòng",
      "điện",
      "nước",
      "internet",
      "wifi",
      "rác",
      "phí chung cư",
    ],
  ],
  ["Mua sắm", ["quần", "áo", "giày", "mỹ phẩm", "shopee", "lazada", "tiktok", "đồ gia dụng"]],
  ["Sức khỏe", ["thuốc", "khám", "bệnh viện", "nha khoa", "vitamin", "gym", "thể thao"]],
  ["Học tập", ["sách", "khóa học", "học phí", "tiếng anh", "tài liệu"]],
  ["Đi chơi", ["xem phim", "cgv", "hẹn hò", "du lịch", "karaoke", "bida", "bowling", "concert"]],
];

function guessCategoryFromTitle(title) {
  const lower = String(title || "").toLowerCase();
  const active = financeState.categories.filter((c) => !c.archived);
  for (const [catName, words] of CATEGORY_KEYWORDS) {
    if (words.some((w) => lower.includes(w))) {
      const found = active.find((c) => c.name.toLowerCase() === catName.toLowerCase());
      if (found) return found;
    }
  }
  return active.find((c) => c.name === "Khác") || active[0] || null;
}

function parseQuickEntry(rawInput, referenceDate = new Date()) {
  let text = String(rawInput || "").trim();
  if (!text) return null;

  let kind = "expense";
  if (text.startsWith("+")) {
    kind = "income";
    text = text.slice(1).trim();
  } else if (text.startsWith("-")) {
    kind = "expense";
    text = text.slice(1).trim();
  }

  let amount = NaN;
  let matchIndex = -1;
  let matchLength = 0;

  // 1. Vietnamese split-unit shorthand first: 1tr5, 2củ35, 1 củ 5, 35k5, 45k500
  const splitPattern = /(?:^|\s)(\d+)\s*(tr|triệu|củ|k|nghìn|ngàn|n)\s*(\d{1,3})(?=\s|$)/i;
  const splitMatch = text.match(splitPattern);
  if (splitMatch) {
    matchIndex = splitMatch.index;
    matchLength = splitMatch[0].length;
    const whole = Number(splitMatch[1]);
    const unit = splitMatch[2].toLowerCase();
    const fracStr = splitMatch[3];
    const scale = unit === "tr" || unit === "triệu" || unit === "củ" ? 1_000_000 : 1_000;
    const frac = Number(fracStr) / Math.pow(10, fracStr.length);
    amount = Math.round((whole + frac) * scale);
  } else {
    // 2. Standard & colloquial Vietnamese shorthand money: 35k, 50 cành, 2 lít, 1.5tr, 45.000
    const moneyPattern =
      /(?:^|\s)(\d+(?:[.,]\d+)?)\s*(k|nghìn|ngàn|n|cành|lít|xị|tr|triệu|củ|đ|d|vnd)?(?=\s|$)/i;
    const match = text.match(moneyPattern);
    if (!match) return null;

    matchIndex = match.index;
    matchLength = match[0].length;
    const rawNum = match[1];
    const unit = (match[2] || "").toLowerCase();

    if (unit === "tr" || unit === "triệu" || unit === "củ") {
      amount = Math.round(Number(rawNum.replace(",", ".")) * 1_000_000);
    } else if (unit === "lít" || unit === "xị") {
      amount = Math.round(Number(rawNum.replace(",", ".")) * 100_000);
    } else if (
      unit === "k" ||
      unit === "n" ||
      unit === "nghìn" ||
      unit === "ngàn" ||
      unit === "cành"
    ) {
      amount = Math.round(Number(rawNum.replace(",", ".")) * 1_000);
    } else if (/^\d{1,3}(?:\.\d{3})+$/.test(rawNum)) {
      amount = Number(rawNum.replace(/\./g, ""));
    } else if (/^\d+$/.test(rawNum)) {
      const plain = Number(rawNum);
      amount = plain < 1000 && plain > 0 ? plain * 1000 : plain;
    }
  }

  if (!Number.isSafeInteger(amount) || amount <= 0 || amount > 9_000_000_000_000) return null;

  let remainder = (text.slice(0, matchIndex) + " " + text.slice(matchIndex + matchLength))
    .replace(/\s+/g, " ")
    .trim();

  // Detect relative Vietnamese dates or explicit DD/MM(/YYYY)
  let targetDate = new Date(referenceDate.getTime());
  const explicitDateMatch = remainder.match(
    /(?:^|\s)(?:ngày\s+)?(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{4}))?(?=\s|$)/i,
  );
  if (explicitDateMatch) {
    const dNum = Number(explicitDateMatch[1]);
    const mNum = Number(explicitDateMatch[2]);
    const yNum = explicitDateMatch[3] ? Number(explicitDateMatch[3]) : referenceDate.getFullYear();
    const maxDay = new Date(yNum, mNum, 0).getDate();
    if (mNum >= 1 && mNum <= 12 && dNum >= 1 && dNum <= maxDay && yNum >= 2000 && yNum <= 2100) {
      targetDate = new Date(yNum, mNum - 1, dNum);
      remainder = (
        remainder.slice(0, explicitDateMatch.index) +
        " " +
        remainder.slice(explicitDateMatch.index + explicitDateMatch[0].length)
      )
        .replace(/\s+/g, " ")
        .trim();
    }
  } else if (/\b(?:hôm qua|tối qua)\b/i.test(remainder)) {
    targetDate.setDate(targetDate.getDate() - 1);
    remainder = remainder.replace(/\b(?:hôm qua|tối qua)\b/gi, "").trim();
  } else if (/\bhôm kia\b/i.test(remainder)) {
    targetDate.setDate(targetDate.getDate() - 2);
    remainder = remainder.replace(/\bhôm kia\b/gi, "").trim();
  } else if (/\b(?:hôm nay|sáng nay|trưa nay|tối nay)\b/i.test(remainder)) {
    remainder = remainder.replace(/\b(?:hôm nay|sáng nay|trưa nay|tối nay)\b/gi, "").trim();
  }

  remainder = remainder.replace(/^[,.\-–:]+\s*|\s*[,.\-–:]+$/g, "").trim();
  const title = remainder || (kind === "income" ? "Khoản thu" : "Chi tiêu");
  if (
    kind === "expense" &&
    !rawInput.trim().startsWith("-") &&
    /\b(lương|thưởng|hoàn tiền|thu nhập|lãi tiết kiệm)\b/i.test(title)
  ) {
    kind = "income";
  }

  const category = guessCategoryFromTitle(title);
  return {
    amount,
    kind,
    title: title.charAt(0).toUpperCase() + title.slice(1),
    spent_on: localISODate(targetDate),
    category_id: category?.id || null,
    category_name: category?.name || "Khác",
  };
}

function renderParsedPreviewHtml(parsed) {
  return `
    <span class="preview-tag ${parsed.kind}">
      ${parsed.kind === "income" ? "Thu +" : "Chi −"}${formatVND(parsed.amount)}
    </span>
    <span class="preview-tag">${escapeHtml(parsed.title)}</span>
    <span class="preview-tag">${escapeHtml(parsed.category_name)}</span>
    <span class="preview-tag">${displayDate(parsed.spent_on)}</span>
  `;
}

function updateQuickAddPreview() {
  const input = document.getElementById("quickAddInput");
  const preview = document.getElementById("quickAddPreview");
  const detailBtn = document.getElementById("quickAddDetailBtn");
  const hints = document.getElementById("quickAddHints");
  if (!input || !preview) return;
  const parsed = parseQuickEntry(input.value);
  if (!parsed) {
    preview.classList.add("hidden");
    detailBtn?.classList.add("hidden");
    hints?.classList?.remove?.("hidden");
    preview.innerHTML = "";
    return;
  }
  hints?.classList?.add?.("hidden");
  detailBtn?.classList.remove("hidden");
  preview.classList.remove("hidden");
  preview.innerHTML = renderParsedPreviewHtml(parsed);
}

function updateMobileQuickPreview() {
  const input = document.getElementById("mobileQuickInput");
  const preview = document.getElementById("mobileQuickPreview");
  if (!input || !preview) return;
  const parsed = parseQuickEntry(input.value);
  if (!parsed) {
    preview.classList?.add?.("hidden");
    preview.innerHTML = "";
    return;
  }
  preview.classList?.remove?.("hidden");
  preview.innerHTML = renderParsedPreviewHtml(parsed);
}

async function submitQuickRawValue(raw, submitBtn, onSuccessReset) {
  const trimmed = String(raw || "").trim();
  if (!trimmed) {
    openTransactionEditor();
    return false;
  }
  const parsed = parseQuickEntry(trimmed);
  if (!parsed || !parsed.category_id) {
    openTransactionEditor(null, { title: trimmed });
    return false;
  }
  const payload = {
    client_id: financeUUID(),
    amount: parsed.amount,
    title: parsed.title,
    kind: parsed.kind,
    category_id: parsed.category_id,
    spent_on: parsed.spent_on,
    note: "",
    source_item_id: null,
  };
  if (submitBtn) submitBtn.disabled = true;
  try {
    try {
      await financeApi("/transactions", { method: "POST", body: JSON.stringify(payload) });
    } catch (error) {
      if (!error.network) throw error;
      queueExpense(payload);
      onSuccessReset?.();
      showToast("Đã lưu trên thiết bị. Tự đồng bộ khi có mạng.");
      renderPendingExpenses();
      updateFinanceConnection();
      return true;
    }
    onSuccessReset?.();
    showToast(`Đã ghi: ${parsed.title} (${formatVND(parsed.amount)})`);
    await refreshFinance();
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function submitQuickAdd(event) {
  event.preventDefault();
  const input = document.getElementById("quickAddInput");
  if (!input) return;
  await submitQuickRawValue(input.value, document.getElementById("quickAddSubmitBtn"), () => {
    input.value = "";
    updateQuickAddPreview();
  });
}

async function submitMobileQuickAdd(event) {
  event.preventDefault();
  const input = document.getElementById("mobileQuickInput");
  if (!input) return;
  const saved = await submitQuickRawValue(
    input.value,
    document.getElementById("mobileQuickSubmitBtn"),
    () => {
      input.value = "";
      updateMobileQuickPreview();
    },
  );
  if (saved && typeof hideModal === "function") hideModal("mobileQuickModal");
}

function openMobileQuickSheet() {
  if (document.documentElement?.classList?.contains?.("auth-locked")) return;
  const input = document.getElementById("mobileQuickInput");
  updateMobileQuickPreview();
  if (typeof showModal === "function") showModal("mobileQuickModal");
  setTimeout(() => input?.focus?.(), 40);
}

function openQuickAddInModal(sourceInputId = "quickAddInput") {
  const input = document.getElementById(sourceInputId);
  const parsed = parseQuickEntry(input?.value || "");
  if (sourceInputId === "mobileQuickInput" && typeof hideModal === "function") {
    hideModal("mobileQuickModal");
  }
  if (parsed) {
    openTransactionEditor(null, {
      amount: parsed.amount,
      title: parsed.title,
      kind: parsed.kind,
      category_id: parsed.category_id,
      spent_on: parsed.spent_on,
    });
  } else {
    openTransactionEditor();
  }
}

// =====================================================================
// KẾT NỐI API & CHUYỂN MÀN HÌNH
// =====================================================================
async function financeApi(path, options = {}) {
  const { timeoutMs = 15000, ...fetchOpts } = options;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(`/api/finance${path}`, {
      ...fetchOpts,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...fetchOpts.headers },
    });
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error("Yêu cầu quá thời gian chờ phản hồi. Hãy thử lại sau ít giây.");
    }
    const error = new Error("Chưa kết nối được máy chủ. Hãy kiểm tra kết nối và thử lại.");
    error.network = true;
    throw error;
  } finally {
    clearTimeout(timeout);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Dữ liệu chưa hợp lệ. Hãy kiểm tra các trường đã nhập.",
    );
    error.status = response.status;
    throw error;
  }
  return data;
}

function openPlanningWorkspace() {
  switchWorkspace(lastPlanningView);
}

function switchWorkspace(view) {
  if (!FINANCE_VIEWS[view]) view = "spending";
  const planning = ["plans", "recurring", "goals"].includes(view);
  if (planning) lastPlanningView = view;
  for (const key of Object.keys(FINANCE_VIEWS))
    document.getElementById(`${key}View`)?.classList.toggle("hidden", key !== view);
  const mainView = planning ? "plans" : view;
  document.querySelectorAll("[data-view]").forEach((button) => {
    if (button.dataset.view === mainView) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.querySelectorAll("[data-plan-view]").forEach((button) => {
    if (button.dataset.planView === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.getElementById("planningNav")?.classList.toggle("hidden", !planning);
  document.getElementById("workspaceTitle").textContent = FINANCE_VIEWS[view][0];
  document.getElementById("workspaceSubtitle").textContent = FINANCE_VIEWS[view][1];
  const ledgerTools = document.getElementById("ledgerTools");
  if (ledgerTools) ledgerTools.open = false;
  document
    .getElementById("mobileFabBtn")
    ?.classList?.toggle?.("is-view-hidden", view !== "spending");
  if (view === "spending") cashflowChart?.resize?.();
  window.scrollTo?.({ top: 0, behavior: "auto" });
  try {
    sessionStorage.setItem("smartspend-view", view);
  } catch (_) {}
}

function transactionQuery(offset = financeOffset, limit = 30) {
  const params = new URLSearchParams({ month: financeMonth, offset, limit });
  const category = document.getElementById("transactionCategoryFilter")?.value;
  const kind = document.getElementById("transactionKindFilter")?.value;
  const sort = document.getElementById("transactionSortSelect")?.value;
  const q = document.getElementById("transactionSearch")?.value.trim();
  if (category) params.set("category_id", category);
  if (kind) params.set("kind", kind);
  if (sort && sort !== "date_desc") params.set("sort", sort);
  if (financeDayFilter && financeDayFilter.startsWith(financeMonth + "-")) {
    params.set("day", financeDayFilter);
  }
  if (q) params.set("q", q);
  return params;
}

async function refreshFinance() {
  const epoch = ++financeEpoch;
  const month = financeMonth;
  try {
    const [categories, overview, transactions, bills, goals, preferences, trends] =
      await Promise.all([
        financeApi("/categories"),
        financeApi(`/overview?month=${month}`),
        financeApi(`/transactions?${transactionQuery()}`),
        financeApi("/recurring"),
        financeApi("/goals"),
        financeApi("/preferences"),
        financeApi(`/trends?months=6&end_month=${month}`).catch(() => null),
      ]);
    if (epoch !== financeEpoch) return;
    if (transactions.total > 0 && financeOffset >= transactions.total) {
      financeOffset = Math.floor((transactions.total - 1) / 30) * 30;
      await refreshFinance();
      return;
    }
    financeState = {
      categories,
      overview,
      trends,
      transactions: transactions.items,
      total: transactions.total,
      bills,
      goals,
      preferences,
    };
    financeCached = false;
    try {
      localStorage.setItem(
        window.smartspendStorageKey(`smartspend-cache:${month}`),
        JSON.stringify({
          ...financeState,
          queryKey: transactionQuery().toString(),
          savedAt: new Date().toISOString(),
        }),
      );
    } catch (_) {}
    if (!financePreferencesLoaded) {
      const people = document.getElementById("peopleInput");
      if (people && people.value === "2 người") people.value = preferences.people || "2 người";
      financePreferencesLoaded = true;
    }
    renderFinance();
  } catch (error) {
    if (epoch !== financeEpoch) return;
    if (error.status === 401) return;
    let cached;
    try {
      cached = JSON.parse(
        localStorage.getItem(window.smartspendStorageKey(`smartspend-cache:${month}`)) || "null",
      );
    } catch (_) {
      cached = null;
    }
    if (cached) {
      financeState = cached;
      if (cached.queryKey !== transactionQuery().toString()) {
        financeState = { ...cached, transactions: [], total: 0 };
      }
    } else financeState = { ...financeState, overview: null, transactions: [], total: 0 };
    financeCached = true;
    renderFinance();
    updateFinanceConnection(
      error.status === 404 ? "Hãy khởi động lại ứng dụng để tải các chức năng mới." : null,
    );
  }
}
window.refreshFinance = refreshFinance;

function renderFinance() {
  renderDueBillsBanner();
  renderFinanceStats();
  renderFinancePulse();
  renderHealthScore();
  renderAiCoachCached();
  renderCategoryBreakdown();
  renderDailySpending();
  renderSixMonthTrends();
  renderSpendingHeatmap();
  renderTransactions();
  renderRecurring();
  renderGoals();
  renderPendingExpenses();
  updateFinanceConnection();
  updateQuickAddPreview();

  const dayChip = document.getElementById("activeDayFilterChip");
  if (dayChip && dayChip.classList) {
    const activeDay =
      financeDayFilter && financeDayFilter.startsWith(financeMonth + "-") ? financeDayFilter : null;
    dayChip.classList.toggle("hidden", !activeDay);
    dayChip.textContent = activeDay ? `Ngày ${displayDate(activeDay)} ×` : "";
  }

  const filter = document.getElementById("transactionCategoryFilter");
  if (filter) {
    const old = filter.value;
    filter.innerHTML = `<option value="">Tất cả danh mục</option>${financeState.categories.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}${c.archived ? " (lưu trữ)" : ""}</option>`).join("")}`;
    filter.value = old;
    const sortVal = document.getElementById("transactionSortSelect")?.value;
    const activeFilters =
      Number(!!filter.value) +
      Number(!!document.getElementById("transactionKindFilter")?.value) +
      Number(!!document.getElementById("transactionSearch")?.value.trim()) +
      Number(!!sortVal && sortVal !== "date_desc") +
      Number(!!(financeDayFilter && financeDayFilter.startsWith(financeMonth + "-")));
    const filterLabel = document.getElementById("transactionFilterLabel");
    if (filterLabel) {
      filterLabel.textContent = activeFilters ? `Lọc (${activeFilters})` : "Lọc";
    }
    document.getElementById("toggleTxFilterBtn")?.classList?.toggle?.("active", activeFilters > 0);
  }
}

function renderFinanceStats() {
  const data = financeState.overview;
  const net = data ? (Number(data.income) || 0) - (Number(data.expense) || 0) : null;
  const remainingVal =
    data?.remaining != null
      ? formatVND(data.remaining)
      : net != null
        ? `${net >= 0 ? "+" : ""}${formatVND(net)}`
        : "—";
  const remainingLabel = data?.remaining != null ? "Còn lại" : "Chênh lệch";
  const isNegative = data?.remaining != null ? data.remaining < 0 : Boolean(net != null && net < 0);

  const budgetHtml =
    data?.budget == null
      ? `<button type="button" class="summary-budget-link" data-f-action="open-budget-editor">Đặt hạn mức</button>`
      : `<button type="button" class="summary-budget-val" data-f-action="open-budget-editor">${formatVND(data.budget)}</button>`;

  document.getElementById("financeStats").innerHTML = `
    <div class="summary-hero-metric">
      <span class="finance-stat-label">Đã chi</span>
      <strong class="summary-hero-amount">${data ? formatVND(data.expense) : "—"}</strong>
    </div>
    <div class="summary-sub-grid">
      <div class="summary-sub-item">
        <span class="finance-stat-label">Đã thu</span>
        <strong>${data ? formatVND(data.income) : "—"}</strong>
      </div>
      <div class="summary-sub-item${isNegative ? " is-negative" : ""}">
        <span class="finance-stat-label">${remainingLabel}</span>
        <strong>${remainingVal}</strong>
      </div>
      <div class="summary-sub-item">
        <span class="finance-stat-label">Ngân sách</span>
        ${budgetHtml}
      </div>
    </div>
  `;
}

function renderFinancePulse() {
  const pulse = document.getElementById("financePulse");
  if (!pulse) return;
  pulse.classList?.toggle?.("hidden", true);
  pulse.innerHTML = "";
}

function renderDueBillsBanner() {
  const banner = document.getElementById("dueBillsBanner");
  if (!banner || !banner.classList) return;
  const dueBills = financeState.overview?.highlights?.due_soon_bills || [];
  if (!dueBills.length) {
    banner.classList.add("hidden");
    banner.innerHTML = "";
    return;
  }
  const overdue = dueBills.filter((b) => b.overdue);
  const firstBill = overdue[0] || dueBills[0];
  const totalDue = dueBills.reduce((sum, b) => sum + (Number(b.amount) || 0), 0);
  banner.classList.remove("hidden");
  banner.classList.toggle("is-overdue", overdue.length > 0);
  const titleText = overdue.length
    ? `Quá hạn ${overdue.length} khoản: ${dueBills.map((b) => escapeHtml(b.name)).join(", ")}`
    : `${dueBills.length} khoản sắp đến hạn (${formatVND(totalDue)})`;
  banner.innerHTML = `
    <strong class="truncate text-xs sm:text-sm">${titleText}</strong>
    <div class="flex items-center gap-2">
      <button type="button" class="ui-button primary small" data-f-action="quick-pay-next-bill" data-bill-id="${firstBill.id}">
        Trả ${escapeHtml(firstBill.name)}
      </button>
      <button type="button" class="ui-button quiet small" data-action="jump-to-recurring">
        Xem
      </button>
    </div>
  `;
}

function renderHealthScore() {
  const card = document.getElementById("healthScoreCard");
  if (!card) return;
  const hs = financeState.overview?.health_score;
  const ins = financeState.overview?.insights;
  const hl = financeState.overview?.highlights;
  if (!hs) {
    card.innerHTML = `<p class="muted small">Đang tính điểm…</p>`;
    return;
  }
  const score = Math.max(0, Math.min(100, Number(hs.score) || 0));
  const circumference = 2 * Math.PI * 22;
  const dashOffset = circumference - (score / 100) * circumference;
  const ringColor = score >= 75 ? "#16a34a" : score >= 50 ? "#2563eb" : "#e11d48";

  const metaParts = [];
  if (ins?.observed_days > 0) {
    metaParts.push(`${ins.no_spend_days || 0}/${ins.observed_days} ngày 0₫`);
  }
  if (hl?.top_category) {
    metaParts.push(`${escapeHtml(hl.top_category.name)} ${hl.top_category.share_pct}%`);
  }

  const pillarsHtml = Array.isArray(hs.pillars)
    ? `<details class="pillars-disclosure"><summary>Chi tiết 4 trụ cột</summary><div class="health-pillars-grid">${hs.pillars
        .map((p) => {
          const pct = Math.min(
            100,
            Math.round(((Number(p.score) || 0) / Math.max(1, Number(p.max) || 1)) * 100),
          );
          return `<div class="health-pillar-item"><div class="flex justify-between text-[11px] tabular-nums"><span class="muted">${escapeHtml(p.label)}</span><strong class="text-strong">${p.score}/${p.max}</strong></div><span class="pillar-track"><i style="width:${pct}%;background:${ringColor}"></i></span></div>`;
        })
        .join("")}</div></details>`
    : "";

  card.innerHTML = `
    <div class="health-score-layout">
      <div class="health-ring-box" aria-label="Điểm sức khỏe ${score} trên 100">
        <svg viewBox="0 0 52 52" class="health-ring-svg">
          <circle cx="26" cy="26" r="22" class="health-ring-track"></circle>
          <circle
            cx="26"
            cy="26"
            r="22"
            class="health-ring-fill"
            style="stroke:${ringColor};stroke-dasharray:${circumference.toFixed(1)};stroke-dashoffset:${dashOffset.toFixed(1)}"
          ></circle>
        </svg>
        <div class="health-ring-value">
          <strong>${score}</strong>
        </div>
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-baseline gap-1.5">
          <h3 class="section-card-title">Điểm sức khỏe</h3>
          <span class="muted text-xs">· ${escapeHtml(hs.grade)}</span>
        </div>
        ${metaParts.length ? `<p class="muted text-xs mt-1 tabular-nums">${metaParts.join(" · ")}</p>` : ""}
      </div>
    </div>
    ${pillarsHtml}
  `;
}

function renderAiCoachCached() {
  const box = document.getElementById("aiCoachResult");
  if (!box) return;
  const cacheKey = `${financeMonth}:${currentCoachFocus}`;
  const cached = aiCoachMonthCache[cacheKey] || aiCoachMonthCache[financeMonth];
  if (!cached) {
    box.classList?.toggle?.("hidden", true);
    box.innerHTML = "";
    return;
  }
  box.classList?.toggle?.("hidden", false);
  const strengthsHtml = (cached.strengths || [])
    .map((s) => `<li class="coach-good">✓ ${escapeHtml(s)}</li>`)
    .join("");
  const warningsHtml = (cached.warnings || [])
    .map((w) => `<li class="coach-warn">! ${escapeHtml(w)}</li>`)
    .join("");
  const actionsHtml = (cached.action_items || [])
    .map((a, idx) => `<li><strong>${idx + 1}.</strong> ${escapeHtml(a)}</li>`)
    .join("");
  box.innerHTML = `
    <div class="coach-report space-y-2">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <strong class="text-strong text-xs sm:text-sm">${escapeHtml(cached.headline)}</strong>
        ${
          cached.suggested_daily_cap > 0
            ? `<span class="plan-meta-pill primary">Hạn mức: ${formatVND(cached.suggested_daily_cap)}/ngày</span>`
            : ""
        }
      </div>
      <p class="text-xs leading-relaxed">${escapeHtml(cached.summary)}</p>
      ${strengthsHtml || warningsHtml ? `<ul class="coach-bullets">${strengthsHtml}${warningsHtml}</ul>` : ""}
      ${actionsHtml ? `<ol class="coach-actions-list">${actionsHtml}</ol>` : ""}
    </div>
  `;
}

function setAiCoachFocus(focusText) {
  currentCoachFocus = String(focusText || "");
  document.querySelectorAll(".coach-focus-chip").forEach((chip) => {
    chip.classList.toggle("active", (chip.dataset.focus || "") === currentCoachFocus);
  });
  renderAiCoachCached();
}

async function runAiFinancialCoach() {
  const btn = document.getElementById("runAiCoachBtn");
  const box = document.getElementById("aiCoachResult");
  if (!box) return;
  if (btn) btn.disabled = true;
  box.classList?.toggle?.("hidden", false);
  box.innerHTML = `<span class="muted small">Đang phân tích ${escapeHtml(formatMonthLabel(financeMonth))}…</span>`;
  try {
    const res = await financeApi("/ai-review", {
      method: "POST",
      timeoutMs: 95000,
      body: JSON.stringify({ month: financeMonth, focus: currentCoachFocus }),
    });
    const cacheKey = `${financeMonth}:${currentCoachFocus}`;
    aiCoachMonthCache[cacheKey] = res.coaching;
    if (!currentCoachFocus) aiCoachMonthCache[financeMonth] = res.coaching;
    renderAiCoachCached();
    showToast("Đã phân tích xong!");
  } catch (error) {
    renderAiCoachCached();
    showToast(error.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function toggleHomePanel(panel, forceOpen = false) {
  const next = forceOpen ? panel : activeHomePanel === panel ? null : panel;
  activeHomePanel = next;

  const map = [
    ["calendar", "spendingHeatmapCard", "toggleCalendarBtn"],
    ["charts", "homePanelCharts", "toggleChartsBtn"],
    ["ai", "homePanelAi", "toggleAiBtn"],
  ];
  for (const [key, panelId, btnId] of map) {
    const isOpen = next === key;
    document.getElementById(panelId)?.classList?.toggle?.("hidden", !isOpen);
    const btn = document.getElementById(btnId);
    btn?.classList?.toggle?.("active", isOpen);
    btn?.setAttribute?.("aria-expanded", String(isOpen));
  }

  if (next === "charts") {
    cashflowChart?.resize?.();
    sixMonthTrendsChart?.resize?.();
    categoryDoughnutChart?.resize?.();
  }
}

function toggleTxFilter(forceOpen = false) {
  const panel = document.getElementById("transactionFilterPanel");
  const btn = document.getElementById("toggleTxFilterBtn");
  if (!panel) return;
  const willOpen = forceOpen ? true : panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !willOpen);
  btn?.setAttribute?.("aria-expanded", String(willOpen));
  if (willOpen) document.getElementById("transactionSearch")?.focus?.();
}

function switchSpendingChartMode(mode) {
  spendingChartMode = mode === "trends" ? "trends" : "daily";
  const dailyBtn = document.getElementById("chartModeDailyBtn");
  const trendsBtn = document.getElementById("chartModeTrendsBtn");
  const dailyWrap = document.getElementById("dailyChartModeWrap");
  const trendsWrap = document.getElementById("sixMonthTrendsWrap");
  const titleEl = document.getElementById("spendingChartTitle");
  const subEl = document.getElementById("spendingChartSubtitle");

  if (dailyBtn) {
    dailyBtn.className = spendingChartMode === "daily" ? "filter-chip active" : "filter-chip";
    dailyBtn.setAttribute("aria-pressed", String(spendingChartMode === "daily"));
  }
  if (trendsBtn) {
    trendsBtn.className = spendingChartMode === "trends" ? "filter-chip active" : "filter-chip";
    trendsBtn.setAttribute("aria-pressed", String(spendingChartMode === "trends"));
  }
  dailyWrap?.classList?.toggle?.("hidden", spendingChartMode !== "daily");
  trendsWrap?.classList?.toggle?.("hidden", spendingChartMode !== "trends");

  if (titleEl) {
    titleEl.textContent = spendingChartMode === "trends" ? "Xu hướng 6 tháng" : "Nhịp độ chi tiêu";
  }
  if (subEl) {
    subEl.textContent = spendingChartMode === "trends" ? "Thu — Chi 6 tháng" : "Chi ròng lũy kế";
  }
  if (spendingChartMode === "trends") {
    renderSixMonthTrends();
  } else {
    renderDailySpending();
  }
}

function renderSixMonthTrends() {
  if (sixMonthTrendsChart) {
    sixMonthTrendsChart.destroy();
    sixMonthTrendsChart = null;
  }
  const box = document.getElementById("sixMonthTrendsBox");
  const summaryEl = document.getElementById("sixMonthTrendsSummary");
  if (!box || !summaryEl) return;

  const trends = financeState.trends;
  if (!trends || !Array.isArray(trends.series) || !trends.series.length) {
    box.innerHTML = `<p class="empty-copy">Chưa có dữ liệu xu hướng nhiều tháng.</p>`;
    summaryEl.innerHTML = "";
    return;
  }

  box.innerHTML = `<div class="cashflow-canvas"><canvas id="sixMonthTrendsCanvas" role="img" aria-label="Biểu đồ thu chi 6 tháng"></canvas></div>`;
  const netTotal = Number(trends.cumulative_net_savings) || 0;
  summaryEl.innerHTML = `
    <span>Trung bình chi: <strong class="text-strong">${formatVND(trends.average_monthly_expense || 0)}/tháng</strong></span>
    <span>Tích lũy ròng 6 tháng: <strong class="${netTotal >= 0 ? "text-emerald-600" : "text-rose-600"}">${netTotal >= 0 ? "+" : ""}${formatVND(netTotal)}</strong></span>
  `;

  if (typeof Chart === "undefined") return;
  const canvas = document.getElementById("sixMonthTrendsCanvas");
  if (!canvas) return;
  const dark = typeof isDarkTheme === "function" && isDarkTheme();
  const tickColor = dark ? "#94a3b8" : "#64748b";
  const gridColor = dark ? "#1e293b" : "#f1f5f9";

  sixMonthTrendsChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: trends.series.map((s) => s.label),
      datasets: [
        {
          label: "Đã thu",
          data: trends.series.map((s) => s.income),
          backgroundColor: "#0ea5e9",
          borderRadius: 6,
        },
        {
          label: "Đã chi",
          data: trends.series.map((s) => s.expense),
          backgroundColor: "#6366f1",
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: { color: tickColor, font: { size: 11 }, boxWidth: 10 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${formatVND(ctx.raw)}`,
            afterBody: (items) => {
              const idx = items[0]?.dataIndex;
              const row = trends.series[idx];
              if (!row) return "";
              return `Chênh lệch ròng: ${row.net >= 0 ? "+" : ""}${formatVND(row.net)}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: tickColor, font: { size: 11 } },
          grid: { display: false },
          border: { display: false },
        },
        y: {
          ticks: {
            maxTicksLimit: 5,
            color: tickColor,
            font: { size: 10 },
            callback: (val) => compactMoneyTick(val),
          },
          grid: { color: gridColor },
          border: { display: false },
        },
      },
    },
  });
}
window.renderSixMonthTrends = renderSixMonthTrends;

function renderSpendingHeatmap() {
  const wrap = document.getElementById("spendingHeatmapGrid");
  const badge = document.getElementById("noSpendBadge");
  if (!wrap) return;
  const data = financeState.overview;
  if (!data || !Array.isArray(data.daily_cashflow)) {
    wrap.innerHTML = `<p class="empty-copy">Chưa có dữ liệu lịch chi tiêu.</p>`;
    if (badge) badge.textContent = "";
    return;
  }
  const [year, month] = financeMonth.split("-").map(Number);
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDow = (new Date(year, month - 1, 1).getDay() + 6) % 7; // Monday = 0 .. Sunday = 6
  const mapByDay = new Map();
  let maxExpense = 0;
  for (const row of data.daily_cashflow) {
    const d = Number(row.date.slice(-2));
    mapByDay.set(d, row);
    if (row.expense > maxExpense) maxExpense = row.expense;
  }
  const todayIso = localISODate();
  const ins = data.insights || {};
  if (badge) {
    badge.textContent =
      ins.observed_days > 0 ? `${ins.no_spend_days || 0} ngày không chi` : `Tháng ${month}/${year}`;
  }

  const headers = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    .map((h) => `<span class="heatmap-dow">${h}</span>`)
    .join("");
  const cells = [];
  for (let pad = 0; pad < firstDow; pad++) {
    cells.push(`<span class="heatmap-pad" aria-hidden="true"></span>`);
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${financeMonth}-${String(d).padStart(2, "0")}`;
    const entry = mapByDay.get(d) || { expense: 0, income: 0 };
    const isFuture = iso > todayIso;
    let level = "level-0";
    if (isFuture && entry.expense === 0 && entry.income === 0) {
      level = "level-future";
    } else if (entry.expense > 0 && maxExpense > 0) {
      const ratio = entry.expense / maxExpense;
      level =
        ratio > 0.75 ? "level-4" : ratio > 0.45 ? "level-3" : ratio > 0.18 ? "level-2" : "level-1";
    }
    const selected = financeDayFilter === iso ? "is-selected" : "";
    const hasIncome = entry.income > 0 ? "has-income" : "";
    const tip = `${displayDate(iso)} — Chi: ${formatVND(entry.expense)}${entry.income ? ` · Thu: +${formatVND(entry.income)}` : ""}`;
    cells.push(
      `<button type="button" class="heatmap-cell ${level} ${selected} ${hasIncome}" data-f-action="filter-by-day" data-day="${iso}" title="${escapeHtml(tip)}" aria-label="${escapeHtml(tip)}"><span>${d}</span></button>`,
    );
  }
  wrap.innerHTML = `
    <div class="heatmap-calendar">${headers}${cells.join("")}</div>
    <div class="heatmap-legend">
      <span>Chạm ngày để lọc</span>
      <span class="heatmap-scale">
        <i>0₫</i>
        <b class="heatmap-dot level-0"></b>
        <b class="heatmap-dot level-1"></b>
        <b class="heatmap-dot level-2"></b>
        <b class="heatmap-dot level-3"></b>
        <b class="heatmap-dot level-4"></b>
        <i>Cao</i>
      </span>
    </div>
  `;
}

function renderCategoryBreakdown() {
  if (categoryDoughnutChart) {
    categoryDoughnutChart.destroy();
    categoryDoughnutChart = null;
  }
  const data = financeState.overview;
  const entries = [...(data?.categories || [])].sort((a, b) => b.amount - a.amount);
  for (const budget of data?.budgets || [])
    if (budget.category_id && !entries.some((c) => c.category_id === budget.category_id))
      entries.push({ category_id: budget.category_id, amount: 0 });
  document.getElementById("categoryBreakdown").innerHTML = entries.length
    ? entries
        .map((entry) => {
          const category = financeCategory(entry.category_id);
          const budget = data.budgets.find((b) => b.category_id === entry.category_id);
          const ratio = budget
            ? budget.amount
              ? entry.amount / budget.amount
              : entry.amount
                ? 1
                : 0
            : entry.amount / Math.max(data.expense, 1);
          const sharePct =
            data?.expense > 0 && entry.amount > 0
              ? ` · ${Math.round((entry.amount / data.expense) * 100)}%`
              : "";
          return `<button type="button" class="category-bar" data-f-action="open-budget-editor" data-category-id="${entry.category_id}" aria-label="Ngân sách ${escapeHtml(category?.name || "Danh mục")}"><span class="bar-label"><span><i style="background:${colorFor(category)}"></i>${escapeHtml(category?.name || "Danh mục")}<small class="muted">${sharePct}</small></span><strong>${formatVND(entry.amount)}</strong></span><span class="thin-track"><span style="width:${Math.min(100, ratio * 100)}%;background:${colorFor(category)}"></span></span>${budget ? `<span class="bar-caption ${entry.amount > budget.amount ? "over-budget" : ""}">Hạn mức ${formatVND(budget.amount)}${entry.amount > budget.amount ? ` · Vượt ${formatVND(entry.amount - budget.amount)}` : ""}</span>` : ""}</button>`;
        })
        .join("")
    : financeEmpty(
        "Chưa có khoản chi trong tháng này.",
        '<button type="button" class="ui-button quiet" data-f-action="open-transaction-editor">Ghi khoản đầu tiên</button>',
      );

  const doughnutWrap = document.getElementById("categoryDoughnutWrap");
  const doughnutCanvas = document.getElementById("categoryDoughnutCanvas");
  const spentEntries = entries.filter((e) => e.amount > 0);
  if (doughnutWrap && doughnutWrap.classList) {
    doughnutWrap.classList.toggle(
      "hidden",
      !spentEntries.length || typeof Chart === "undefined" || !doughnutCanvas,
    );
  }
  if (spentEntries.length && doughnutCanvas && typeof Chart !== "undefined") {
    const dark = typeof isDarkTheme === "function" && isDarkTheme();
    categoryDoughnutChart = new Chart(doughnutCanvas, {
      type: "doughnut",
      data: {
        labels: spentEntries.map((e) => financeCategory(e.category_id)?.name || "Danh mục"),
        datasets: [
          {
            data: spentEntries.map((e) => e.amount),
            backgroundColor: spentEntries.map((e) => colorFor(financeCategory(e.category_id))),
            borderColor: dark ? "#131c2e" : "#ffffff",
            borderWidth: 2.5,
            hoverOffset: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "66%",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${formatVND(ctx.raw)}`,
            },
          },
        },
      },
    });
  }
}
window.renderCategoryBreakdown = renderCategoryBreakdown;

let cashflowChart = null;

// Daily closing balance: expenses increase the line; income decreases it.
function buildCashflowSeries(monthValue, rows, budget, currentDate = localISODate()) {
  const [year, month] = monthValue.split("-").map(Number);
  const days = new Date(year, month, 0).getDate();
  const byDay = new Map();
  for (const row of rows) {
    if (!row.date.startsWith(monthValue + "-")) continue;
    const day = Number(row.date.slice(-2));
    if (day < 1 || day > days) continue;
    const previous = byDay.get(day) || { expense: 0, income: 0 };
    byDay.set(day, {
      expense: previous.expense + row.expense,
      income: previous.income + row.income,
    });
  }
  const currentMonth = currentDate.slice(0, 7);
  const lastDay =
    monthValue < currentMonth
      ? days
      : Math.max(monthValue === currentMonth ? Number(currentDate.slice(-2)) : 0, ...byDay.keys());
  const points = [{ x: 0, y: 0, expense: 0, income: 0 }];
  let net = 0;
  for (let day = 1; day <= lastDay; day++) {
    const amounts = byDay.get(day) || { expense: 0, income: 0 };
    const next = net + amounts.expense - amounts.income;
    if (budget != null && (net - budget) * (next - budget) < 0) {
      points.push({ x: day - 1 + (budget - net) / (next - net), y: budget, crossing: true });
    }
    points.push({ x: day, y: next, ...amounts });
    net = next;
  }
  const peak = Math.max(0, ...points.map((p) => p.y));
  const lowest = Math.min(0, ...points.map((p) => p.y));
  return {
    points,
    days,
    net,
    peak,
    over: budget != null && net > budget,
    minimum: lowest < 0 ? lowest * 1.08 : 0,
    maximum:
      budget != null && budget > 0 && peak <= budget
        ? budget
        : Math.max(1, peak, budget || 0) * 1.08,
  };
}

function cashflowSegmentColor(context, budget) {
  return budget != null && Math.max(context.p0.parsed.y, context.p1.parsed.y) > budget
    ? "#dc2626"
    : "#6366f1";
}

function renderDailySpending() {
  if (cashflowChart) {
    cashflowChart.destroy();
    cashflowChart = null;
  }
  const data = financeState.overview;
  const container = document.getElementById("dailySpendingChart");
  const status = document.getElementById("monthBudgetStatus");
  if (!data || !Array.isArray(data.daily_cashflow)) {
    container.innerHTML = financeEmpty("Kết nối lại để tải biểu đồ thu chi trong tháng.");
    status.innerHTML = "";
    return;
  }
  const series = buildCashflowSeries(financeMonth, data.daily_cashflow, data.budget);
  const explanation = `Chi ròng lũy kế: ${formatVND(series.net)}. ${data.budget == null ? "Chưa đặt ngân sách tháng." : `Ngân sách ${formatVND(data.budget)}.${series.over ? ` Vượt ${formatVND(series.net - data.budget)}.` : ""}`}`;
  container.innerHTML = `<div class="cashflow-canvas"><canvas id="cashflowCanvas" role="img" aria-label="${escapeHtml(explanation)}"></canvas></div><div class="cashflow-legend"><span><i class="cashflow-key"></i>Chi ròng lũy kế</span>${data.budget != null ? '<span><i class="cashflow-key budget"></i>Hạn mức</span><span><i class="cashflow-key exceeded"></i>Vượt mức</span>' : ""}</div>`;
  status.classList.toggle("is-over-budget", series.over);
  status.innerHTML = `<span role="status">${data.budget == null ? "Chưa đặt hạn mức tháng" : series.over ? `Vượt hạn mức ${formatVND(series.net - data.budget)}` : `Chi ròng ${formatVND(series.net)} / ${formatVND(data.budget)}`}</span><button type="button" class="text-action" data-f-action="open-budget-editor">${data.budget == null ? "Đặt ngay" : "Sửa"}</button>`;
  if (typeof Chart === "undefined") {
    container.innerHTML = `<p class="empty-copy">${escapeHtml(explanation)}</p>`;
    return;
  }

  const dark = typeof isDarkTheme === "function" && isDarkTheme();
  const tickColor = dark ? "#94a3b8" : "#64748b";
  const gridColor = dark ? "#1e293b" : "#f1f5f9";

  const datasets = [
    {
      label: "Chi ròng lũy kế",
      data: series.points,
      borderWidth: 2.5,
      borderColor: "#6366f1",
      backgroundColor: "#6366f1",
      tension: 0,
      fill: false,
      pointRadius: (ctx) => (ctx.dataIndex === series.points.length - 1 ? 3 : 0),
      pointHoverRadius: (ctx) => (ctx.raw?.crossing ? 0 : 5),
      pointBackgroundColor: (ctx) =>
        data.budget != null && ctx.parsed.y > data.budget ? "#dc2626" : "#6366f1",
      segment: { borderColor: (ctx) => cashflowSegmentColor(ctx, data.budget) },
    },
  ];
  if (data.budget != null)
    datasets.push({
      label: "Ngân sách tháng",
      data: [
        { x: 0, y: data.budget },
        { x: series.days, y: data.budget },
      ],
      borderColor: "#94a3b8",
      borderWidth: 2,
      borderDash: [6, 5],
      pointRadius: 0,
      pointHitRadius: 0,
      fill: false,
    });
  cashflowChart = new Chart(document.getElementById("cashflowCanvas"), {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      layout: { padding: { top: 6, right: 6 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => item.datasetIndex === 0 && !item.raw.crossing,
          callbacks: {
            title: (items) =>
              items.length
                ? items[0].parsed.x === 0
                  ? "Đầu tháng"
                  : `Ngày ${items[0].parsed.x}/${financeMonth.slice(-2)}`
                : "",
            label: (item) => `Chi ròng: ${formatVND(item.parsed.y)}`,
            afterLabel: (item) =>
              item.parsed.x === 0
                ? ""
                : [
                    `Chi trong ngày: ${formatVND(item.raw.expense)}`,
                    `Thu trong ngày: ${formatVND(item.raw.income)}`,
                    ...(data.budget != null && item.parsed.y > data.budget
                      ? [`Vượt ngân sách: ${formatVND(item.parsed.y - data.budget)}`]
                      : []),
                  ],
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          min: 0,
          max: series.days,
          grid: { display: false },
          border: { display: false },
          ticks: {
            maxTicksLimit: 7,
            precision: 0,
            color: tickColor,
            font: { size: 10 },
            callback: (value) => (value === 0 ? "Đầu" : String(value).padStart(2, "0")),
          },
        },
        y: {
          min: series.minimum,
          max: series.maximum,
          border: { display: false },
          grid: { color: gridColor },
          ticks: {
            maxTicksLimit: 5,
            color: tickColor,
            font: { size: 10 },
            callback: (value) => compactMoneyTick(value),
          },
        },
      },
    },
  });
}
window.renderDailySpending = renderDailySpending;

function renderTransactions() {
  let lastDay = "";
  const list = document.getElementById("transactionList");
  const totalLabel = document.getElementById("transactionTotalLabel");
  if (totalLabel) {
    totalLabel.textContent = financeState.total ? `${financeState.total} giao dịch` : "";
  }
  list.innerHTML = financeState.transactions.length
    ? financeState.transactions
        .map((row) => {
          const category = financeCategory(row.category_id);
          const heading =
            row.spent_on !== lastDay
              ? `<div class="transaction-day">${displayDate(row.spent_on)}</div>`
              : "";
          lastDay = row.spent_on;
          return `${heading}<div class="transaction-row"><span class="transaction-symbol" style="color:${colorFor(category)}">${renderIcon(row.kind === "income" ? "arrow-down-left" : "receipt")}</span><button type="button" class="transaction-main" data-f-action="edit-transaction" data-tx-id="${row.id}"><strong>${escapeHtml(row.title)}</strong><span>${escapeHtml(category?.name || "Danh mục")}${row.source_item_id ? " · Từ kế hoạch" : row.recurring_id ? " · Định kỳ" : ""}${row.note ? ` · ${escapeHtml(row.note.slice(0, 45))}` : ""}</span></button><span class="transaction-amount ${row.kind === "income" ? "income" : ""}">${row.kind === "income" ? "+" : "−"}${formatVND(row.amount)}</span></div>`;
        })
        .join("")
    : financeEmpty(
        financeCached && !financeState.overview
          ? "Chưa kết nối được máy chủ. Dữ liệu sẽ hiện khi kết nối lại."
          : "Chưa có giao dịch phù hợp.",
      );
  const total = financeState.total;
  const totalPages = Math.ceil(total / 30);
  const currentPage = Math.min(Math.floor(financeOffset / 30) + 1, totalPages);
  document.getElementById("transactionPagination").innerHTML = total
    ? `<span>Trang ${currentPage}/${totalPages}</span><div><button type="button" class="icon-button" data-f-action="page-transactions" data-delta="-1" aria-label="Trang giao dịch trước" ${financeOffset === 0 ? "disabled" : ""}>${renderIcon("chevron-left")}</button><button type="button" class="icon-button" data-f-action="page-transactions" data-delta="1" aria-label="Trang giao dịch sau" ${financeOffset + 30 >= total ? "disabled" : ""}>${renderIcon("chevron-right")}</button></div>`
    : "";
}

function categoryOptions(selected, includeAll = false) {
  return `${includeAll ? '<option value="">Toàn bộ tháng</option>' : ""}${financeState.categories
    .filter((c) => !c.archived || c.id === Number(selected))
    .map(
      (c) =>
        `<option value="${c.id}" ${c.id === Number(selected) ? "selected" : ""}>${escapeHtml(c.name)}</option>`,
    )
    .join("")}`;
}

function formField(label, id, type, value = "", extra = "") {
  if (type === "number") {
    const minimum = extra.match(/\bmin="([^"]+)"/)?.[1] || "0";
    const maximum = extra.match(/\bmax="([^"]+)"/)?.[1] || "9000000000000";
    extra = extra.replace(/\s*\b(?:min|max|step|inputmode)="[^"]*"/g, "");
    return `<div class="editor-field"><label for="${id}">${label}</label><input id="${id}" name="${id}" type="text" inputmode="numeric" data-money data-money-min="${minimum}" data-money-max="${maximum}" value="${escapeHtml(formatMoneyInputValue(value))}" ${extra} /></div>`;
  }
  return `<div class="editor-field"><label for="${id}">${label}</label><input id="${id}" name="${id}" type="${type}" value="${escapeHtml(value)}" ${extra} /></div>`;
}
window.formField = formField;

function openFinanceEditor(title, body, save, buttonLabel = "Lưu") {
  financeEditorSave = save;
  document.getElementById("financeModalTitle").textContent = title;
  document.getElementById("financeModalBody").innerHTML = body;
  document
    .getElementById("financeModalBody")
    .querySelectorAll("input[data-money]")
    .forEach(formatMoneyInput);
  document.getElementById("financeFormError").classList.add("hidden");
  document.getElementById("financeModalActions").classList.toggle("hidden", !save);
  document.getElementById("financeSaveButton").textContent = buttonLabel;
  showModal("financeModal");
  document
    .querySelector('#financeModalBody input:not([type="hidden"]), #financeModalBody select')
    ?.focus();
}
window.openFinanceEditor = openFinanceEditor;

async function submitFinanceEditor(event) {
  event.preventDefault();
  if (!financeEditorSave) return;
  const button = document.getElementById("financeSaveButton");
  const errorBox = document.getElementById("financeFormError");
  errorBox.classList.add("hidden");
  button.disabled = true;
  const form = document.getElementById("financeEditorForm");
  const controls = [...form.querySelectorAll("input, select, textarea, button")];
  const wasDisabled = controls.map((c) => c.disabled);
  try {
    const save = financeEditorSave;
    document.getElementById("financeModal").dataset.busy = "true";
    const operation = save(new FormData(form));
    controls.forEach((c) => (c.disabled = true));
    await operation;
    delete document.getElementById("financeModal").dataset.busy;
    hideModal("financeModal");
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.classList.remove("hidden");
  } finally {
    delete document.getElementById("financeModal").dataset.busy;
    controls.forEach((c, i) => (c.disabled = wasDisabled[i]));
    button.disabled = false;
  }
}

function openTransactionEditor(row = null, defaults = {}) {
  if (!financeState.categories.some((c) => !c.archived)) {
    showToast("Hãy kết nối máy chủ và thêm danh mục trước.", true);
    return;
  }
  const initial = row || {
    client_id: financeUUID(),
    kind: "expense",
    spent_on: localISODate(),
    ...defaults,
  };
  initial.category_id ??=
    financeState.categories.find((c) => c.name === "Khác" && !c.archived)?.id ||
    financeState.categories.find((c) => !c.archived)?.id;
  const body = `<div class="editor-field"><label for="entryKind">Loại giao dịch</label><select id="entryKind" name="entryKind"><option value="expense" ${initial.kind !== "income" ? "selected" : ""}>Khoản chi</option><option value="income" ${initial.kind === "income" ? "selected" : ""} ${initial.source_item_id || initial.recurring_id ? "disabled" : ""}>Khoản thu</option></select></div>${formField("Số tiền (VNĐ)", "entryAmount", "number", initial.amount || "", 'min="1" max="9000000000000" step="1" required inputmode="numeric" placeholder="35.000"')}${formField("Nội dung", "entryTitle", "text", initial.title || "", 'required maxlength="255" placeholder="Ăn sáng"')}<div class="editor-field"><label for="entryCategory">Danh mục</label><select id="entryCategory" name="entryCategory" required>${categoryOptions(initial.category_id)}</select></div><details class="entry-more" ${row ? "open" : ""}><summary>Chi tiết thêm</summary><div class="entry-more-fields">${formField("Ngày", "entryDate", "date", initial.spent_on, "required")}<div class="editor-field"><label for="entryNote">Ghi chú</label><textarea id="entryNote" name="entryNote" maxlength="2000" rows="2">${escapeHtml(initial.note || "")}</textarea></div>${row ? `<div class="flex flex-wrap items-center justify-between gap-2 pt-1"><button type="button" class="text-action" data-f-action="duplicate-tx-today" data-tx-id="${row.id}">Nhân bản hôm nay</button><button id="deleteTransactionButton" type="button" class="text-action danger-action" data-f-action="delete-tx-from-editor" data-tx-id="${row.id}">Xóa giao dịch</button></div>` : ""}</div></details>`;
  openFinanceEditor(
    row ? "Sửa giao dịch" : initial.source_item_id ? "Ghi chi từ kế hoạch" : "Ghi thu/chi",
    body,
    async (form) => {
      const payload = {
        client_id: initial.client_id,
        amount: parseMoneyInput(form.get("entryAmount")),
        title: form.get("entryTitle").trim(),
        kind: form.get("entryKind"),
        category_id: Number(form.get("entryCategory")),
        spent_on: form.get("entryDate"),
        note: form.get("entryNote") || "",
        source_item_id: initial.source_item_id || null,
      };
      if (
        !payload.title ||
        !Number.isSafeInteger(payload.amount) ||
        payload.amount <= 0 ||
        payload.amount > 9e12
      )
        throw new Error("Nhập nội dung và số tiền nguyên lớn hơn 0.");
      if (row) {
        await financeApi(`/transactions/${row.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        try {
          await financeApi("/transactions", { method: "POST", body: JSON.stringify(payload) });
        } catch (error) {
          if (!error.network || initial.source_item_id) throw error;
          queueExpense(payload);
          showToast("Đã lưu trên thiết bị. Khoản này đang chờ đồng bộ.");
          renderPendingExpenses();
          updateFinanceConnection();
          return;
        }
      }
      showToast(row ? "Đã cập nhật giao dịch" : "Đã ghi giao dịch");
      await Promise.all([refreshFinance(), loadPlansFromDB()]);
    },
    row ? "Lưu thay đổi" : "Ghi giao dịch",
  );
}

async function editTransactionById(id) {
  try {
    openTransactionEditor(await financeApi(`/transactions/${id}`));
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteFinanceTransaction(id) {
  try {
    await financeApi(`/transactions/${id}`, { method: "DELETE" });
    await Promise.all([refreshFinance(), loadPlansFromDB()]);
    actionToast("Đã chuyển giao dịch vào thùng rác", "Hoàn tác", async () => {
      await financeApi(`/transactions/${id}/restore`, { method: "POST" });
      await Promise.all([refreshFinance(), loadPlansFromDB()]);
    });
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  }
}

async function deleteTransactionFromEditor(id) {
  const modal = document.getElementById("financeModal");
  if (modal.dataset.busy === "true") return;
  const button = document.getElementById("deleteTransactionButton");
  modal.dataset.busy = "true";
  button.disabled = true;
  try {
    const success = await deleteFinanceTransaction(id);
    modal.dataset.busy = "false";
    if (success) hideModal("financeModal");
  } finally {
    modal.dataset.busy = "false";
    button.disabled = false;
  }
}

async function duplicateTransactionToday(id) {
  try {
    const orig = await financeApi(`/transactions/${id}`);
    const payload = {
      client_id: financeUUID(),
      title: orig.title,
      amount: orig.amount,
      kind: orig.kind,
      spent_on: localISODate(),
      category_id: orig.category_id,
      note: orig.note || "",
      source_item_id: null,
    };
    await financeApi("/transactions", { method: "POST", body: JSON.stringify(payload) });
    hideModal("financeModal");
    showToast(`Đã nhân bản "${orig.title}" cho hôm nay`);
    await refreshFinance();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function copyPreviousMonthBudgets() {
  try {
    const res = await financeApi(`/budgets/${financeMonth}/copy-previous`, { method: "POST" });
    hideModal("financeModal");
    await refreshFinance();
    showToast(`Đã sao chép ${res.copied} hạn mức từ tháng ${res.source_month}`);
  } catch (error) {
    showToast(error.message, true);
  }
}

function openBudgetEditor(categoryId = null) {
  const existing = financeState.overview?.budgets.find((b) => b.category_id === categoryId);
  const copyPrevBtn = financeState.overview?.has_previous_budgets
    ? `<div class="mt-3 pt-3 border-t border-slate-200/60 dark:border-slate-700/60 flex items-center justify-between gap-2"><span class="muted small">Có hạn mức tháng trước</span><button type="button" class="ui-button quiet small" data-f-action="copy-prev-budgets">${renderIcon("copy", "icon-xs")} Sao chép</button></div>`
    : "";
  openFinanceEditor(
    `Ngân sách ${financeMonth.split("-").reverse().join("/")}`,
    `<div class="editor-field"><label for="budgetCategory">Phạm vi</label><select id="budgetCategory" name="budgetCategory">${categoryOptions(categoryId, true)}</select></div>${formField("Hạn mức (VNĐ)", "budgetAmount", "number", existing?.amount ?? "", 'min="0" max="9000000000000" step="1" required placeholder="3.000.000"')}${copyPrevBtn}`,
    async (form) => {
      await financeApi(`/budgets/${financeMonth}`, {
        method: "PUT",
        body: JSON.stringify({
          amount: parseMoneyInput(form.get("budgetAmount")),
          category_id: Number(form.get("budgetCategory")) || null,
        }),
      });
      await refreshFinance();
      showToast("Đã lưu ngân sách");
    },
  );
  const select = document.getElementById("budgetCategory");
  if (select) select.value = categoryId || "";
}

function fillBudgetAmount(value) {
  const input = document.getElementById("budgetAmount");
  input.value = formatMoneyInputValue(
    financeState.overview?.budgets.find((b) => b.category_id === (Number(value) || null))?.amount ??
      "",
  );
  formatMoneyInput(input);
}

// =====================================================================
// KHOẢN ĐỊNH KỲ & MỤC TIÊU TIẾT KIỆM
// =====================================================================
function renderRecurring() {
  const monthlyCommitment = financeState.overview?.insights?.monthly_recurring_commitment || 0;
  document.getElementById("recurringCount").textContent = monthlyCommitment
    ? `${financeState.bills.length} khoản đang theo dõi · Cam kết cố định ~${formatVND(monthlyCommitment)}/tháng`
    : `${financeState.bills.length} khoản đang theo dõi`;
  const names = { weekly: "Hằng tuần", monthly: "Hằng tháng", yearly: "Hằng năm" };
  const dueSoon = financeState.bills.filter(
    (b) => b.next_due <= localISODate(new Date(Date.now() + 3 * 86400000)),
  );
  const badge = document.getElementById("billDueCount");
  badge.textContent = dueSoon.length;
  badge.classList.toggle("hidden", !dueSoon.length);
  document.getElementById("recurringList").innerHTML = financeState.bills.length
    ? financeState.bills
        .map(
          (b) =>
            `<article class="surface collection-card"><div class="section-toolbar"><h3>${escapeHtml(b.name)}</h3><div class="card-tools"><button type="button" class="icon-button" data-f-action="open-bill-editor" data-bill-id="${b.id}" aria-label="Sửa ${escapeHtml(b.name)}">${renderIcon("pencil")}</button><button type="button" class="icon-button" data-f-action="archive-record" data-record-type="recurring" data-record-id="${b.id}" aria-label="Lưu trữ ${escapeHtml(b.name)}">${renderIcon("trash-2")}</button></div></div><strong class="collection-amount">${formatVND(b.amount)}</strong><p class="muted small">${escapeHtml(financeCategory(b.category_id)?.name || "")} · ${names[b.frequency]}</p><div class="collection-footer"><span class="due-label ${b.overdue ? "overdue" : ""}">${b.overdue ? "Quá hạn · " : "Hạn · "}${displayDate(b.next_due)}</span><button type="button" class="ui-button quiet small" data-f-action="open-bill-payment" data-bill-id="${b.id}">Thanh toán</button></div></article>`,
        )
        .join("")
    : financeEmpty(
        "Chưa có khoản định kỳ.",
        '<button type="button" class="ui-button primary small" data-f-action="open-bill-editor">Thêm khoản định kỳ</button>',
      );
}

function openBillEditor(id = null) {
  const bill = financeState.bills.find((b) => b.id === id) || {};
  openFinanceEditor(
    id ? "Sửa khoản định kỳ" : "Thêm khoản định kỳ",
    `${formField("Tên khoản", "billName", "text", bill.name || "", 'required maxlength="160" placeholder="Tiền Internet"')}${formField("Số tiền (VNĐ)", "billAmount", "number", bill.amount || "", 'min="1" max="9000000000000" step="1" required')}<div class="editor-columns"><div class="editor-field"><label for="billCategory">Danh mục</label><select id="billCategory" name="billCategory" required>${categoryOptions(bill.category_id)}</select></div><div class="editor-field"><label for="billFrequency">Lặp lại</label><select id="billFrequency" name="billFrequency"><option value="monthly">Hằng tháng</option><option value="weekly">Hằng tuần</option><option value="yearly">Hằng năm</option></select></div></div>${formField("Ngày đến hạn tiếp theo", "billDue", "date", bill.next_due || localISODate(), "required")}`,
    async (form) => {
      await financeApi(`/recurring${id ? `/${id}` : ""}`, {
        method: id ? "PUT" : "POST",
        body: JSON.stringify({
          name: form.get("billName").trim(),
          amount: parseMoneyInput(form.get("billAmount")),
          category_id: Number(form.get("billCategory")),
          frequency: form.get("billFrequency"),
          next_due: form.get("billDue"),
        }),
      });
      await refreshFinance();
      showToast("Đã lưu khoản định kỳ");
    },
  );
  const freq = document.getElementById("billFrequency");
  if (freq) freq.value = bill.frequency || "monthly";
}

function openBillPayment(id) {
  const bill = financeState.bills.find((b) => b.id === id);
  if (!bill) return;
  openFinanceEditor(
    "Ghi thanh toán",
    `<div class="payment-summary"><span>${escapeHtml(bill.name)}</span><strong>${formatVND(bill.amount)}</strong><span class="muted small">Hạn ${displayDate(bill.next_due)}</span></div>${formField("Ngày thanh toán", "billPaidOn", "date", localISODate(), "required")}`,
    async (form) => {
      await financeApi(`/recurring/${id}/pay`, {
        method: "POST",
        body: JSON.stringify({ due_on: bill.next_due, spent_on: form.get("billPaidOn") }),
      });
      await refreshFinance();
      showToast("Đã ghi thanh toán");
    },
    "Xác nhận",
  );
}

function renderGoals() {
  document.getElementById("goalsCount").textContent = `${financeState.goals.length} mục tiêu`;
  document.getElementById("goalsList").innerHTML = financeState.goals.length
    ? financeState.goals
        .map((g) => {
          const ratio = Math.round((g.saved / g.target) * 100);
          const isCompleted = Boolean(g.completed || g.saved >= g.target);
          const paceNote = isCompleted
            ? `<p class="muted small mt-2 font-semibold">Đã đạt mục tiêu</p>`
            : g.monthly_needed > 0 && g.days_left > 0
              ? `<p class="muted small mt-2 tabular-nums">~${formatVND(g.monthly_needed)}/tháng · Hạn ${displayDate(g.deadline)}</p>`
              : g.deadline
                ? `<p class="muted small mt-2 tabular-nums">Hạn ${displayDate(g.deadline)}</p>`
                : "";
          return `<article class="surface collection-card"><div class="section-toolbar"><h3>${escapeHtml(g.name)}</h3><div class="card-tools"><button type="button" class="icon-button" data-f-action="open-goal-editor" data-goal-id="${g.id}" aria-label="Sửa ${escapeHtml(g.name)}">${renderIcon("pencil")}</button><button type="button" class="icon-button" data-f-action="archive-record" data-record-type="goals" data-record-id="${g.id}" aria-label="Lưu trữ ${escapeHtml(g.name)}">${renderIcon("trash-2")}</button></div></div><strong class="collection-amount">${formatVND(g.saved)}</strong><div class="goal-track"><i style="width:${Math.min(100, ratio)}%"></i></div><div class="bar-label small tabular-nums"><span>Mục tiêu ${formatVND(g.target)}</span><strong>${ratio}%</strong></div>${paceNote}<div class="collection-footer"><button type="button" class="text-action" data-f-action="open-contribution-history" data-goal-id="${g.id}">Lịch sử</button><button type="button" class="ui-button quiet small" data-f-action="open-contribution-editor" data-goal-id="${g.id}">+ Thêm tiền</button></div></article>`;
        })
        .join("")
    : financeEmpty(
        "Chưa có mục tiêu tiết kiệm.",
        '<button type="button" class="ui-button primary small" data-f-action="open-goal-editor">Thêm mục tiêu</button>',
      );
}

function openGoalEditor(id = null) {
  const goal = financeState.goals.find((g) => g.id === id) || {};
  openFinanceEditor(
    id ? "Sửa mục tiêu" : "Thêm mục tiêu",
    `${formField("Tên mục tiêu", "goalName", "text", goal.name || "", 'required maxlength="160" placeholder="Quỹ dự phòng"')}${formField("Số tiền (VNĐ)", "goalTarget", "number", goal.target || "", 'min="1" max="9000000000000" step="1" required')}${formField("Ngày dự kiến", "goalDeadline", "date", goal.deadline || "")}`,
    async (form) => {
      await financeApi(`/goals${id ? `/${id}` : ""}`, {
        method: id ? "PUT" : "POST",
        body: JSON.stringify({
          name: form.get("goalName").trim(),
          target: parseMoneyInput(form.get("goalTarget")),
          deadline: form.get("goalDeadline") || null,
        }),
      });
      await refreshFinance();
      showToast("Đã lưu mục tiêu");
    },
  );
}

function openContributionEditor(id) {
  const goal = financeState.goals.find((g) => g.id === id);
  if (!goal) return;
  const clientId = financeUUID();
  openFinanceEditor(
    "Thêm tiền tiết kiệm",
    `<p class="muted small mb-3">${escapeHtml(goal.name)}</p>${formField("Số tiền (VNĐ)", "savedAmount", "number", "", 'required min="1" max="9000000000000" step="1"')}${formField("Ngày", "savedOn", "date", localISODate(), "required")}`,
    async (form) => {
      await financeApi(`/goals/${id}/contributions`, {
        method: "POST",
        body: JSON.stringify({
          client_id: clientId,
          amount: parseMoneyInput(form.get("savedAmount")),
          saved_on: form.get("savedOn"),
        }),
      });
      await refreshFinance();
      showToast("Đã cập nhật tiến độ mục tiêu");
    },
    "Thêm tiền",
  );
}

async function openContributionHistory(id) {
  try {
    const rows = await financeApi(`/goals/${id}/contributions`);
    openFinanceEditor(
      "Lịch sử dành tiền",
      rows.length
        ? rows
            .map(
              (r) =>
                `<div class="manager-row"><span>${displayDate(r.saved_on)}</span><strong>${formatVND(r.amount)}</strong><button type="button" class="icon-button" data-f-action="remove-contribution" data-contribution-id="${r.id}" data-goal-id="${id}" aria-label="Xóa khoản dành tiền ${displayDate(r.saved_on)}">${renderIcon("trash-2")}</button></div>`,
            )
            .join("")
        : '<p class="empty-copy">Chưa có khoản dành tiền.</p>',
      null,
    );
  } catch (error) {
    showToast(error.message, true);
  }
}

async function removeGoalContribution(id, goalId) {
  try {
    const prior = (await financeApi(`/goals/${goalId}/contributions`)).find((row) => row.id === id);
    if (!prior) return;
    await financeApi(`/contributions/${id}`, { method: "DELETE" });
    await refreshFinance();
    await openContributionHistory(goalId);
    actionToast("Đã xóa khoản dành tiền", "Hoàn tác", async () => {
      await financeApi(`/goals/${goalId}/contributions`, {
        method: "POST",
        body: JSON.stringify({
          client_id: prior.client_id,
          amount: prior.amount,
          saved_on: prior.saved_on,
        }),
      });
      await refreshFinance();
      if (
        !document.getElementById("financeModal").classList.contains("hidden") &&
        document.getElementById("financeModalTitle").textContent === "Lịch sử dành tiền"
      )
        await openContributionHistory(goalId);
    });
  } catch (error) {
    showToast(error.message, true);
  }
}

async function archiveFinanceRecord(type, id) {
  try {
    await financeApi(`/${type}/${id}`, { method: "DELETE" });
    await refreshFinance();
    actionToast("Đã chuyển vào kho lưu trữ", "Hoàn tác", async () => {
      await financeApi(`/${type}/${id}/restore`, { method: "POST" });
      await refreshFinance();
    });
  } catch (error) {
    showToast(error.message, true);
  }
}

// =====================================================================
// DANH MỤC, SỞ THÍCH & ĐỔI MẬT KHẨU
// =====================================================================
function openCategoryManager() {
  openFinanceEditor(
    "Quản lý danh mục",
    `<div class="section-toolbar mb-2"><p class="muted small">Lưu trữ danh mục vẫn giữ nguyên lịch sử giao dịch.</p><button type="button" class="ui-button soft small" data-f-action="open-category-editor">Thêm mới</button></div>${financeState.categories
      .filter((c) => !c.archived)
      .map(
        (c) =>
          `<div class="manager-row"><i class="category-dot" style="background:${colorFor(c)}"></i><span>${escapeHtml(c.name)}</span><button type="button" class="icon-button" data-f-action="open-category-editor" data-category-id="${c.id}" aria-label="Sửa danh mục ${escapeHtml(c.name)}">${renderIcon("pencil")}</button><button type="button" class="icon-button" data-f-action="archive-category" data-category-id="${c.id}" aria-label="Lưu trữ danh mục ${escapeHtml(c.name)}">${renderIcon("trash-2")}</button></div>`,
      )
      .join("")}`,
    null,
  );
}

function openCategoryEditor(id = null) {
  const category = financeCategory(id) || {};
  openFinanceEditor(
    id ? "Sửa danh mục" : "Thêm danh mục",
    `${formField("Tên danh mục", "categoryName", "text", category.name || "", 'required maxlength="80" placeholder="Thú cưng"')}<div class="editor-field"><label for="categoryColor">Màu nhận diện</label><select id="categoryColor" name="categoryColor">${Object.keys(
      FINANCE_COLORS,
    )
      .map(
        (key, index) =>
          `<option value="${key}">${["Cam", "Xanh lá", "Tím", "Xanh trời", "Chàm", "Hồng", "Xanh ngọc", "Xanh dương", "Xám"][index]}</option>`,
      )
      .join("")}</select></div>`,
    async (form) => {
      await financeApi(`/categories${id ? `/${id}` : ""}`, {
        method: id ? "PUT" : "POST",
        body: JSON.stringify({
          name: form.get("categoryName").trim(),
          color: form.get("categoryColor"),
        }),
      });
      await refreshFinance();
      showToast("Đã lưu danh mục");
    },
  );
  const col = document.getElementById("categoryColor");
  if (col) col.value = category.color || "indigo";
}

async function archiveFinanceCategory(id) {
  try {
    await financeApi(`/categories/${id}`, { method: "DELETE" });
    await refreshFinance();
    openCategoryManager();
    actionToast("Đã lưu trữ danh mục", "Hoàn tác", async () => {
      await financeApi(`/categories/${id}/restore`, { method: "POST" });
      await refreshFinance();
      if (
        !document.getElementById("financeModal").classList.contains("hidden") &&
        document.getElementById("financeModalTitle").textContent === "Quản lý danh mục"
      ) {
        openCategoryManager();
      }
    });
  } catch (error) {
    showToast(error.message, true);
  }
}

function openPreferencesEditor() {
  const prefs = financeState.preferences;
  openFinanceEditor(
    "Sở thích mặc định",
    `${formField("Số người thường dùng", "prefPeople", "text", prefs.people || "2 người", 'required maxlength="80"')}${formField("Khẩu vị, hoạt động yêu thích", "prefTastes", "text", prefs.tastes || "", 'maxlength="2000" placeholder="Món Việt, nấu nhanh…"')}${formField("Món hoặc nguyên liệu cần tránh", "prefAvoid", "text", prefs.avoid || "", 'maxlength="2000" placeholder="Không ăn cay…"')}`,
    async (form) => {
      await financeApi("/preferences", {
        method: "PUT",
        body: JSON.stringify({
          people: form.get("prefPeople"),
          tastes: form.get("prefTastes"),
          avoid: form.get("prefAvoid"),
        }),
      });
      const peopleInput = document.getElementById("peopleInput");
      if (peopleInput) peopleInput.value = form.get("prefPeople");
      await refreshFinance();
      showToast("Đã lưu sở thích mặc định");
    },
  );
}

function openChangePasswordEditor() {
  openFinanceEditor(
    "Đổi mật khẩu truy cập",
    `${formField("Mật khẩu hiện tại", "currentPwd", "password", "", 'required maxlength="256" autocomplete="current-password"')}${formField("Mật khẩu mới (ít nhất 12 ký tự)", "newPwd", "password", "", 'required minlength="12" maxlength="128" autocomplete="new-password"')}${formField("Nhập lại mật khẩu mới", "confirmPwd", "password", "", 'required minlength="12" maxlength="128" autocomplete="new-password"')}<p class="muted small">Sau khi đổi mật khẩu, tất cả các phiên đăng nhập cũ ở thiết bị khác sẽ tự động bị thu hồi.</p>`,
    async (form) => {
      const currentPassword = form.get("currentPwd");
      const newPassword = form.get("newPwd");
      const confirmPassword = form.get("confirmPwd");
      if (newPassword.length < 12) {
        throw new Error("Mật khẩu mới cần ít nhất 12 ký tự.");
      }
      if (newPassword !== confirmPassword) {
        throw new Error("Mật khẩu xác nhận chưa khớp.");
      }
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Chưa đổi được mật khẩu");
      showToast("Đã cập nhật mật khẩu và làm mới phiên bảo mật!");
    },
    "Cập nhật mật khẩu",
  );
}

// =====================================================================
// KHO LƯU TRỮ & THÙNG RÁC (ARCHIVE & TRASH CENTER)
// =====================================================================
async function openArchiveCenter() {
  try {
    const archive = await financeApi("/archive");
    const sections = [];

    if (archive.transactions.length) {
      sections.push(
        `<h4 class="font-semibold text-xs muted uppercase tracking-wider mb-2">Giao dịch đã xóa (${archive.transactions.length})</h4>` +
          archive.transactions
            .map(
              (t) =>
                `<div class="manager-row"><span><strong>${escapeHtml(t.title)}</strong><small class="block muted">${displayDate(t.spent_on)} · ${formatVND(t.amount)}</small></span><button type="button" class="ui-button soft small" data-f-action="restore-archive-item" data-archive-kind="transactions" data-archive-id="${t.id}">Khôi phục</button><button type="button" class="icon-button" data-f-action="purge-archive-tx" data-archive-id="${t.id}" title="Xóa vĩnh viễn">${renderIcon("trash-2")}</button></div>`,
            )
            .join(""),
      );
    }

    if (archive.plans.length) {
      sections.push(
        `<h4 class="font-semibold text-xs muted uppercase tracking-wider mt-4 mb-2">Kế hoạch đã xóa (${archive.plans.length})</h4>` +
          archive.plans
            .map(
              (p) =>
                `<div class="manager-row"><span><strong>${escapeHtml(p.title)}</strong><small class="block muted">Ngân sách ${formatVND(p.total_budget)}</small></span><button type="button" class="ui-button soft small" data-f-action="restore-archive-plan" data-archive-id="${p.archive_id}">Khôi phục</button><button type="button" class="icon-button" data-f-action="purge-archive-plan" data-archive-id="${p.archive_id}" title="Xóa vĩnh viễn">${renderIcon("trash-2")}</button></div>`,
            )
            .join(""),
      );
    }

    if (archive.bills.length) {
      sections.push(
        `<h4 class="font-semibold text-xs muted uppercase tracking-wider mt-4 mb-2">Khoản định kỳ lưu trữ (${archive.bills.length})</h4>` +
          archive.bills
            .map(
              (b) =>
                `<div class="manager-row"><span><strong>${escapeHtml(b.name)}</strong><small class="block muted">${formatVND(b.amount)}</small></span><button type="button" class="ui-button soft small" data-f-action="restore-archive-item" data-archive-kind="recurring" data-archive-id="${b.id}">Khôi phục</button></div>`,
            )
            .join(""),
      );
    }

    if (archive.goals.length) {
      sections.push(
        `<h4 class="font-semibold text-xs muted uppercase tracking-wider mt-4 mb-2">Mục tiêu lưu trữ (${archive.goals.length})</h4>` +
          archive.goals
            .map(
              (g) =>
                `<div class="manager-row"><span><strong>${escapeHtml(g.name)}</strong><small class="block muted">Mục tiêu ${formatVND(g.target)}</small></span><button type="button" class="ui-button soft small" data-f-action="restore-archive-item" data-archive-kind="goals" data-archive-id="${g.id}">Khôi phục</button></div>`,
            )
            .join(""),
      );
    }

    if (archive.categories.length) {
      sections.push(
        `<h4 class="font-semibold text-xs muted uppercase tracking-wider mt-4 mb-2">Danh mục lưu trữ (${archive.categories.length})</h4>` +
          archive.categories
            .map(
              (c) =>
                `<div class="manager-row"><span>${escapeHtml(c.name)}</span><button type="button" class="ui-button soft small" data-f-action="restore-archive-item" data-archive-kind="categories" data-archive-id="${c.id}">Khôi phục</button></div>`,
            )
            .join(""),
      );
    }

    openFinanceEditor(
      "Kho lưu trữ & Thùng rác",
      sections.length
        ? `<div class="space-y-1">${sections.join("")}</div>`
        : '<p class="empty-copy">Thùng rác và kho lưu trữ hiện đang trống.</p>',
      null,
    );
  } catch (error) {
    showToast(error.message, true);
  }
}

// =====================================================================
// SAO LƯU & NHẬP DỮ LIỆU (CSV / JSON BACKUP & IMPORT)
// =====================================================================
function sanitizeCsvCell(value) {
  const str = String(value ?? "");
  // Neutralize spreadsheet formula triggers without corrupting bullet notes like "- Mua rau"
  const safe = /^[\s]*(?:[=+@\t\r]|-(?=[\d=+@]))/.test(str) ? `'${str}` : str;
  return `"${safe.replaceAll('"', '""')}"`;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportTransactions() {
  try {
    const rows = [];
    for (let offset = 0; ; offset += 100) {
      const page = await financeApi(`/transactions?${transactionQuery(offset, 100)}`);
      rows.push(...page.items);
      if (rows.length >= page.total || !page.items.length) break;
    }
    const csv = [
      ["Ngày", "Nội dung", "Loại", "Danh mục", "Số tiền (VNĐ)", "Ghi chú"],
      ...rows.map((r) => [
        r.spent_on,
        r.title,
        r.kind === "expense" ? "Chi" : "Thu",
        financeCategory(r.category_id)?.name || "Khác",
        r.amount,
        r.note,
      ]),
    ]
      .map((r) => r.map(sanitizeCsvCell).join(","))
      .join("\r\n");
    downloadBlob(
      new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }),
      `chi-tieu-${financeMonth}.csv`,
    );
    showToast(`Đã xuất ${rows.length} giao dịch ra CSV`);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function exportYearCsv() {
  try {
    const year = financeMonth.slice(0, 4);
    const data = await financeApi(`/export?year=${year}`);
    const csv = [
      ["Ngày", "Nội dung", "Loại", "Danh mục", "Số tiền (VNĐ)", "Ghi chú"],
      ...data.transactions.map((r) => [
        r.spent_on,
        r.title,
        r.kind === "expense" ? "Chi" : "Thu",
        r.category_name || "Khác",
        r.amount,
        r.note,
      ]),
    ]
      .map((r) => r.map(sanitizeCsvCell).join(","))
      .join("\r\n");
    downloadBlob(
      new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }),
      `chi-tieu-nam-${year}.csv`,
    );
    showToast(`Đã xuất báo cáo năm ${year} (${data.transactions.length} giao dịch)`);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function exportFullJsonBackup() {
  try {
    const data = await financeApi("/export");
    const json = JSON.stringify(data, null, 2);
    downloadBlob(
      new Blob([json], { type: "application/json;charset=utf-8" }),
      `smartspend-backup-${localISODate()}.json`,
    );
    showToast(`Đã tải xuống bản sao lưu (${data.transactions.length} giao dịch)`);
  } catch (error) {
    showToast(error.message, true);
  }
}

function parseSimpleCsvLine(line) {
  const cells = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      cells.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  cells.push(current.trim());
  return cells;
}

function parseImportFileText(filename, text) {
  const clean = text.replace(/^\uFEFF/, "").trim();
  if (filename.toLowerCase().endsWith(".json")) {
    const data = JSON.parse(clean);
    const list = Array.isArray(data) ? data : data.transactions;
    if (!Array.isArray(list)) throw new Error("File JSON không đúng định dạng sao lưu SmartSpend.");
    return list.map((item) => ({
      client_id: item.client_id || null,
      title: String(item.title || "").trim(),
      amount: Number(item.amount),
      kind: item.kind === "income" ? "income" : "expense",
      spent_on: String(item.spent_on || ""),
      category_name: String(item.category_name || "Khác"),
      note: String(item.note || ""),
    }));
  }
  // Parse SmartSpend CSV: Ngày, Nội dung, Loại, Danh mục, Số tiền (VNĐ), Ghi chú
  const lines = clean.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) throw new Error("File CSV chưa có dòng dữ liệu giao dịch.");
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const [spentOn, title, kindLabel, categoryName, rawAmount, note = ""] = parseSimpleCsvLine(
      lines[i],
    );
    const numericAmount = Number(String(rawAmount || "").replace(/\./g, ""));
    if (!spentOn || !title || !Number.isSafeInteger(numericAmount) || numericAmount <= 0) continue;
    rows.push({
      client_id: null,
      spent_on: spentOn,
      title: title.replace(/^'(?=[=+@\t\r-])/, ""),
      kind: /^(thu|income)/i.test(kindLabel) ? "income" : "expense",
      category_name: categoryName || "Khác",
      amount: numericAmount,
      note: note.replace(/^'(?=[=+@\t\r-])/, ""),
    });
  }
  return rows;
}

function buildImportPayload(filename, text) {
  const clean = text.replace(/^\uFEFF/, "").trim();
  if (filename.toLowerCase().endsWith(".json")) {
    const data = JSON.parse(clean);
    if (data && !Array.isArray(data) && Number(data.version) >= 2) {
      return {
        version: 2,
        categories: Array.isArray(data.categories)
          ? data.categories.map((c) => ({
              name: String(c.name || "").trim(),
              color: c.color || "indigo",
              archived: Boolean(c.archived),
            }))
          : [],
        transactions: parseImportFileText(filename, text).slice(0, 5000),
        budgets: Array.isArray(data.budgets) ? data.budgets.slice(0, 500) : [],
        recurring_bills: Array.isArray(data.recurring_bills)
          ? data.recurring_bills.slice(0, 200)
          : [],
        goals: Array.isArray(data.goals) ? data.goals.slice(0, 200) : [],
        plans: Array.isArray(data.plans) ? data.plans.slice(0, 200) : [],
        preferences:
          data.preferences && typeof data.preferences === "object" ? data.preferences : null,
      };
    }
  }
  const transactions = parseImportFileText(filename, text);
  if (!transactions.length) {
    throw new Error("Không tìm thấy giao dịch hợp lệ trong file đã chọn.");
  }
  return { version: 1, transactions: transactions.slice(0, 5000) };
}

function openBackupCenter() {
  const year = financeMonth.slice(0, 4);
  openFinanceEditor(
    "Sao lưu & Nhập dữ liệu",
    `<div class="space-y-4">
      <div class="status-info-box space-y-2.5">
        <strong class="block text-strong">Xuất dữ liệu ra thiết bị</strong>
        <p class="muted small">Tải bảng tính CSV để mở bằng Excel/Numbers hoặc bản sao lưu JSON v2 đầy đủ (gồm Giao dịch, Ngân sách, Định kỳ, Mục tiêu &amp; Kế hoạch AI).</p>
        <div class="flex flex-wrap gap-2 pt-1">
          <button type="button" class="ui-button soft small" data-f-action="export-csv-month">${renderIcon("download")} CSV tháng ${financeMonth}</button>
          <button type="button" class="ui-button soft small" data-f-action="export-csv-year">${renderIcon("download")} CSV cả năm ${year}</button>
          <button type="button" class="ui-button primary small" data-f-action="export-json-all">${renderIcon("download")} Sao lưu JSON đầy đủ</button>
        </div>
      </div>

      <div class="editor-field mb-0">
        <label for="ledgerImportFile">Khôi phục / Nhập từ file (.json hoặc .csv)</label>
        <input id="ledgerImportFile" name="ledgerImportFile" type="file" accept=".json,.csv" />
        <p class="muted small mt-1">Các mục trùng định danh tự động được bỏ qua an toàn, không bao giờ bị nhân đôi.</p>
      </div>
    </div>`,
    async (form) => {
      const file = form.get("ledgerImportFile");
      if (!file || !file.size) {
        throw new Error("Hãy chọn một file .json hoặc .csv để nhập.");
      }
      const content = await file.text();
      const importPayload = buildImportPayload(file.name, content);
      const result = await financeApi("/import", {
        method: "POST",
        body: JSON.stringify(importPayload),
      });
      await Promise.all([refreshFinance(), window.loadPlansFromDB?.()]);
      const extras = [
        result.restored_plans ? `${result.restored_plans} kế hoạch` : "",
        result.restored_goals ? `${result.restored_goals} mục tiêu` : "",
        result.restored_bills ? `${result.restored_bills} khoản định kỳ` : "",
      ].filter(Boolean);
      showToast(
        `Đã nhập ${result.imported} giao dịch${extras.length ? `, ${extras.join(", ")}` : ""}${result.skipped ? ` (bỏ qua ${result.skipped} bản trùng)` : ""}!`,
      );
    },
    "Nhập dữ liệu",
  );
}

// =====================================================================
// HÀNG ĐỢI NGOẠI TUYẾN (OFFLINE EXPENSE OUTBOX)
// =====================================================================
window.migrateLegacyExpenseOutbox = () => {
  if (window.smartspendUserId !== "legacy-owner") return;
  try {
    const oldKey = "smartspend-outbox-v1";
    const legacy = JSON.parse(localStorage.getItem(oldKey) || "[]");
    if (Array.isArray(legacy)) {
      for (const row of legacy)
        if (row?.client_id)
          localStorage.setItem(`${expenseOutboxKey()}:${row.client_id}`, JSON.stringify(row));
      localStorage.removeItem(oldKey);
    }
    for (const key of Object.keys(localStorage)) {
      if (!key.startsWith(`${oldKey}:`)) continue;
      const row = JSON.parse(localStorage.getItem(key));
      if (row?.client_id) {
        localStorage.setItem(`${expenseOutboxKey()}:${row.client_id}`, JSON.stringify(row));
        localStorage.removeItem(key);
      }
    }
  } catch (_) {
    showToast("Chưa chuyển được khoản chờ đồng bộ cũ. Dữ liệu vẫn được giữ trên thiết bị.", true);
  }
};

function readExpenseOutbox() {
  if (!window.smartspendUserId) return [];
  try {
    const result = new Map();
    const legacy = JSON.parse(localStorage.getItem(expenseOutboxKey()) || "[]");
    if (Array.isArray(legacy)) legacy.forEach((row) => result.set(row.client_id, row));
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key?.startsWith(`${expenseOutboxKey()}:`)) continue;
      const row = JSON.parse(localStorage.getItem(key));
      if (row?.client_id) result.set(row.client_id, row);
    }
    return [...result.values()];
  } catch (_) {
    return [];
  }
}
function hasPendingExpenses() {
  return readExpenseOutbox().length > 0;
}
window.hasPendingExpenses = hasPendingExpenses;

function queueExpense(payload) {
  try {
    localStorage.setItem(`${expenseOutboxKey()}:${payload.client_id}`, JSON.stringify(payload));
  } catch (_) {
    throw new Error(
      "Thiết bị không lưu được khoản chờ đồng bộ. Hãy kết nối lại trước khi ghi chi.",
    );
  }
}
function removePendingExpense(id) {
  localStorage.removeItem(`${expenseOutboxKey()}:${id}`);
  const legacy = JSON.parse(localStorage.getItem(expenseOutboxKey()) || "[]");
  if (Array.isArray(legacy) && legacy.some((row) => row.client_id === id))
    localStorage.setItem(
      expenseOutboxKey(),
      JSON.stringify(legacy.filter((row) => row.client_id !== id)),
    );
}
function renderPendingExpenses() {
  const rows = readExpenseOutbox();
  document.getElementById("pendingTransactions").innerHTML = rows.length
    ? `<div class="pending-list"><div class="section-toolbar"><strong>${rows.length} giao dịch chờ đồng bộ</strong><button type="button" class="text-action" data-f-action="sync-outbox" ${financeSyncing ? "disabled" : ""}>${financeSyncing ? "Đang đồng bộ…" : "Đồng bộ ngay"}</button></div>${rows.map((r) => `<div class="pending-row"><span>${escapeHtml(r.title)}<small>${displayDate(r.spent_on)}</small></span><strong>${formatVND(r.amount)}</strong><button type="button" class="icon-button" ${financeSyncing ? "disabled" : ""} data-cancel-pending="${escapeHtml(r.client_id)}" aria-label="Bỏ khoản đang chờ: ${escapeHtml(r.title)}">${renderIcon("x")}</button></div>`).join("")}<p class="small muted">Sẽ tự động cộng vào báo cáo tháng ngay khi máy chủ xác nhận.</p></div>`
    : "";
}
async function syncExpenseOutbox() {
  if (financeSyncing || !window.smartspendUserId) return;
  financeSyncing = true;
  renderPendingExpenses();
  let failed = null;
  try {
    for (const payload of readExpenseOutbox()) {
      if (!readExpenseOutbox().some((r) => r.client_id === payload.client_id)) continue;
      try {
        await financeApi("/transactions", { method: "POST", body: JSON.stringify(payload) });
        removePendingExpense(payload.client_id);
      } catch (error) {
        failed = error;
        break;
      }
    }
  } finally {
    financeSyncing = false;
    renderPendingExpenses();
    updateFinanceConnection();
  }
  await refreshFinance();
  if (failed && !failed.network) showToast(`Chưa đồng bộ được: ${failed.message}`, true);
}
function updateFinanceConnection(message = null) {
  const el = document.getElementById("financeConnection");
  if (!el) return;
  const pending = readExpenseOutbox().length;
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  const show = financeCached || offline || pending;
  el.classList.toggle("hidden", !show);
  el.textContent =
    message ||
    (financeCached
      ? "Đang xem bản lưu ngoại tuyến trên thiết bị. Bạn vẫn có thể ghi giao dịch mới."
      : pending
        ? `${pending} giao dịch đang chờ đồng bộ lên máy chủ.`
        : "Thiết bị đang ngoại tuyến.");
  if (show) {
    const button = document.createElement("button");
    button.className = "text-action";
    button.type = "button";
    button.textContent = "Thử đồng bộ";
    button.addEventListener("click", syncExpenseOutbox);
    el.append(button);
  }
}

// =====================================================================
// ĐIỀU HƯỚNG THÁNG, PHÂN TRANG & TÍCH HỢP KẾ HOẠCH
// =====================================================================
function changeFinanceMonth(direction) {
  const [year, month] = financeMonth.split("-").map(Number);
  changeFinanceMonthTo(localISODate(new Date(year, month - 1 + direction, 1)).slice(0, 7));
}
function changeFinanceMonthTo(value) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return;
  financeMonth = value;
  financeDayFilter = null;
  financeOffset = 0;
  const monthInput = document.getElementById("financeMonth");
  if (monthInput) monthInput.value = value;
  syncMonthDisplay();
  refreshFinance();
}
function resetTransactionPage() {
  financeOffset = 0;
  refreshFinance();
}
function scheduleTransactionSearch() {
  clearTimeout(financeSearchTimer);
  financeSearchTimer = setTimeout(resetTransactionPage, 280);
}
function pageTransactions(direction) {
  financeOffset = Math.max(0, financeOffset + direction * 30);
  refreshFinance();
}

async function recordPlanPayment(itemId) {
  const item = currentPlan?.items.find((i) => i.id === itemId);
  if (!item) return;
  if (item.payment) {
    await editTransactionById(item.payment.id);
    return;
  }
  const name = currentPlan.plan_type === "meal" ? "Đi chợ" : "Đi chơi";
  openTransactionEditor(null, {
    title: item.name,
    amount: item.price || "",
    source_item_id: item.id,
    category_id: financeState.categories.find((c) => c.name === name && !c.archived)?.id,
  });
}
window.recordPlanPayment = recordPlanPayment;

async function copyActivePlan() {
  if (!currentPlan) return;
  try {
    const response = await fetch(`/api/plans/${currentPlan.id}/copy`, { method: "POST" });
    if (!response.ok) throw new Error("Chưa sao chép được kế hoạch");
    const plan = await response.json();
    await loadPlansFromDB(plan.id);
    showToast("Đã tạo bản sao kế hoạch mới");
  } catch (error) {
    showToast(error.message, true);
  }
}
window.copyActivePlan = copyActivePlan;

function openPlanReplacement(itemId) {
  const item = currentPlan?.items.find((i) => i.id === itemId);
  if (!item) return;
  openFinanceEditor(
    "Đổi một hạng mục bằng AI",
    `<p class="mb-3 font-semibold">${escapeHtml(item.name)}</p>${formField("Yêu cầu thay thế (tùy chọn)", "replacePreferences", "text", "", 'maxlength="2000" placeholder="Đổi sang món cá, ít dầu mỡ…"')}${item.category === "daily_menu" ? '<p class="muted small">Đổi thực đơn ngày không tự sửa nguyên liệu khác; hãy kiểm tra lại giỏ đi chợ.</p>' : ""}<p class="muted small">Phương án mới sẽ tự động giữ trong phần ngân sách còn lại.</p>`,
    async (form) => {
      const response = await fetch(`/api/items/${itemId}/replace`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: form.get("replacePreferences") }),
      });
      const data = await readAIResponse(response);
      if (!response.ok) throw new Error(data.detail || "Chưa đổi được hạng mục");
      applyUpdatedPlanFromServer(data.plan);
      showToast("Đã đổi hạng mục bằng AI");
    },
    "Đổi bằng AI",
  );
}
window.openPlanReplacement = openPlanReplacement;

// =====================================================================
// BẢNG LỆNH NHANH (COMMAND PALETTE — CTRL+K / ⌘K)
// =====================================================================
function normalizeCmdSearch(str) {
  return String(str || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
}

function getCommandPaletteActions() {
  return [
    {
      id: "new-tx",
      title: "Ghi khoản thu/chi mới",
      sub: "Mở hộp thoại nhập chi tiết số tiền, danh mục và ghi chú",
      icon: "plus",
      kbd: "N",
      run: () => openTransactionEditor(),
    },
    {
      id: "quick-add",
      title: "Nhập nhanh bằng tiếng Việt",
      sub: "Nhảy tới thanh Quick-Add (VD: 35k5 phở bò, 50 cành bún, 1tr5 tiền nhà)",
      icon: "zap",
      kbd: "Q",
      run: () => {
        switchWorkspace("spending");
        document.getElementById("quickAddInput")?.focus();
      },
    },
    {
      id: "ai-coach",
      title: "Phân tích dòng tiền tháng này",
      sub: "Xem chẩn đoán và hạn mức chi tiêu khuyến nghị mỗi ngày",
      icon: "trending-up",
      kbd: "",
      run: () => {
        switchWorkspace("spending");
        toggleHomePanel("ai", true);
        runAiFinancialCoach();
      },
    },
    {
      id: "trends-6m",
      title: "Xem biểu đồ Xu hướng Thu — Chi 6 tháng",
      sub: "So sánh thu nhập, chi tiêu và tích lũy ròng qua 6 tháng",
      icon: "bar-chart-3",
      kbd: "",
      run: () => {
        switchWorkspace("spending");
        toggleHomePanel("charts", true);
        switchSpendingChartMode("trends");
      },
    },
    {
      id: "ai-plan",
      title: "Lập kế hoạch Thực đơn / Đi chơi bằng AI",
      sub: "Thiết kế giỏ đi chợ gộp hoặc lịch trình hẹn hò sát giá Việt Nam",
      icon: "calendar-days",
      kbd: "2",
      run: () => {
        switchWorkspace("plans");
        document.getElementById("budgetInput")?.focus();
      },
    },
    {
      id: "set-budget",
      title: "Đặt hoặc điều chỉnh Ngân sách tháng",
      sub: "Thiết lập hạn mức chi tiêu tổng thể hoặc theo từng danh mục",
      icon: "wallet",
      kbd: "",
      run: () => openBudgetEditor(),
    },
    ...(financeState.overview?.has_previous_budgets
      ? [
          {
            id: "copy-budget",
            title: "Sao chép hạn mức ngân sách từ tháng trước",
            sub: "Áp dụng nhanh bộ hạn mức tháng gần nhất cho tháng đang xem",
            icon: "copy",
            kbd: "",
            run: () => copyPreviousMonthBudgets(),
          },
        ]
      : []),
    {
      id: "recurring",
      title: "Quản lý Khoản định kỳ & Hóa đơn",
      sub: "Xem lịch đến hạn tiền nhà, điện nước, Internet, gói đăng ký",
      icon: "repeat",
      kbd: "",
      run: () => switchWorkspace("recurring"),
    },
    {
      id: "goals",
      title: "Mục tiêu tiết kiệm & Tích lũy",
      sub: "Theo dõi tiến độ và mức cần dành mỗi tháng để đạt mục tiêu",
      icon: "target",
      kbd: "",
      run: () => switchWorkspace("goals"),
    },
    {
      id: "backup",
      title: "Sao lưu JSON v2 đầy đủ / Xuất CSV",
      sub: "Tải về toàn bộ dữ liệu sổ hoặc khôi phục từ bản sao lưu",
      icon: "download",
      kbd: "",
      run: () => openBackupCenter(),
    },
    {
      id: "archive",
      title: "Mở Kho lưu trữ & Thùng rác",
      sub: "Khôi phục giao dịch, kế hoạch, mục tiêu đã xóa hoặc lưu trữ",
      icon: "archive",
      kbd: "",
      run: () => openArchiveCenter(),
    },
    {
      id: "theme",
      title: "Chuyển đổi giao diện Sáng / Tối",
      sub: "Đổi chế độ màu hiển thị dịu mắt ngay lập tức",
      icon: "moon",
      kbd: "D",
      run: () => typeof toggleTheme === "function" && toggleTheme(),
    },
    {
      id: "pwa-qr",
      title: "Cài đặt ứng dụng trên iPhone / Điện thoại (PWA)",
      sub: "Mở mã QR và cài đặt ra màn hình chính hỗ trợ ngoại tuyến",
      icon: "smartphone",
      kbd: "",
      run: () => typeof openIphoneModal === "function" && openIphoneModal(),
    },
  ];
}

function getFilteredPaletteItems(rawQuery) {
  const actions = getCommandPaletteActions();
  const trimmed = String(rawQuery || "").trim();
  const parsedQuick = trimmed ? parseQuickEntry(trimmed) : null;
  const quickItem =
    parsedQuick && parsedQuick.category_id
      ? [
          {
            id: "__quick_entry__",
            title: `Ghi ngay: ${parsedQuick.title} (${parsedQuick.kind === "income" ? "+" : "−"}${formatVND(parsedQuick.amount)})`,
            sub: `Danh mục: ${parsedQuick.category_name} · Ngày ${displayDate(parsedQuick.spent_on)}`,
            icon: "zap",
            kbd: "Enter",
            run: async () => {
              const qInput = document.getElementById("quickAddInput");
              if (qInput) {
                qInput.value = trimmed;
                await submitQuickAdd({ preventDefault() {} });
              }
            },
          },
        ]
      : [];

  if (!trimmed) return [...quickItem, ...actions];
  const norm = normalizeCmdSearch(trimmed);
  const matched = actions.filter((item) =>
    normalizeCmdSearch(`${item.title} ${item.sub}`).includes(norm),
  );
  return matched.length ? [...matched, ...quickItem] : [...quickItem];
}

function renderCommandPaletteList() {
  const listEl = document.getElementById("commandPaletteList");
  const inputEl = document.getElementById("commandPaletteInput");
  if (!listEl) return;
  const items = getFilteredPaletteItems(inputEl?.value || "");
  if (!items.length) {
    listEl.innerHTML = `<p class="empty-copy">Không tìm thấy lệnh phù hợp. Bạn cũng có thể gõ thẳng "35k ăn sáng" để ghi nhanh!</p>`;
    return;
  }
  if (cmdSelectedIndex >= items.length) cmdSelectedIndex = 0;
  if (cmdSelectedIndex < 0) cmdSelectedIndex = items.length - 1;

  listEl.innerHTML = items
    .map(
      (item, idx) => `
      <button
        type="button"
        role="option"
        aria-selected="${idx === cmdSelectedIndex}"
        class="command-palette-item ${idx === cmdSelectedIndex ? "is-active" : ""}"
        data-f-action="run-cmd-item"
        data-cmd-idx="${idx}"
      >
        <span class="command-item-icon">${renderIcon(item.icon)}</span>
        <span class="command-item-body">
          <strong>${escapeHtml(item.title)}</strong>
          <small>${escapeHtml(item.sub)}</small>
        </span>
        ${item.kbd ? `<kbd>${escapeHtml(item.kbd)}</kbd>` : ""}
      </button>
    `,
    )
    .join("");
}

function executeCommandPaletteIndex(index) {
  const inputEl = document.getElementById("commandPaletteInput");
  const items = getFilteredPaletteItems(inputEl?.value || "");
  const chosen = items[index];
  if (!chosen) return;
  hideModal("commandPaletteModal");
  chosen.run();
}

function openCommandPalette() {
  if (document.documentElement?.classList?.contains("auth-locked")) return;
  const inputEl = document.getElementById("commandPaletteInput");
  if (inputEl) inputEl.value = "";
  cmdSelectedIndex = 0;
  renderCommandPaletteList();
  if (typeof showModal === "function") showModal("commandPaletteModal");
  inputEl?.focus?.();
}
window.openCommandPalette = openCommandPalette;
document.addEventListener("click", async (event) => {
  const tools = document.getElementById("ledgerTools");
  if (tools?.open && (!tools.contains(event.target) || event.target.closest("button"))) {
    tools.open = false;
  }

  const cancelBtn = event.target?.closest?.("[data-cancel-pending]");
  if (cancelBtn) {
    if (financeSyncing) return;
    try {
      removePendingExpense(cancelBtn.dataset.cancelPending);
      renderPendingExpenses();
      updateFinanceConnection();
    } catch (error) {
      showToast(error.message, true);
    }
    return;
  }

  const navBtn = event.target?.closest?.("[data-action]");
  if (navBtn) {
    switch (navBtn.dataset.action) {
      case "open-transaction-editor":
        openTransactionEditor();
        return;
      case "switch-workspace":
        switchWorkspace(navBtn.dataset.targetView);
        return;
      case "open-planning-workspace":
        openPlanningWorkspace();
        return;
      case "quick-add-detail":
        openQuickAddInModal();
        return;
      case "fill-quick-chip": {
        const qInput = document.getElementById("quickAddInput");
        if (qInput) {
          qInput.value = navBtn.dataset.sample || "";
          updateQuickAddPreview();
          qInput.focus();
        }
        return;
      }
      case "open-month-picker": {
        const mInput = document.getElementById("financeMonth");
        if (mInput) {
          if (typeof mInput.showPicker === "function") {
            try {
              mInput.showPicker();
            } catch (_) {
              mInput.focus?.();
            }
          } else {
            mInput.focus?.();
          }
        }
        return;
      }
      case "open-mobile-quick-sheet":
        openMobileQuickSheet();
        return;
      case "close-mobile-quick-sheet":
        hideModal("mobileQuickModal");
        return;
      case "fill-mobile-chip": {
        const mQuick = document.getElementById("mobileQuickInput");
        if (mQuick) {
          mQuick.value = navBtn.dataset.sample || "";
          updateMobileQuickPreview();
          mQuick.focus?.();
        }
        return;
      }
      case "mobile-open-detail":
        openQuickAddInModal("mobileQuickInput");
        return;
      case "jump-to-recurring":
        switchWorkspace("recurring");
        return;
      case "change-finance-month":
        changeFinanceMonth(Number(navBtn.dataset.delta));
        return;
      case "open-budget-editor":
        openBudgetEditor();
        return;
      case "open-category-manager":
        openCategoryManager();
        return;
      case "export-csv-month":
        exportTransactions();
        return;
      case "open-backup-center":
        openBackupCenter();
        return;
      case "open-archive-center":
        openArchiveCenter();
        return;
      case "open-bill-editor":
        openBillEditor();
        return;
      case "open-goal-editor":
        openGoalEditor();
        return;
      case "open-preferences":
        openPreferencesEditor();
        return;
      case "open-change-password":
        openChangePasswordEditor();
        return;
      case "logout-all-devices":
        window.logoutAllDevices?.();
        return;
      case "logout":
        window.logoutAccess?.();
        return;
      case "close-finance-modal":
        hideModal("financeModal");
        return;
      default:
        break;
    }
  }

  const fBtn = event.target?.closest?.("[data-f-action]");
  if (!fBtn) return;
  const fAction = fBtn.dataset.fAction;
  switch (fAction) {
    case "open-transaction-editor":
      openTransactionEditor();
      break;
    case "open-budget-editor":
      openBudgetEditor(fBtn.dataset.categoryId ? Number(fBtn.dataset.categoryId) : null);
      break;
    case "edit-transaction":
      editTransactionById(Number(fBtn.dataset.txId));
      break;
    case "delete-tx-from-editor":
      deleteTransactionFromEditor(Number(fBtn.dataset.txId));
      break;
    case "page-transactions":
      pageTransactions(Number(fBtn.dataset.delta));
      break;
    case "open-bill-editor":
      openBillEditor(fBtn.dataset.billId ? Number(fBtn.dataset.billId) : null);
      break;
    case "open-bill-payment":
      openBillPayment(Number(fBtn.dataset.billId));
      break;
    case "open-goal-editor":
      openGoalEditor(fBtn.dataset.goalId ? Number(fBtn.dataset.goalId) : null);
      break;
    case "open-contribution-editor":
      openContributionEditor(Number(fBtn.dataset.goalId));
      break;
    case "open-contribution-history":
      openContributionHistory(Number(fBtn.dataset.goalId));
      break;
    case "remove-contribution":
      removeGoalContribution(Number(fBtn.dataset.contributionId), Number(fBtn.dataset.goalId));
      break;
    case "archive-record":
      archiveFinanceRecord(fBtn.dataset.recordType, Number(fBtn.dataset.recordId));
      break;
    case "open-category-editor":
      openCategoryEditor(fBtn.dataset.categoryId ? Number(fBtn.dataset.categoryId) : null);
      break;
    case "archive-category":
      archiveFinanceCategory(Number(fBtn.dataset.categoryId));
      break;
    case "sync-outbox":
      syncExpenseOutbox();
      break;
    case "export-csv-month":
      exportTransactions();
      break;
    case "export-csv-year":
      exportYearCsv();
      break;
    case "export-json-all":
      exportFullJsonBackup();
      break;
    case "run-ai-coach":
      runAiFinancialCoach();
      break;
    case "set-coach-focus":
      setAiCoachFocus(fBtn.dataset.focus || "");
      break;
    case "switch-spending-chart-mode":
      switchSpendingChartMode(fBtn.dataset.mode || "daily");
      break;
    case "toggle-home-panel":
      toggleHomePanel(fBtn.dataset.panel || "calendar");
      break;
    case "toggle-tx-filter":
      toggleTxFilter();
      break;
    case "quick-pay-next-bill":
      openBillPayment(Number(fBtn.dataset.billId));
      break;
    case "copy-prev-budgets":
      copyPreviousMonthBudgets();
      break;
    case "duplicate-tx-today":
      duplicateTransactionToday(Number(fBtn.dataset.txId));
      break;
    case "run-cmd-item":
      executeCommandPaletteIndex(Number(fBtn.dataset.cmdIdx));
      break;
    case "filter-by-day": {
      const clickedDay = fBtn.dataset.day || null;
      financeDayFilter = financeDayFilter === clickedDay ? null : clickedDay;
      financeOffset = 0;
      refreshFinance();
      break;
    }
    case "clear-day-filter":
      financeDayFilter = null;
      financeOffset = 0;
      refreshFinance();
      break;
    case "restore-archive-item":
      try {
        await financeApi(`/${fBtn.dataset.archiveKind}/${fBtn.dataset.archiveId}/restore`, {
          method: "POST",
        });
        await Promise.all([refreshFinance(), window.loadPlansFromDB?.()]);
        showToast("Đã khôi phục dữ liệu");
        await openArchiveCenter();
      } catch (err) {
        showToast(err.message, true);
      }
      break;
    case "purge-archive-tx":
      try {
        await financeApi(`/transactions/${fBtn.dataset.archiveId}/permanent`, {
          method: "DELETE",
        });
        showToast("Đã xóa vĩnh viễn giao dịch");
        await openArchiveCenter();
      } catch (err) {
        showToast(err.message, true);
      }
      break;
    case "restore-archive-plan":
      try {
        const res = await fetch(`/api/plans/trash/${fBtn.dataset.archiveId}/restore`, {
          method: "POST",
        });
        if (!res.ok) throw new Error("Chưa khôi phục được kế hoạch");
        const restored = await res.json();
        await Promise.all([window.loadPlansFromDB?.(restored.id), refreshFinance()]);
        showToast("Đã khôi phục kế hoạch");
        await openArchiveCenter();
      } catch (err) {
        showToast(err.message, true);
      }
      break;
    case "purge-archive-plan":
      try {
        const res = await fetch(`/api/plans/trash/${fBtn.dataset.archiveId}`, {
          method: "DELETE",
        });
        if (!res.ok) throw new Error("Chưa xóa vĩnh viễn được kế hoạch");
        showToast("Đã xóa vĩnh viễn kế hoạch");
        await openArchiveCenter();
      } catch (err) {
        showToast(err.message, true);
      }
      break;
    default:
      break;
  }
});

document.addEventListener("change", (event) => {
  const el = event.target;
  if (!el) return;
  if (el.id === "financeMonth") changeFinanceMonthTo(el.value);
  else if (
    el.id === "transactionCategoryFilter" ||
    el.id === "transactionKindFilter" ||
    el.id === "transactionSortSelect"
  )
    resetTransactionPage();
  else if (el.id === "budgetCategory") fillBudgetAmount(el.value);
});

document.addEventListener("input", (event) => {
  const el = event.target;
  if (!el) return;
  if (el.id === "transactionSearch") scheduleTransactionSearch();
  else if (el.id === "quickAddInput") updateQuickAddPreview();
  else if (el.id === "mobileQuickInput") updateMobileQuickPreview();
  else if (el.id === "commandPaletteInput") {
    cmdSelectedIndex = 0;
    renderCommandPaletteList();
  }
});

document.addEventListener("keydown", (event) => {
  if (
    (event.ctrlKey || event.metaKey) &&
    !event.altKey &&
    (event.key === "k" || event.key === "K")
  ) {
    if (!document.documentElement?.classList?.contains("auth-locked")) {
      event.preventDefault();
      const palette = document.getElementById("commandPaletteModal");
      if (palette && !palette.classList.contains("hidden")) {
        hideModal("commandPaletteModal");
      } else {
        openCommandPalette();
      }
    }
    return;
  }

  const palette = document.getElementById("commandPaletteModal");
  if (palette && !palette.classList.contains("hidden")) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      cmdSelectedIndex++;
      renderCommandPaletteList();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      cmdSelectedIndex--;
      renderCommandPaletteList();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      executeCommandPaletteIndex(cmdSelectedIndex);
      return;
    }
  }

  const tools = document.getElementById("ledgerTools");
  if (event.key === "Escape" && tools?.open) {
    tools.open = false;
    tools.querySelector("summary")?.focus();
    return;
  }
  if (
    event.defaultPrevented ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    document.documentElement?.classList?.contains("auth-locked") ||
    document.querySelector?.('[role="dialog"]:not(.hidden)')
  ) {
    return;
  }
  const tag = event.target?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || event.target?.isContentEditable)
    return;

  if (event.key === "n" || event.key === "N") {
    event.preventDefault();
    openTransactionEditor();
  } else if (event.key === "q" || event.key === "Q") {
    event.preventDefault();
    switchWorkspace("spending");
    document.getElementById("quickAddInput")?.focus();
  } else if (event.key === "/") {
    event.preventDefault();
    switchWorkspace("spending");
    toggleTxFilter(true);
  } else if (event.key === "1") {
    event.preventDefault();
    switchWorkspace("spending");
  } else if (event.key === "2") {
    event.preventDefault();
    openPlanningWorkspace();
  } else if (event.key === "3") {
    event.preventDefault();
    switchWorkspace("account");
  } else if (event.key === "d" || event.key === "D") {
    event.preventDefault();
    if (typeof toggleTheme === "function") toggleTheme();
  } else if (event.key === "?") {
    event.preventDefault();
    if (typeof showModal === "function") showModal("shortcutsModal");
  }
});

window.addEventListener("storage", (event) => {
  if (event.key?.startsWith(OUTBOX_KEY)) {
    renderPendingExpenses();
    updateFinanceConnection();
  }
});
window.addEventListener("online", syncExpenseOutbox);
window.addEventListener("offline", () => updateFinanceConnection());

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("quickAddForm")?.addEventListener("submit", submitQuickAdd);
  document.getElementById("mobileQuickForm")?.addEventListener("submit", submitMobileQuickAdd);
  document.getElementById("financeEditorForm")?.addEventListener("submit", submitFinanceEditor);

  await window.smartspendAuthReady;
  const monthInput = document.getElementById("financeMonth");
  if (monthInput) monthInput.value = financeMonth;
  syncMonthDisplay();
  let initialView = "spending";
  try {
    const urlView =
      typeof location !== "undefined" && location.search
        ? new URLSearchParams(location.search).get("view")
        : null;
    initialView =
      urlView && FINANCE_VIEWS[urlView]
        ? urlView
        : sessionStorage.getItem("smartspend-view") || "spending";
  } catch (_) {}
  switchWorkspace(initialView);
  await refreshFinance();
  if (hasPendingExpenses() && navigator.onLine !== false) await syncExpenseOutbox();
});
