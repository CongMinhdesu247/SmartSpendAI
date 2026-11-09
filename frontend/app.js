// Local Lucide SVG sprite; no icon runtime or icon font required.
function renderIcon(name) {
  return `<svg class="icon" aria-hidden="true"><use href="/icons.svg?v=12#${name}"></use></svg>`;
}

// =====================================================================
//  SMARTSPEND PRO - FRONTEND APPLICATION LOGIC (TAILWIND + CHART.JS)
// =====================================================================

let allPlans = [];
let currentPlan = null;
let historyFilter = "all"; // "all" | "meal" | "hangout"
let financeChart = null;
let currentChartType = "doughnut"; // "doughnut" | "bar"
let canEditServerConfig = false;
let plansHaveMore = false, plansLoading = false, plansEpoch = 0;
const PLAN_PAGE_SIZE = 30;
const pendingPlanItems = new Set();
let planWriteQueue = Promise.resolve();

// Định dạng tiền tệ chuẩn Việt Nam (VD: 500.000 ₫)
function formatVND(amount) {
  const value = Math.round(Number(amount) || 0);
  return value.toLocaleString("vi-VN") + " ₫";
}

// Hiển thị thông báo nổi (Toast)
function showToast(message, isError = false) {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `px-4 py-3 rounded-xl shadow-none border text-xs sm:text-sm font-semibold flex items-center gap-2.5 transition-all duration-300 ${
    isError
      ? "bg-slate-100 border-slate-200/80 text-rose-700"
      : "bg-white border-slate-200/80 text-slate-700"
  }`;
  toast.innerHTML = `
    ${renderIcon(isError ? "triangle-alert" : "check")}
    <span>${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 300);
  }, 3600);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Khởi chạy khi mở trang
document.addEventListener("DOMContentLoaded", async () => {
  await window.smartspendAuthReady;
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  await loadConfigStatus();
  await loadPlansFromDB();
});

// =====================================================================
// 1. QUẢN LÝ CẤU HÌNH API & SUPABASE POSTGRESQL (/api/config)
// =====================================================================
async function loadConfigStatus() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return;
    const data = await res.json();

    canEditServerConfig = data.can_edit_config === true;
    document.querySelectorAll('[data-server-config]').forEach(control => control.classList.toggle('hidden', !canEditServerConfig));
    if (!canEditServerConfig) {
      if (!document.getElementById('settingsModal').classList.contains('hidden')) hideModal('settingsModal');
      return;
    }

    renderDbStatusBadge(data.db_status);

    const apiKeyInput = document.getElementById("configApiKeyInput");
    const dbUrlInput = document.getElementById("configDbUrlInput");
    if (apiKeyInput) { apiKeyInput.value = ""; apiKeyInput.placeholder = data.has_api_key ? "Đã cấu hình (để trống để giữ nguyên)" : "AIzaSy…"; apiKeyInput.disabled = !data.can_edit_config; }
    if (dbUrlInput) { dbUrlInput.value = ""; dbUrlInput.placeholder = data.has_database_url ? "Đã cấu hình (để trống để giữ nguyên)" : "postgresql://…"; dbUrlInput.disabled = !data.can_edit_config; }
    document.getElementById("saveConfigSubmitBtn").classList.toggle("hidden", !data.can_edit_config);
    document.getElementById("configClearOptions").classList.toggle("hidden", !data.can_edit_config);
    document.getElementById("clearApiKeyInput").checked = false;
    document.getElementById("clearDbUrlInput").checked = false;

    const statusBox = document.getElementById("configModalStatusBox");
    if (statusBox) {
      if (data.db_status?.is_cloud_postgres) {
        statusBox.innerHTML = ` <strong class="text-slate-700">Supabase:</strong> <code>${escapeHtml(
          data.db_status.configured_url_masked
        )}</code>. `;
      } else {
        statusBox.innerHTML = ` <strong class="text-slate-700">Lưu trên máy:</strong> <code>smartspend_local.db</code>.`;
      }
    }
  } catch (err) {
    console.error("Lỗi tải cấu hình:", err);
  }
}

function renderDbStatusBadge(dbStatus) {
  const badge = document.getElementById("dbStatusBadge");
  const dot = document.getElementById("dbStatusDot");
  const text = document.getElementById("dbStatusText");
  if (!badge || !text || !dot) return;

  if (dbStatus && dbStatus.is_cloud_postgres) {
    badge.className =
      "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all cursor-pointer bg-slate-100 border-slate-200/80 text-slate-700 hover:bg-slate-100";
    dot.className = "w-2 h-2 rounded-full bg-slate-400";
    text.textContent = "Supabase PostgreSQL";
  } else {
    badge.className =
      "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all cursor-pointer bg-slate-100 border-slate-200/80 text-slate-700 hover:bg-slate-100";
    dot.className = "w-2 h-2 rounded-full bg-slate-500";
    text.textContent = "Local SQLite";
  }
}

let modalTrigger = null;

function showModal(id) {
  const modal = document.getElementById(id);
  if (modal.classList.contains("hidden")) modalTrigger = document.activeElement;
  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  modal.querySelector("button, input")?.focus();
}

function hideModal(id) {
  if (document.getElementById(id).dataset.busy === "true") return;
  document.getElementById(id).classList.add("hidden");
  document.body.style.overflow = "";
  if (modalTrigger?.isConnected && modalTrigger.getClientRects().length) modalTrigger.focus();
  else document.querySelector('[data-view][aria-current="page"]')?.focus();
}

document.addEventListener("keydown", (event) => {
  const modal = document.querySelector('[role="dialog"]:not(.hidden)');
  if (!modal) return;
  if (event.key === "Escape") hideModal(modal.id);
  if (event.key !== "Tab") return;
  const controls = [...modal.querySelectorAll('button, input, select, textarea, summary, a[href]')].filter(
    (control) => !control.disabled && control.getClientRects().length
  );
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

  btn.disabled = true;
  btn.textContent = "Đang kết nối…";

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gemini_api_key: apiKey || null,
        database_url: dbUrl || null,
        clear_api_key: document.getElementById("clearApiKeyInput").checked,
        clear_database_url: document.getElementById("clearDbUrlInput").checked,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Không thể lưu cấu hình");
    }

    renderDbStatusBadge(data.db_status);
    showToast(data.connection?.message || "Đã lưu kết nối");
    await loadConfigStatus();
    await loadPlansFromDB();
    await window.refreshFinance?.();
    closeSettingsModal();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${renderIcon("folder")} Lưu kết nối`;
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
    if (!res.ok) throw new Error('Không lấy được địa chỉ app');
    const data = await res.json();
    const lanUrl = data.app_url || data.lan_url || window.location.origin;

    document.getElementById("iphoneLanUrlCode").textContent = lanUrl;
    document.getElementById("iphoneConnectionMessage").textContent = data.public_url ? "Quét mã QR bằng Camera iPhone. Địa chỉ HTTPS này dùng được qua Wi-Fi hoặc 4G/5G." : "Địa chỉ này chỉ dùng cùng Wi-Fi. Cần cấu hình hosting để mở app khi máy tính tắt.";
    document.getElementById("iphoneConnectionNote").textContent = data.public_url ? "Mở bằng Safari, đăng nhập và chọn Chia sẻ → Thêm vào Màn hình chính." : "Hosting chưa được kết nối. App trên máy tính vẫn cần mở khi dùng địa chỉ LAN.";
    // Image requests cannot attach the account header used by private APIs.
    // Fetch through the authenticated wrapper, then render the SVG locally.
    try {
      const qr = await fetch('/api/network-qr', { cache: 'no-store' });
      if (!qr.ok) throw new Error('Không tải được QR');
      qrImage.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(await qr.text());
      qrImage.classList.remove('hidden');
    } catch (_) {
      document.getElementById('iphoneConnectionNote').textContent = 'Chưa tải được mã QR. Bạn vẫn có thể sao chép đường link và mở bằng Safari trên iPhone.';
    }
  } catch (err) {
    const fallbackUrl = window.location.origin;
    document.getElementById("iphoneLanUrlCode").textContent = fallbackUrl;
    document.getElementById("iphoneQrImg").removeAttribute("src");
    document.getElementById("iphoneConnectionMessage").textContent = "Chưa lấy được địa chỉ app. Hãy kiểm tra kết nối và thử lại.";
  }
}

