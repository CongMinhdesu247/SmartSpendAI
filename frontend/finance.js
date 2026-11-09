/* Personal ledger workspace. Plans and actual transactions remain independent. */
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
  spending: ["Sổ chi tiêu", "Thu, chi và ngân sách theo tháng."],
  plans: ["Kế hoạch", "Gợi ý AI, khoản định kỳ và mục tiêu tiết kiệm."],
  recurring: ["Khoản định kỳ", "Theo dõi lịch và xác nhận thanh toán."],
  goals: ["Mục tiêu tiết kiệm", "Theo dõi tiền dành riêng cho từng mục tiêu."],
  account: ["Tài khoản", "Sổ riêng và các tùy chọn của bạn."],
};
let lastPlanningView = "plans";
const OUTBOX_KEY = "smartspend-outbox-v2";
function expenseOutboxKey() {
  return window.smartspendStorageKey(OUTBOX_KEY);
}
let financeState = {
  categories: [],
  overview: null,
  transactions: [],
  total: 0,
  bills: [],
  goals: [],
  preferences: {},
};
let financeMonth = localISODate().slice(0, 7);
let financeOffset = 0,
  financeEpoch = 0,
  financeEditorSave = null,
  financeSearchTimer;
let financeCached = false,
  financeSyncing = false,
  financePreferencesLoaded = false;

