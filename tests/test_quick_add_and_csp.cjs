// Verify CSP-safe zero inline handlers, Smart Quick-Add NLP, CSV safety & offline auth unlock.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

// 1. Strict CSP verification: zero inline on*= event attributes across all frontend files
for (const file of [
  "frontend/index.html",
  "frontend/auth.js",
  "frontend/app.js",
  "frontend/finance.js",
]) {
  const source = fs.readFileSync(file, "utf8");
  assert.doesNotMatch(
    source,
    /\s+on(?:click|submit|input|change|keydown|keyup|focus|blur)\s*=/i,
    `${file} must not contain inline event handlers so script-src 'self' CSP stays strict`,
  );
  assert.doesNotMatch(
    source,
    /fonts\.googleapis\.com|fonts\.gstatic\.com/i,
    `${file} must not leak requests to external font CDNs`,
  );
}

// 2. Smart Quick-Add Vietnamese natural language parser & CSV injection filter
const ctx = {
  Date,
  Intl,
  URLSearchParams,
  Set,
  Map,
  Promise,
  AbortController,
  setTimeout,
  clearTimeout,
  console,
  navigator: { onLine: true },
  document: {
    addEventListener() {},
    getElementById: () => ({
      value: "",
      textContent: "",
      innerHTML: "",
      classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    }),
    querySelectorAll: () => [],
  },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("frontend/app.js", "utf8"), ctx);
vm.runInContext(fs.readFileSync("frontend/finance.js", "utf8"), ctx);

vm.runInContext(
  `financeState.categories = [
    { id: 1, name: "Ăn uống", color: "orange", archived: false },
    { id: 2, name: "Đi chợ", color: "green", archived: false },
    { id: 3, name: "Nhà ở", color: "indigo", archived: false },
    { id: 4, name: "Di chuyển", color: "sky", archived: false },
    { id: 5, name: "Khác", color: "slate", archived: false }
  ];`,
  ctx,
);

const fixedNow = new ctx.Date(2026, 10, 18, 12, 0, 0); // 2026-11-18
ctx.fixedNow = fixedNow;

let parsed = vm.runInContext("parseQuickEntry('35k phở bò sáng nay', fixedNow)", ctx);
assert.equal(parsed.amount, 35000);
assert.equal(parsed.kind, "expense");
assert.equal(parsed.category_name, "Ăn uống");
assert.equal(parsed.spent_on, "2026-11-18");

parsed = vm.runInContext("parseQuickEntry('1,5tr tiền nhà', fixedNow)", ctx);
assert.equal(parsed.amount, 1500000);
assert.equal(parsed.kind, "expense");
assert.equal(parsed.category_name, "Nhà ở");

parsed = vm.runInContext("parseQuickEntry('+15tr lương tháng 11', fixedNow)", ctx);
assert.equal(parsed.amount, 15000000);
assert.equal(parsed.kind, "income");

parsed = vm.runInContext("parseQuickEntry('45k cà phê hôm qua', fixedNow)", ctx);
assert.equal(parsed.amount, 45000);
assert.equal(parsed.spent_on, "2026-11-17");
assert.equal(parsed.category_name, "Ăn uống");

parsed = vm.runInContext("parseQuickEntry('1tr5 tiền nhà', fixedNow)", ctx);
assert.equal(parsed.amount, 1500000);
assert.equal(parsed.category_name, "Nhà ở");

parsed = vm.runInContext("parseQuickEntry('35k5 phở bò ngày 15/11', fixedNow)", ctx);
assert.equal(parsed.amount, 35500);
assert.equal(parsed.spent_on, "2026-11-15");

parsed = vm.runInContext("parseQuickEntry('50 cành bún chả', fixedNow)", ctx);
assert.equal(parsed.amount, 50000);
assert.equal(parsed.category_name, "Ăn uống");

parsed = vm.runInContext("parseQuickEntry('2 lít đổ xăng', fixedNow)", ctx);
assert.equal(parsed.amount, 200000);
assert.equal(parsed.category_name, "Di chuyển");

parsed = vm.runInContext("parseQuickEntry('1 củ 5 tiền nhà', fixedNow)", ctx);
assert.equal(parsed.amount, 1500000);
assert.equal(parsed.category_name, "Nhà ở");