function closeIphoneModal() {
  hideModal("iphoneModal");
}

function copyIphoneLanUrl() {
  const url = document.getElementById("iphoneLanUrlCode").textContent;
  navigator.clipboard.writeText(url);
  showToast("Đã sao chép địa chỉ");
}

// =====================================================================
// 3. CHUYỂN ĐỔI CHẾ ĐỘ & GỌI AI TẠO KẾ HOẠCH (/api/plans/generate)
// =====================================================================
function switchPlanMode(mode) {
  document.getElementById("planTypeInput").value = mode;
  const mealBtn = document.getElementById("modeMealBtn");
  const hangoutBtn = document.getElementById("modeHangoutBtn");
  const durationInput = document.getElementById("durationInput");
  const styleSelect = document.getElementById("styleModeInput");
  const titleInput = document.getElementById("planTitleInput");
  const prefInput = document.getElementById("preferencesInput");

  const activeClass =
    "py-2.5 px-3 rounded-lg text-xs sm:text-sm font-semibold transition-all bg-indigo-50 text-indigo-700";
  const inactiveClass =
    "py-2.5 px-3 rounded-lg text-xs sm:text-sm font-semibold transition-all text-slate-500 hover:text-indigo-700";

  mealBtn.setAttribute("aria-pressed", String(mode === "meal"));
  hangoutBtn.setAttribute("aria-pressed", String(mode === "hangout"));

  if (mode === "meal") {
    mealBtn.className = activeClass;
    hangoutBtn.className = inactiveClass;
    durationInput.value = "7 ngày";
    titleInput.placeholder = "Thực đơn tuần này";
    prefInput.placeholder =
      "Khẩu vị, món cần tránh…";
    styleSelect.innerHTML = `
      <option value="Nấu ăn tại nhà & mang cơm đi làm">Nấu tại nhà & mang cơm</option>
      <option value="Cơm gia đình tiết kiệm, đủ chất">Cơm gia đình tiết kiệm</option>
      <option value="Thực đơn Eat Clean / Giảm cân">Eat Clean / Giữ dáng</option>
      <option value="Sinh viên / Người ở trọ bận rộn">Sinh viên / Nấu nhanh</option>
    `;
  } else {
    hangoutBtn.className = activeClass;
    mealBtn.className = inactiveClass;
    durationInput.value = "1 buổi tối cuối tuần";
    titleInput.placeholder = "Hẹn hò cuối tuần";
    prefInput.placeholder =
      "Địa điểm, hoạt động yêu thích…";
    styleSelect.innerHTML = `
      <option value="Hẹn hò cặp đôi lãng mạn">Hẹn hò cặp đôi</option>
      <option value="Đi chơi tụ tập nhóm bạn">Tụ tập nhóm bạn</option>
      <option value="Dã ngoại / Giải trí cuối tuần">Dã ngoại cuối tuần</option>
      <option value="Foodtour ẩm thực đường phố">Foodtour ẩm thực</option>
    `;
  }
}