function localISODate(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
function financeUUID() {
  if (crypto.randomUUID) return crypto.randomUUID();
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
function financeCategory(id) {
  return financeState.categories.find((c) => c.id === Number(id));
}
function colorFor(category) {
  return FINANCE_COLORS[category?.color] || FINANCE_COLORS.indigo;
}
function financeEmpty(message, action = "") {
  return `<div class="finance-empty">${renderIcon("receipt")}<p>${escapeHtml(message)}</p>${action}</div>`;
}

async function financeApi(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  let response;
  try {
    response = await fetch(`/api/finance${path}`, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch (_) {
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
    document.getElementById(`${key}View`).classList.toggle("hidden", key !== view);
  const mainView = planning ? "plans" : view;
  document.querySelectorAll("[data-view]").forEach((button) => {
    if (button.dataset.view === mainView) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.querySelectorAll("[data-plan-view]").forEach((button) => {
    if (button.dataset.planView === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.getElementById("planningNav").classList.toggle("hidden", !planning);
  document.getElementById("primaryLedgerAction").classList.toggle("hidden", view !== "spending");
  document.getElementById("workspaceTitle").textContent = FINANCE_VIEWS[view][0];
  document.getElementById("workspaceSubtitle").textContent = FINANCE_VIEWS[view][1];
  document.getElementById("ledgerTools").open = false;
  if (view === "spending") cashflowChart?.resize?.();
  window.scrollTo?.({ top: 0, behavior: "auto" });
  try {
    sessionStorage.setItem("smartspend-view", view);
  } catch (_) {
    /* Navigation still works without storage. */
  }
}

document.addEventListener("click", (event) => {
  const tools = document.getElementById("ledgerTools");
  if (tools?.open && (!tools.contains(event.target) || event.target.closest("button")))
    tools.open = false;
});
document.addEventListener("keydown", (event) => {
  const tools = document.getElementById("ledgerTools");
  if (event.key === "Escape" && tools?.open) {
    tools.open = false;
    tools.querySelector("summary").focus();
  }
});

function transactionQuery(offset = financeOffset, limit = 30) {
  const params = new URLSearchParams({ month: financeMonth, offset, limit });
  const category = document.getElementById("transactionCategoryFilter").value;
  const kind = document.getElementById("transactionKindFilter").value;
  const q = document.getElementById("transactionSearch").value.trim();
  if (category) params.set("category_id", category);
  if (kind) params.set("kind", kind);
  if (q) params.set("q", q);
  return params;
}

async function refreshFinance() {
  const epoch = ++financeEpoch;
  const month = financeMonth;
  try {
    const [categories, overview, transactions, bills, goals, preferences] = await Promise.all([
      financeApi("/categories"),
      financeApi(`/overview?month=${month}`),
      financeApi(`/transactions?${transactionQuery()}`),
      financeApi("/recurring"),
      financeApi("/goals"),
      financeApi("/preferences"),
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
    } catch (_) {
      /* Cache is optional; the server remains the source of truth. */
    }
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

function renderFinance() {
  renderFinanceStats();
  renderCategoryBreakdown();
  renderDailySpending();
  renderTransactions();
  renderRecurring();
  renderGoals();
  renderPendingExpenses();
  updateFinanceConnection();
  const filter = document.getElementById("transactionCategoryFilter");
  const old = filter.value;
  filter.innerHTML = `<option value="">Tất cả danh mục</option>${financeState.categories.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}${c.archived ? " (lưu trữ)" : ""}</option>`).join("")}`;
  filter.value = old;
  const activeFilters =
    Number(!!filter.value) +
    Number(!!document.getElementById("transactionKindFilter").value) +
    Number(!!document.getElementById("transactionSearch").value.trim());
  document.getElementById("transactionFilterLabel").textContent = activeFilters
    ? `Tìm kiếm và lọc (${activeFilters})`
    : "Tìm kiếm và lọc";
}

function renderFinanceStats() {
  const data = financeState.overview;
  const rows = [
    [
      "Ngân sách tháng",
      data?.budget == null ? "Chưa đặt" : formatVND(data.budget),
      "wallet",
      "indigo",
    ],
    ["Đã chi", data ? formatVND(data.expense) : "—", "arrow-up-right", "orange"],
    [
      "Còn trong ngân sách",
      data?.remaining == null ? "—" : formatVND(data.remaining),
      "piggy-bank",
      data?.remaining < 0 ? "rose" : "green",
    ],
    ["Đã thu", data ? formatVND(data.income) : "—", "arrow-down-left", "sky"],
  ];
  document.getElementById("financeStats").innerHTML = rows
    .map(
      ([label, value, icon, color]) =>
        `<div class="finance-stat tone-${color}"><div><span>${label}</span>${renderIcon(icon)}</div><strong>${value}</strong></div>`,
    )
    .join("");
}

function renderCategoryBreakdown() {
  const data = financeState.overview;
  const entries = [...(data?.categories || [])].sort((a, b) => b.amount - a.amount);
  // Include budgets with no spending so a newly set limit remains visible.
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
          return `<button type="button" class="category-bar" onclick="openBudgetEditor(${entry.category_id})" aria-label="Ngân sách ${escapeHtml(category?.name || "Danh mục")}"><span class="bar-label"><span><i style="background:${colorFor(category)}"></i>${escapeHtml(category?.name || "Danh mục")}</span><strong>${formatVND(entry.amount)}</strong></span><span class="thin-track"><span style="width:${Math.min(100, ratio * 100)}%;background:${colorFor(category)}"></span></span>${budget ? `<span class="bar-caption ${entry.amount > budget.amount ? "over-budget" : ""}">Hạn mức ${formatVND(budget.amount)}${entry.amount > budget.amount ? ` · Vượt ${formatVND(entry.amount - budget.amount)}` : ""}</span>` : ""}</button>`;
        })
        .join("")
    : financeEmpty(
        "Chưa có khoản chi trong tháng này.",
        '<button type="button" class="ui-button quiet" onclick="openTransactionEditor()">Ghi khoản đầu tiên</button>',
      );
}

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
    // Split a crossing exactly at the limit, so only the exceeded portion is red.
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
  container.innerHTML = `<div class="cashflow-canvas"><canvas id="cashflowCanvas" role="img" aria-label="${escapeHtml(explanation)}"></canvas></div><div class="cashflow-legend"><span><i class="cashflow-key"></i>Chi trừ thu (lũy kế)</span>${data.budget != null ? '<span><i class="cashflow-key budget"></i>Ngân sách tháng</span><span><i class="cashflow-key exceeded"></i>Vượt ngân sách</span>' : ""}</div><p class="cashflow-help">Chi tiền: đường tăng · Nhận tiền: đường giảm. Số dư chốt cuối mỗi ngày.</p>`;
  status.classList.toggle("is-over-budget", series.over);
  status.innerHTML = `<span role="status">${data.budget == null ? "Đặt ngân sách tháng để bật cảnh báo vượt chi." : series.over ? `Đã vượt ngân sách ${formatVND(series.net - data.budget)}` : `Chi ròng ${formatVND(series.net)} / ${formatVND(data.budget)}`}</span><button type="button" class="text-action" onclick="openBudgetEditor()">${data.budget == null ? "Đặt ngân sách" : "Điều chỉnh"}</button>`;
  if (typeof Chart === "undefined") {
    container.innerHTML = `<p class="empty-copy">${escapeHtml(explanation)}</p>`;
    return;
  }
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
            color: "#64748b",
            font: { size: 10 },
            callback: (value) => (value === 0 ? "Đầu" : String(value).padStart(2, "0")),
          },
        },
        y: {
          min: series.minimum,
          max: series.maximum,
          border: { display: false },
          grid: { color: "#f1f5f9" },
          ticks: {
            maxTicksLimit: 5,
            color: "#64748b",
            font: { size: 10 },
            callback: (value) =>
              new Intl.NumberFormat("vi-VN", {
                notation: "compact",
                maximumFractionDigits: 1,
              }).format(value) + " ₫",
          },
        },
      },
    },
  });
}

function renderTransactions() {
  let lastDay = "";
  const list = document.getElementById("transactionList");
  list.innerHTML = financeState.transactions.length
    ? financeState.transactions
        .map((row) => {
          const category = financeCategory(row.category_id);
          const heading =
            row.spent_on !== lastDay
              ? `<div class="transaction-day">${displayDate(row.spent_on)}</div>`
              : "";
          lastDay = row.spent_on;
          return `${heading}<div class="transaction-row"><span class="transaction-symbol" style="color:${colorFor(category)}">${renderIcon(row.kind === "income" ? "arrow-down-left" : "receipt")}</span><button type="button" class="transaction-main" onclick="editTransactionById(${row.id})"><strong>${escapeHtml(row.title)}</strong><span>${escapeHtml(category?.name || "Danh mục")}${row.source_item_id ? " · Từ kế hoạch" : row.recurring_id ? " · Định kỳ" : ""}</span></button><span class="transaction-amount ${row.kind === "income" ? "income" : ""}">${row.kind === "income" ? "+" : "−"}${formatVND(row.amount)}</span></div>`;
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
    ? `<span>Trang ${currentPage}/${totalPages}</span><div><button type="button" class="icon-button" onclick="pageTransactions(-1)" aria-label="Trang giao dịch trước" ${financeOffset === 0 ? "disabled" : ""}>${renderIcon("chevron-left")}</button><button type="button" class="icon-button" onclick="pageTransactions(1)" aria-label="Trang giao dịch sau" ${financeOffset + 30 >= total ? "disabled" : ""}>${renderIcon("chevron-right")}</button></div>`
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
    return `<div class="editor-field"><label for="${id}">${label}</label><input id="${id}" name="${id}" type="text" inputmode="numeric" data-money data-money-min="${minimum}" data-money-max="${maximum}" oninput="formatMoneyInput(this)" value="${escapeHtml(formatMoneyInputValue(value))}" ${extra} /></div>`;
  }
  return `<div class="editor-field"><label for="${id}">${label}</label><input id="${id}" name="${id}" type="${type}" value="${escapeHtml(value)}" ${extra} /></div>`;
}
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
async function submitFinanceEditor(event) {
  event.preventDefault();
  if (!financeEditorSave) return;
  const button = document.getElementById("financeSaveButton");
  const errorBox = document.getElementById("financeFormError");
  errorBox.classList.add("hidden");
  button.disabled = true;
  // Prevent closing or changing fields while the submitted write is in flight.
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
  const body = `<div class="editor-field"><label for="entryKind">Loại giao dịch</label><select id="entryKind" name="entryKind"><option value="expense" ${initial.kind !== "income" ? "selected" : ""}>Khoản chi</option><option value="income" ${initial.kind === "income" ? "selected" : ""} ${initial.source_item_id || initial.recurring_id ? "disabled" : ""}>Khoản thu</option></select></div>${formField("Số tiền (VNĐ)", "entryAmount", "number", initial.amount || "", 'min="1" max="9000000000000" step="1" required inputmode="numeric" placeholder="35000"')}${formField("Nội dung", "entryTitle", "text", initial.title || "", 'required maxlength="255" placeholder="Ăn sáng"')}<div class="editor-field"><label for="entryCategory">Danh mục</label><select id="entryCategory" name="entryCategory" required>${categoryOptions(initial.category_id)}</select></div><details class="entry-more" ${row && (row.note || row.spent_on !== localISODate()) ? "open" : ""}><summary>Thêm chi tiết</summary><div class="entry-more-fields">${formField("Ngày giao dịch", "entryDate", "date", initial.spent_on, "required")}<div class="editor-field"><label for="entryNote">Ghi chú (tùy chọn)</label><textarea id="entryNote" name="entryNote" maxlength="2000" rows="2">${escapeHtml(initial.note || "")}</textarea></div>${row ? `<button id="deleteTransactionButton" type="button" class="text-action danger-action" onclick="deleteTransactionFromEditor(${row.id})">Xóa giao dịch này</button>` : ""}</div></details>${initial.source_item_id ? '<p class="muted small">Khoản này liên kết với hạng mục trong kế hoạch.</p>' : ""}`;
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

function actionToast(message, label, action) {
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
  document.getElementById("toastContainer").append(toast);
  setTimeout(() => toast.remove(), 10000);
}
async function deleteFinanceTransaction(id) {
  try {
    await financeApi(`/transactions/${id}`, { method: "DELETE" });
    await Promise.all([refreshFinance(), loadPlansFromDB()]);
    actionToast("Đã xóa giao dịch", "Hoàn tác", async () => {
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

function openBudgetEditor(categoryId = null) {
  const existing = financeState.overview?.budgets.find((b) => b.category_id === categoryId);
  openFinanceEditor(
    `Ngân sách ${financeMonth.split("-").reverse().join("/")}`,
    `<div class="editor-field"><label for="budgetCategory">Phạm vi</label><select id="budgetCategory" name="budgetCategory" onchange="fillBudgetAmount(this.value)">${categoryOptions(categoryId, true)}</select></div>${formField("Hạn mức (VNĐ)", "budgetAmount", "number", existing?.amount ?? "", 'min="0" max="9000000000000" step="1" required placeholder="3.000.000"')}<p class="muted small">Ngân sách là hạn mức dự kiến, không phải số dư tài khoản.</p>`,
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
  document.getElementById("budgetCategory").value = categoryId || "";
}
function fillBudgetAmount(value) {
  const input = document.getElementById("budgetAmount");
  input.value = formatMoneyInputValue(
    financeState.overview?.budgets.find((b) => b.category_id === (Number(value) || null))?.amount ??
      "",
  );
  formatMoneyInput(input);
}

function renderRecurring() {
  document.getElementById("recurringCount").textContent =
    `${financeState.bills.length} khoản đang theo dõi`;
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
            `<article class="surface collection-card"><div class="section-toolbar"><span class="collection-icon tone-indigo">${renderIcon("repeat")}</span><div class="card-tools"><button type="button" class="icon-button" onclick="openBillEditor(${b.id})" aria-label="Sửa ${escapeHtml(b.name)}">${renderIcon("pencil")}</button><button type="button" class="icon-button" onclick="archiveFinanceRecord('recurring',${b.id})" aria-label="Lưu trữ ${escapeHtml(b.name)}">${renderIcon("trash-2")}</button></div></div><h3>${escapeHtml(b.name)}</h3><strong class="collection-amount">${formatVND(b.amount)}</strong><p class="muted small">${escapeHtml(financeCategory(b.category_id)?.name || "")} · ${names[b.frequency]}</p><div class="collection-footer"><span class="due-label ${b.overdue ? "overdue" : ""}">${b.overdue ? "Quá hạn · " : "Đến hạn · "}${displayDate(b.next_due)}</span><button type="button" class="ui-button soft" onclick="openBillPayment(${b.id})">Ghi thanh toán</button></div></article>`,
        )
        .join("")
    : financeEmpty(
        "Thêm tiền nhà, điện nước hoặc gói đăng ký để theo dõi ngày đến hạn.",
        '<button type="button" class="ui-button soft" onclick="openBillEditor()">Thêm khoản định kỳ</button>',
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
  document.getElementById("billFrequency").value = bill.frequency || "monthly";
}
function openBillPayment(id) {
  const bill = financeState.bills.find((b) => b.id === id);
  if (!bill) return;
  openFinanceEditor(
    "Ghi thanh toán",
    `<div class="payment-summary"><span>${escapeHtml(bill.name)}</span><strong>${formatVND(bill.amount)}</strong><span class="muted small">Kỳ đến hạn ${displayDate(bill.next_due)}</span></div>${formField("Ngày thanh toán", "billPaidOn", "date", localISODate(), "required")}<p class="muted small">Tạo một khoản chi và chuyển lịch sang kỳ tiếp theo.</p>`,
    async (form) => {
      await financeApi(`/recurring/${id}/pay`, {
        method: "POST",
        body: JSON.stringify({ due_on: bill.next_due, spent_on: form.get("billPaidOn") }),
      });
      await refreshFinance();
      showToast("Đã ghi thanh toán");
    },
    "Xác nhận thanh toán",
  );
}

function renderGoals() {
  document.getElementById("goalsCount").textContent = `${financeState.goals.length} mục tiêu`;
  document.getElementById("goalsList").innerHTML = financeState.goals.length
    ? financeState.goals
        .map((g) => {
          const ratio = Math.round((g.saved / g.target) * 100);
          return `<article class="surface collection-card"><div class="section-toolbar"><span class="collection-icon tone-green">${renderIcon("target")}</span><div class="card-tools"><button type="button" class="icon-button" onclick="openGoalEditor(${g.id})" aria-label="Sửa ${escapeHtml(g.name)}">${renderIcon("pencil")}</button><button type="button" class="icon-button" onclick="archiveFinanceRecord('goals',${g.id})" aria-label="Lưu trữ ${escapeHtml(g.name)}">${renderIcon("trash-2")}</button></div></div><h3>${escapeHtml(g.name)}</h3><strong class="collection-amount">${formatVND(g.saved)}</strong><div class="goal-track"><i style="width:${Math.min(100, ratio)}%"></i></div><div class="bar-label small"><span>Mục tiêu ${formatVND(g.target)}</span><strong>${ratio}%</strong></div>${g.deadline ? `<p class="muted small">${g.deadline < localISODate() && g.saved < g.target ? "Đã qua ngày dự kiến" : "Dự kiến"} · ${displayDate(g.deadline)}</p>` : ""}<div class="collection-footer"><button type="button" class="text-action" onclick="openContributionHistory(${g.id})">Lịch sử</button><button type="button" class="ui-button soft" onclick="openContributionEditor(${g.id})">Thêm tiền</button></div></article>`;
        })
        .join("")
    : financeEmpty(
        "Bắt đầu với một điều bạn muốn dành tiền cho.",
        '<button type="button" class="ui-button soft" onclick="openGoalEditor()">Tạo mục tiêu đầu tiên</button>',
      );
}
function openGoalEditor(id = null) {
  const goal = financeState.goals.find((g) => g.id === id) || {};
  openFinanceEditor(
    id ? "Sửa mục tiêu" : "Thêm mục tiêu",
    `${formField("Tên mục tiêu", "goalName", "text", goal.name || "", 'required maxlength="160" placeholder="Chuyến đi Đà Lạt"')}${formField("Số tiền mục tiêu (VNĐ)", "goalTarget", "number", goal.target || "", 'min="1" max="9000000000000" step="1" required')}${formField("Ngày dự kiến (tùy chọn)", "goalDeadline", "date", goal.deadline || "")}`,
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
    "Thêm tiền vào mục tiêu",
    `<p class="muted">${escapeHtml(goal.name)}</p>${formField("Số tiền dành thêm (VNĐ)", "savedAmount", "number", "", 'required min="1" max="9000000000000" step="1"')}${formField("Ngày", "savedOn", "date", localISODate(), "required")}<p class="muted small">Đây là ghi nhận tiền dành riêng, không tạo khoản chi hoặc chuyển tiền ngân hàng.</p>`,
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
                `<div class="manager-row"><span>${displayDate(r.saved_on)}</span><strong>${formatVND(r.amount)}</strong><button type="button" class="icon-button" onclick="removeGoalContribution(${r.id},${id})" aria-label="Xóa khoản dành tiền ${displayDate(r.saved_on)}">${renderIcon("trash-2")}</button></div>`,
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
    actionToast("Đã lưu trữ", "Hoàn tác", async () => {
      await financeApi(`/${type}/${id}/restore`, { method: "POST" });
      await refreshFinance();
    });
  } catch (error) {
    showToast(error.message, true);
  }
}

function openCategoryManager() {
  openFinanceEditor(
    "Danh mục",
    `<div class="section-toolbar"><p class="muted small">Lưu trữ danh mục vẫn giữ lịch sử giao dịch.</p><button type="button" class="ui-button soft" onclick="openCategoryEditor()">Thêm</button></div>${financeState.categories
      .filter((c) => !c.archived)
      .map(
        (c) =>
          `<div class="manager-row"><i class="category-dot" style="background:${colorFor(c)}"></i><span>${escapeHtml(c.name)}</span><button type="button" class="icon-button" onclick="openCategoryEditor(${c.id})" aria-label="Sửa danh mục ${escapeHtml(c.name)}">${renderIcon("pencil")}</button><button type="button" class="icon-button" onclick="archiveFinanceCategory(${c.id})" aria-label="Lưu trữ danh mục ${escapeHtml(c.name)}">${renderIcon("trash-2")}</button></div>`,
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
  document.getElementById("categoryColor").value = category.color || "indigo";
}
async function archiveFinanceCategory(id) {
  try {
    await financeApi(`/categories/${id}`, { method: "DELETE" });
    await refreshFinance();
    openCategoryManager();
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
      document.getElementById("peopleInput").value = form.get("prefPeople");
      await refreshFinance();
      showToast("Đã lưu sở thích");
    },
  );
}

// Only the verified original owner may import the pre-account offline queue.
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
    // Read the earlier array format as well, without dropping any pending rows.
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
function queueExpense(payload) {
  // One storage key per UUID prevents two tabs from overwriting each other's queue.
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
    ? `<div class="pending-list"><div class="section-toolbar"><strong>${rows.length} giao dịch chờ đồng bộ</strong><button type="button" class="text-action" onclick="syncExpenseOutbox()" ${financeSyncing ? "disabled" : ""}>${financeSyncing ? "Đang đồng bộ…" : "Đồng bộ"}</button></div>${rows.map((r) => `<div class="pending-row"><span>${escapeHtml(r.title)}<small>${displayDate(r.spent_on)}</small></span><strong>${formatVND(r.amount)}</strong><button type="button" class="icon-button" ${financeSyncing ? "disabled" : ""} data-cancel-pending="${escapeHtml(r.client_id)}" aria-label="Bỏ khoản đang chờ: ${escapeHtml(r.title)}">${renderIcon("x")}</button></div>`).join("")}<p class="small muted">Chưa cộng vào báo cáo tháng cho đến khi máy chủ xác nhận.</p></div>`
    : "";
}
async function syncExpenseOutbox() {
  if (financeSyncing || !window.smartspendUserId) return;
  financeSyncing = true;
  renderPendingExpenses();
  let failed = null;
  try {
    // Re-read before every write; deleting from the queue never discards other tabs' additions.
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
  const pending = readExpenseOutbox().length;
  const show = financeCached || !navigator.onLine || pending;
  el.classList.toggle("hidden", !show);
  el.textContent =
    message ||
    (financeCached
      ? "Đang xem dữ liệu đã lưu trên thiết bị. Máy chủ chưa kết nối."
      : pending
        ? `${pending} giao dịch đang chờ đồng bộ.`
        : "Thiết bị đang ngoại tuyến.");
  if (show) {
    const button = document.createElement("button");
    button.className = "text-action";
    button.type = "button";
    button.textContent = "Thử đồng bộ";
    button.onclick = syncExpenseOutbox;
    el.append(button);
  }
}
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-cancel-pending]");
  if (!button) return;
  if (financeSyncing) return;
  try {
    removePendingExpense(button.dataset.cancelPending);
    renderPendingExpenses();
    updateFinanceConnection();
  } catch (error) {
    showToast(error.message, true);
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

function changeFinanceMonth(direction) {
  const [year, month] = financeMonth.split("-").map(Number);
  changeFinanceMonthTo(localISODate(new Date(year, month - 1 + direction, 1)).slice(0, 7));
}
function changeFinanceMonthTo(value) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return;
  financeMonth = value;
  financeOffset = 0;
  document.getElementById("financeMonth").value = value;
  refreshFinance();
}
function resetTransactionPage() {
  financeOffset = 0;
  refreshFinance();
}
function scheduleTransactionSearch() {
  clearTimeout(financeSearchTimer);
  financeSearchTimer = setTimeout(resetTransactionPage, 300);
}
function pageTransactions(direction) {
  financeOffset = Math.max(0, financeOffset + direction * 30);
  refreshFinance();
}
async function exportTransactions() {
  try {
    const rows = [];
    for (let offset = 0; ; offset += 100) {
      const page = await financeApi(`/transactions?${transactionQuery(offset, 100)}`);
      rows.push(...page.items);
      if (rows.length >= page.total || !page.items.length) break;
    }
    const cell = (value) =>
      `"${String(value ?? "")
        .replace(/^[\s]*[=+@\-]/, "'$&")
        .replaceAll('"', '""')}"`;
    const csv = [
      ["Ngày", "Nội dung", "Loại", "Danh mục", "Số tiền (VNĐ)", "Ghi chú"],
      ...rows.map((r) => [
        r.spent_on,
        r.title,
        r.kind === "expense" ? "Chi" : "Thu",
        financeCategory(r.category_id)?.name,
        r.amount,
        r.note,
      ]),
    ]
      .map((r) => r.map(cell).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `chi-tieu-${financeMonth}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    showToast(error.message, true);
  }
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
async function copyActivePlan() {
  if (!currentPlan) return;
  try {
    const response = await fetch(`/api/plans/${currentPlan.id}/copy`, { method: "POST" });
    if (!response.ok) throw new Error("Chưa sao chép được kế hoạch");
    const plan = await response.json();
    await loadPlansFromDB(plan.id);
    showToast("Đã tạo bản sao chưa hoàn thành");
  } catch (error) {
    showToast(error.message, true);
  }
}
function openPlanReplacement(itemId) {
  const item = currentPlan?.items.find((i) => i.id === itemId);
  if (!item) return;
  openFinanceEditor(
    "Đổi một hạng mục bằng AI",
    `<p>${escapeHtml(item.name)}</p>${formField("Yêu cầu thay thế (tùy chọn)", "replacePreferences", "text", "", 'maxlength="2000" placeholder="Đổi sang món cá, ít dầu…"')}${item.category === "daily_menu" ? '<p class="muted small">Đổi thực đơn không tự thay đổi danh sách nguyên liệu. Hãy kiểm tra lại giỏ đi chợ.</p>' : ""}<p class="muted small">Phương án mới giữ trong ngân sách còn lại. Giá là ước tính.</p>`,
    async (form) => {
      const response = await fetch(`/api/items/${itemId}/replace`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: form.get("replacePreferences") }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Chưa đổi được hạng mục");
      applyUpdatedPlanFromServer(data.plan);
      showToast("Đã đổi hạng mục");
    },
    "Đổi bằng AI",
  );
}

document.addEventListener("DOMContentLoaded", async () => {
  await window.smartspendAuthReady;
  document.getElementById("financeMonth").value = financeMonth;
  let initialView = "spending";
  try {
    initialView = sessionStorage.getItem("smartspend-view") || "spending";
  } catch (_) {
    /* Use the default view. */
  }
  switchWorkspace(initialView);
  await refreshFinance();
  if (hasPendingExpenses() && navigator.onLine) await syncExpenseOutbox();
});