// Command Palette quick-entry & fuzzy search
const cmdQuick = vm.runInContext("getFilteredPaletteItems('45k cà phê')", ctx);
assert.equal(cmdQuick[0].id, "__quick_entry__");
const cmdTrends = vm.runInContext("getFilteredPaletteItems('6 thang')", ctx);
assert.equal(cmdTrends[0].id, "trends-6m");

// Minimalist month label, axis money formatting & concise advice bullets
assert.equal(vm.runInContext("formatMonthLabel('2026-11')", ctx), "Tháng 11/2026");
assert.equal(vm.runInContext("formatMonthLabel('2026-03')", ctx), "Tháng 3/2026");
assert.equal(vm.runInContext("formatAxisMoney(21600)", ctx), "21,6k");
assert.equal(vm.runInContext("formatAxisMoney(20000)", ctx), "20k");
assert.equal(vm.runInContext("formatAxisMoney(1500000)", ctx), "1,5tr");
assert.equal(vm.runInContext("formatConciseAdviceItems('Một. Hai. Ba. Bốn.').length", ctx), 3);
assert.doesNotMatch(
  fs.readFileSync("frontend/style.css", "utf8"),
  /linear-gradient|radial-gradient/i,
);
assert.doesNotMatch(fs.readFileSync("frontend/index.html", "utf8"), /#sparkles/i);

// CSV Formula Injection vs normal Vietnamese bullet notes
assert.equal(ctx.sanitizeCsvCell("- Mua thêm rau"), '"- Mua thêm rau"');
assert.equal(ctx.sanitizeCsvCell("=CMD|' /C calc'!A0"), `"'=CMD|' /C calc'!A0"`);
assert.equal(ctx.sanitizeCsvCell("-1+2"), `"'-1+2"`);

// 3. Offline PWA auth unlock when previously authenticated (within 30-day TTL) & cache wipe on 401
const storage = {};
Object.defineProperties(storage, {
  getItem: { value: (k) => (Object.hasOwn(storage, k) ? storage[k] : null) },
  setItem: { value: (k, v) => (storage[k] = String(v)) },
  removeItem: { value: (k) => delete storage[k] },
});
storage.setItem("smartspend-auth-seen", String(Date.now() - 3600_000));
storage.setItem("smartspend-active-account", "user-offline-1");
storage.setItem("smartspend-auth-username", "minh");
storage.setItem("smartspend-cache:2026-11:user:user-offline-1", '{"expense":50000}');

let domLoadedHandler = null;
let netDown = true;
const authCtx = {
  localStorage: storage,
  Date,
  URL,
  Headers,
  Request,
  Response,
  Promise,
  console,
  location: { href: "https://app.example/", origin: "https://app.example", reload() {} },
  addEventListener() {},
  document: {
    documentElement: { classList: { add() {}, remove() {}, contains: () => false } },
    addEventListener(type, fn) {
      if (type === "DOMContentLoaded") domLoadedHandler = fn;
    },
    getElementById: () => ({
      textContent: "",
      value: "",
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {},
    }),
  },
  fetch: async () => {
    if (netDown) throw new Error("Network offline");
    return new Response("{}", { status: 401 });
  },
};
authCtx.window = authCtx;
vm.createContext(authCtx);
vm.runInContext(fs.readFileSync("frontend/auth.js", "utf8"), authCtx);

(async () => {
  domLoadedHandler();
  const readyState = await authCtx.smartspendAuthReady;
  assert.equal(readyState.offline, true);
  assert.equal(authCtx.smartspendUserId, "user-offline-1");

  // When server later returns 401 on a private API call, private cache must be wiped
  netDown = false;
  const resp = await authCtx.fetch("/api/finance/overview?month=2026-11");
  assert.equal(resp.status, 401);
  assert.equal(storage.getItem("smartspend-cache:2026-11:user:user-offline-1"), null);

  // Expired offline session (> 30 days) must NOT unlock offline mode and must wipe cache
  netDown = true;
  storage.setItem("smartspend-auth-seen", String(Date.now() - 31 * 86400 * 1000));
  storage.setItem("smartspend-active-account", "user-offline-1");
  storage.setItem("smartspend-cache:2026-11:user:user-offline-1", '{"expense":50000}');
  await authCtx.retryAccess();
  assert.equal(storage.getItem("smartspend-cache:2026-11:user:user-offline-1"), null);
  assert.equal(storage.getItem("smartspend-auth-seen"), null);

  console.log("Strict CSP, Smart Quick-Add NLP, CSV safety and offline PWA unlock: passed");
})().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