function updateBudgetPreview(val) {
  document.getElementById("budgetPreviewBadge").textContent = formatVND(val);
}

function setQuickBudget(amount) {
  const input = document.getElementById("budgetInput");
  input.value = amount;
  updateBudgetPreview(amount);
}

async function handleGeneratePlan(event) {
  event.preventDefault();

  const planType = document.getElementById("planTypeInput").value;
  const customTitle = document.getElementById("planTitleInput").value.trim();
  const totalBudget = Number(document.getElementById("budgetInput").value) || 500000;
  const region = document.getElementById("regionInput").value;
  const styleMode = document.getElementById("styleModeInput").value;
  const duration = document.getElementById("durationInput").value.trim();
  const people = document.getElementById("peopleInput").value.trim();
  const notes = document.getElementById("preferencesInput").value.trim();

  const daysOrPeopleCombined = `${duration} cho ${people}`;
  const fullPreferences = [
    `Hình thức: ${styleMode}`,
    notes ? `Ghi chú riêng: ${notes}` : "",
  ]
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

    const data = await res.json();
    if (!res.ok) {
      if (res.status === 400 && typeof data.detail === "string" && data.detail.toLowerCase().includes("api key")) {
        openSettingsModal();
      }
      throw new Error(typeof data.detail === "string" ? data.detail : "Dữ liệu chưa hợp lệ. Hãy kiểm tra độ dài và nội dung biểu mẫu.");
    }

    document.getElementById("planTitleInput").value = "";
    showToast(" Đã tạo kế hoạch thông minh và lưu vào Database!");
    await loadPlansFromDB(data.id);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    overlay.classList.add("hidden");
    submitBtn.disabled = false;
  }
}

// =====================================================================
// 4. LỊCH SỬ KẾ HOẠCH TỪ DATABASE (/api/plans)
// =====================================================================
async function loadPlansFromDB(targetPlanId = null, append = false) {
  if (append && (plansLoading || !plansHaveMore)) return;
  const epoch = ++plansEpoch;
  plansLoading = true;
  const moreButton = document.getElementById('morePlansButton');
  if (moreButton) moreButton.disabled = true;
  try {
    const params = new URLSearchParams({ limit: PLAN_PAGE_SIZE });
    if (historyFilter !== 'all') params.set('plan_type', historyFilter);
    if (append && allPlans.length) params.set('before_id', allPlans.at(-1).id);
    const res = await fetch(`/api/plans?${params}`);
    if (!res.ok) throw new Error("Không tải được kế hoạch");
    const page = await res.json();
    if (epoch !== plansEpoch) return;
    plansHaveMore = page.length === PLAN_PAGE_SIZE;
    allPlans = append ? [...allPlans, ...page.filter(p => !allPlans.some(old => old.id === p.id))] : page;

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
    console.error("Không thể tải lịch sử kế hoạch:", err);
    document.getElementById("plansHistoryList").innerHTML =
      `<p class="text-xs text-slate-500 py-4">Không tải được kế hoạch. Bấm Làm mới để thử lại.</p>`;
  } finally {
    if (epoch === plansEpoch) {
      plansLoading = false;
      if (moreButton) { moreButton.disabled = false; moreButton.classList.toggle('hidden', !plansHaveMore); }
    }
  }
}

function setHistoryFilter(filterType) {
  historyFilter = filterType;
  for (const [suffix, value] of [["All", "all"], ["Meal", "meal"], ["Hangout", "hangout"]]) {
    document.getElementById(`historyFilter${suffix}`).setAttribute("aria-pressed", String(filterType === value));
  }

  const activeCls =
    "px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100";
  const normalCls =
    "px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-50 text-slate-500 hover:text-indigo-700";

  document.getElementById("historyFilterAll").className =
    filterType === "all" ? activeCls : normalCls;
  document.getElementById("historyFilterMeal").className =
    filterType === "meal" ? activeCls : normalCls;
  document.getElementById("historyFilterHangout").className =
    filterType === "hangout" ? activeCls : normalCls;

  loadPlansFromDB();
}

function renderPlansHistoryList() {
  const container = document.getElementById("plansHistoryList");
  const filtered =
    historyFilter === "all"
      ? allPlans
      : allPlans.filter((p) => p.plan_type === historyFilter);

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="text-center py-8 text-slate-500 text-xs border border-dashed border-slate-200 rounded-xl">
        Chưa có kế hoạch nào trong danh mục này.
      </div>
    `;
    return;
  }

  container.innerHTML = filtered
    .map((plan) => {
      const isSelected = currentPlan && currentPlan.id === plan.id;
      const icon = renderIcon(plan.plan_type === "meal" ? "utensils" : "coffee");
      const dateStr = plan.created_at
        ? new Date(plan.created_at).toLocaleDateString("vi-VN")
        : "";

      return `
        <div
          role="button" tabindex="0" aria-pressed="${Boolean(isSelected)}"
          onkeydown="if(event.target === this && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); selectPlanById(${plan.id}); }"
          onclick="selectPlanById(${plan.id})"
          class="group p-3.5 rounded-xl border transition-all cursor-pointer flex items-start justify-between gap-2 ${
            isSelected
              ? "bg-slate-100 border-slate-200/80 shadow-none"
              : "bg-white border-slate-200 hover:border-indigo-200 hover:bg-slate-50"
          }"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <span class="text-sm">${icon}</span>
              <h4 class="text-xs sm:text-sm font-semibold text-slate-900 truncate">
                ${escapeHtml(plan.title)}
              </h4>
            </div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[11px] text-slate-500">
              <span>Ngân sách: <strong class="text-slate-700">${formatVND(plan.total_budget)}</strong></span>
              <span>Đã chi: <strong class="text-slate-700">${formatVND(plan.actual_spent)}</strong></span>
              <span> ${escapeHtml(plan.region)} ${dateStr ? `• ${dateStr}` : ""}</span>
            </div>
          </div>

          <button
            type="button"
            onclick="event.stopPropagation(); deletePlanById(${plan.id})"
            class="opacity-70 group-hover:opacity-100 text-slate-500 hover:text-rose-600 p-1.5 rounded-lg hover:bg-slate-100 transition"
            aria-label="Xóa kế hoạch: ${escapeHtml(plan.title)}" title="Xóa kế hoạch này"
          >
            ${renderIcon("trash-2")} 
          </button>
        </div>
      `;
    })
    .join("");
}

function selectPlanById(planId) {
  const found = allPlans.find((p) => p.id === planId);
  if (found) {
    selectActivePlan(found);
  }
}

// =====================================================================
// 5. HIỂN THỊ DASHBOARD CHI TIẾT, BIỂU ĐỒ CHART.JS & CHECKLIST
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

function renderStatCardsAndProgress(plan) {
  const remaining = plan.total_budget - plan.actual_spent;
  const legacyNotice = document.getElementById("legacyPlanNotice");
  legacyNotice.classList.toggle("hidden", !plan.unrecorded_legacy_spent);
  legacyNotice.textContent = plan.unrecorded_legacy_spent
    ? `Số liệu trước nâng cấp: ${formatVND(plan.unrecorded_legacy_spent)} theo checkbox. Sổ thu/chi mới chỉ tính giao dịch đã ghi.`
    : "";

  // 4 Stat Cards
  document.getElementById("statTotalBudget").textContent = formatVND(plan.total_budget);

  document.getElementById("statEstimatedCost").textContent = formatVND(plan.estimated_cost);
  document.getElementById("statActualSpent").textContent = formatVND(plan.actual_spent);

  const remEl = document.getElementById("statRemaining");
  remEl.textContent = formatVND(remaining);
  remEl.className = `text-lg sm:text-xl font-semibold ${
    remaining >= 0 ? "text-slate-700" : "text-rose-600"
  }`;

  // Header & Badges
  const typeBadge = document.getElementById("activePlanTypeBadge");
  if (plan.plan_type === "meal") {
    typeBadge.className =
      "px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100";
    typeBadge.textContent = "Thực đơn";
  } else {
    typeBadge.className =
      "px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100";
    typeBadge.textContent = "Đi chơi";
  }

  document.getElementById("activePlanRegionBadge").textContent = ` ${plan.region}`;
  document.getElementById("activePlanDateBadge").textContent = plan.created_at
    ? ` ${new Date(plan.created_at).toLocaleString("vi-VN")}`
    : "Vừa tạo";
  document.getElementById("activePlanTitle").textContent = plan.title;
  document.getElementById("activePlanAdvice").textContent =
    plan.advice || "Hãy ưu tiên mua sắm theo đúng định lượng để tối ưu ngân sách.";

  // Progress Bar
  const baseBudget = Math.max(1, plan.total_budget);
  const estPct = Math.min(100, Math.round((plan.estimated_cost / baseBudget) * 100));
  const actPct = Math.round((plan.actual_spent / baseBudget) * 100);

  document.getElementById("barActualLabel").textContent = formatVND(plan.actual_spent);
  document.getElementById("barEstimatedLabel").textContent = formatVND(plan.estimated_cost);
  document.getElementById("barPercentLabel").textContent = `${actPct}% ngân sách`;
  document.getElementById("barEstimatedFill").style.width = `${estPct}%`;
  document.getElementById("barActualFill").style.width = `${Math.min(100, actPct)}%`;
}

// =====================================================================
// 6. BIỂU ĐỒ TÀI CHÍNH TRỰC QUAN (CHART.JS)
// =====================================================================
function switchChartType(type) {
  currentChartType = type;
  document.getElementById("chartTypeDoughnutBtn").setAttribute("aria-pressed", String(type === "doughnut"));
  document.getElementById("chartTypeBarBtn").setAttribute("aria-pressed", String(type === "bar"));
  const doughnutBtn = document.getElementById("chartTypeDoughnutBtn");
  const barBtn = document.getElementById("chartTypeBarBtn");

  const activeCls =
    "px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100";
  const inactiveCls =
    "px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-slate-50 text-slate-500 hover:text-indigo-700";

  doughnutBtn.className = type === "doughnut" ? activeCls : inactiveCls;
  barBtn.className = type === "bar" ? activeCls : inactiveCls;

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

  const actualSpent = Math.max(0, plan.actual_spent || 0);
  const unspentPlanned = Math.max(
    0,
    (plan.items || [])
      .filter((i) => !i.payment)
      .reduce((acc, item) => acc + (Number(item.price) || 0), 0)
  );
  const remainingFree = Math.max(0, plan.total_budget - (actualSpent + unspentPlanned));

  if (currentChartType === "doughnut") {
    financeChart = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: [
          "Đã chi",
          "Chưa chi",
          "Còn lại",
        ],
        datasets: [
          {
            data: [actualSpent, unspentPlanned, remainingFree],
            backgroundColor: ["#6366f1", "#7dd3fc", "#e2e8f0"],
            borderColor: "#ffffff",
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
              color: "#475569",
              font: { size: 11, family: "Inter" },
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
        labels: ["Ngân sách gốc", "Chi phí AI dự kiến", "Đã chi thực tế", "Số dư còn lại"],
        datasets: [
          {
            label: "Số tiền (VNĐ)",
            data: [
              plan.total_budget,
              plan.estimated_cost,
              actualSpent,
              Math.max(0, plan.total_budget - actualSpent),
            ],
            backgroundColor: ["#a5b4fc", "#7dd3fc", "#6366f1", "#5eead4"],
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
            ticks: { color: "#64748b", font: { size: 11 } },
            grid: { display: false },
          },
          y: {
            ticks: {
              color: "#64748b",
              font: { size: 11 },
              callback: (val) => (val / 1000).toLocaleString("vi-VN") + "k",
            },
            grid: { color: "rgba(148, 163, 184, 0.16)" },
          },
        },
      },
    });
  }
}

// =====================================================================
// 7. RENDER DANH SÁCH CHECKLIST TƯƠNG TÁC & ĐỒNG BỘ DATABASE
// =====================================================================
function renderInteractiveChecklist(plan) {
  const items = plan.items || [];
  const mealSections = document.getElementById("mealPlanSections");
  const hangoutSection = document.getElementById("hangoutPlanSection");

  if (plan.plan_type === "meal") {
    mealSections.classList.remove("hidden");
    hangoutSection.classList.add("hidden");

    const groceryItems = items.filter((i) => i.category === "grocery");
    const dailyMenuItems = items.filter((i) => i.category === "daily_menu");

    document.getElementById("groceryCountBadge").textContent = `${
      groceryItems.filter((i) => i.is_completed).length
    }/${groceryItems.length} đã mua`;
    document.getElementById("dailyMenuCountBadge").textContent = `${dailyMenuItems.length} ngày`;

    document.getElementById("groceryChecklistContainer").innerHTML =
      groceryItems.length > 0
        ? groceryItems.map((item) => renderSingleItemCard(item, "grocery")).join("")
        : `<div class="text-xs text-slate-500 py-4 text-center">Chưa có mục đi chợ nào.</div>`;

    document.getElementById("dailyMenuChecklistContainer").innerHTML =
      dailyMenuItems.length > 0
        ? dailyMenuItems.map((item) => renderSingleItemCard(item, "daily_menu")).join("")
        : `<div class="text-xs text-slate-500 py-4 text-center">Chưa có thực đơn ngày nào.</div>`;
  } else {
    mealSections.classList.add("hidden");
    hangoutSection.classList.remove("hidden");

    document.getElementById("activityCountBadge").textContent = `${
      items.filter((i) => i.is_completed).length
    }/${items.length} hoàn thành`;

    document.getElementById("activityChecklistContainer").innerHTML =
      items.length > 0
        ? items.map((item) => renderSingleItemCard(item, "activity")).join("")
        : `<div class="text-xs text-slate-500 py-4 text-center">Chưa có hoạt động nào.</div>`;
  }
}

function renderSingleItemCard(item, sectionType) {
  const isDone = Boolean(item.is_completed);
  const tagColor = "bg-slate-100 text-slate-700 border-slate-200/80";

  return `
    <div
      id="item-card-${item.id}"
      class="p-3.5 rounded-xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
        isDone
          ? "bg-slate-100 border-slate-200/80"
          : "bg-white border-slate-200 hover:border-indigo-200"
      }"
    >
      <!-- Bên trái: Checkbox + Thông tin -->
      <div class="flex items-start gap-3 flex-1 min-w-0">
        <input
          type="checkbox"
          aria-label="Hoàn thành: ${escapeHtml(item.name)}"
          ${isDone ? "checked" : ""} ${pendingPlanItems.has(item.id) ? 'disabled' : ''}
          onchange="toggleItemCompleted(${item.id}, this.checked)"
          class="mt-1 w-5 h-5 rounded accent-indigo-500 cursor-pointer flex-shrink-0"
          title="Tích để ghi chi theo giá của mục; bỏ tích để hủy khoản chi tự động"
        />
        <div class="flex-1 min-w-0">
          <div class="flex flex-wrap items-center gap-2 mb-1">
            <span class="text-[11px] font-semibold px-2 py-0.5 rounded-full border ${tagColor}">
              ${escapeHtml(item.time_or_day || item.category)}
            </span>
            <h4 class="text-sm font-semibold ${
              isDone ? "line-through text-slate-500" : "text-slate-900"
            }">
              ${escapeHtml(item.name)}
            </h4>
          </div>
          <p class="text-xs text-slate-500 leading-relaxed whitespace-pre-line">
            ${escapeHtml(item.details)}
          </p>
        </div>
      </div>

      <!-- Bên phải: Ô sửa giá tiền trực tiếp -->
      <div class="plan-item-actions flex items-center justify-between sm:justify-end gap-2 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-200/80 flex-shrink-0">
        <span class="text-[11px] text-slate-500 sm:hidden">Ước tính:</span>
        <div class="flex items-center gap-1.5 bg-slate-50 border border-slate-200 focus-within:border-indigo-500 rounded-xl px-2.5 py-1.5">
          <input
            type="number"
            aria-label="Chi phí dự kiến: ${escapeHtml(item.name)}"
            value="${item.price}"
            min="0"
            max="2000000000"
            step="1000"
            ${pendingPlanItems.has(item.id) ? 'disabled' : ''}
            onchange="updateItemPrice(${item.id}, this.value)"
            class="w-24 bg-transparent text-right text-xs sm:text-sm font-semibold ${
              item.price > 0 ? "text-slate-700" : "text-slate-500"
            } outline-none"
            title="Sửa giá của mục và khoản chi do ô hoàn thành tự tạo. Khoản nhập thủ công được sửa riêng."
          />
          <span class="text-[11px] font-semibold text-slate-500">₫</span>
        </div>
        <button type="button" class="ui-button ${item.payment ? 'quiet' : 'soft'} small" onclick="recordPlanPayment(${item.id})" title="${item.payment ? `Đã ghi ${formatVND(item.payment.amount)}` : 'Ghi khoản thanh toán thực tế'}">${renderIcon(item.payment ? 'check' : 'receipt')} ${item.payment ? 'Đã ghi chi' : 'Ghi chi'}</button>
        ${!item.payment ? `<details class="item-menu"><summary aria-label="Tùy chọn hạng mục ${escapeHtml(item.name)}">${renderIcon('ellipsis')}</summary><div><button type="button" onclick="openPlanReplacement(${item.id}); this.closest('details').open=false">${renderIcon('sparkles')} Đổi bằng AI</button></div></details>` : ''}
      </div>
    </div>
  `;
}

// =====================================================================
// 8. API PATCH ITEM & DELETE PLAN (ĐỒNG BỘ TỨC THÌ VỚI POSTGRESQL)
// =====================================================================
async function toggleItemCompleted(itemId, isCompleted) {
  return savePlanItem(itemId, { is_completed: isCompleted });
}

async function updateItemPrice(itemId, rawValue) {
  const newPrice = Number(rawValue);
  if (!Number.isInteger(newPrice) || newPrice < 0 || newPrice > 2000000000) {
    renderInteractiveChecklist(currentPlan);
    showToast('Giá phải là số nguyên từ 0 đến 2 tỷ đồng.', true);
    return;
  }
  return savePlanItem(itemId, { price: newPrice });
}

function savePlanItem(itemId, payload) {
  if (pendingPlanItems.has(itemId)) return planWriteQueue;
  pendingPlanItems.add(itemId);
  document.querySelectorAll(`#item-card-${itemId} input, #item-card-${itemId} button`).forEach(c => c.disabled = true);
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
        throw new Error(typeof data.detail === 'string' ? data.detail : "Không thể lưu hạng mục");
      }

      if (data.plan) {
        applyUpdatedPlanFromServer(data.plan);
        await window.refreshFinance?.();
      }
    } catch (err) {
      showToast(err.name === 'AbortError' ? 'Chưa xác nhận được thay đổi. Hãy kết nối và làm mới kế hoạch.' : err.message, true);
      if (currentPlan) renderInteractiveChecklist(currentPlan);
    } finally {
      clearTimeout(timer);
      pendingPlanItems.delete(itemId);
      document.querySelectorAll(`#item-card-${itemId} input, #item-card-${itemId} button`).forEach(c => c.disabled = false);
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
  if (currentPlan && currentPlan.id !== updatedPlan.id) { renderPlansHistoryList(); return; }
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
    showToast("Đã đồng bộ kế hoạch");
  } catch (err) {
    showToast("Không thể làm mới kế hoạch", true);
  }
}

async function deletePlanById(planId) {
  if (!planId) return;
  const target = allPlans.find((p) => p.id === planId);
  const title = target ? target.title : `#${planId}`;

  if (!confirm(`Bạn có chắc chắn muốn xóa kế hoạch "${title}" khỏi Database không?`)) {
    return;
  }

  try {
    const res = await fetch(`/api/plans/${planId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      throw new Error("Không thể xóa kế hoạch");
    }

    const deleted = await res.json();
    actionToast("Đã xóa kế hoạch", "Hoàn tác", async () => {
      const response = await fetch(`/api/plans/trash/${deleted.undo_id}/restore`, { method: "POST" });
      if (!response.ok) throw new Error("Chưa khôi phục được kế hoạch");
      const restored = await response.json();
      await loadPlansFromDB(restored.id);
      await refreshFinance();
    });
    if (currentPlan && currentPlan.id === planId) {
      currentPlan = null;
    }
    await loadPlansFromDB();
  } catch (err) {
    showToast(err.message, true);
  }
}
