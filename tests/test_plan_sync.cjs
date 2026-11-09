// Exercise actual checklist writes and both Chart.js configurations.
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const nodes = {},
  charts = [],
  requests = [],
  rendered = [],
  toasts = [];
let refreshed = 0,
  fail = false;
const node = () => ({
  textContent: "",
  innerHTML: "",
  style: {},
  classList: { toggle() {}, add() {}, remove() {} },
  setAttribute() {},
});
const plan = (spent, completed = true) => ({
  id: 1,
  title: "Đi chợ",
  plan_type: "meal",
  region: "HCM",
  total_budget: 500000,
  estimated_cost: 80000,
  actual_spent: spent,
  items: [
    {
      id: 2,
      price: 80000,
      name: "Cá",
      category: "grocery",
      is_completed: completed,
      payment: spent ? { id: 3, amount: spent } : null,
    },
  ],
});
const ctx = {
  console,
  Date,
  Intl,
  URLSearchParams,
  Set,
  Promise,
  AbortController,
  setTimeout,
  clearTimeout,
  navigator: {},
  document: {
    addEventListener() {},
    getElementById: (id) => (nodes[id] ||= node()),
    querySelectorAll: () => [],
  },
  Chart: class {
    constructor(canvas, config) {
      charts.push(config);
    }
    destroy() {}
  },
  fetch: async (url, options) => {
    requests.push({ url, payload: JSON.parse(options.body) });
    if (fail) throw new Error("Mất kết nối");
    const completed = JSON.parse(options.body).is_completed;
    return { ok: true, json: async () => ({ plan: plan(completed ? 80000 : 0, completed) }) };
  },
};
ctx.window = ctx;
ctx.refreshFinance = async () => {
  refreshed++;
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("frontend/app.js", "utf8"), ctx);
ctx.fixture = plan(0, false);
ctx.renderPlansHistoryList = () => {};
ctx.renderInteractiveChecklist = (p) => rendered.push(p);
ctx.showToast = (message) => toasts.push(message);
vm.runInContext("currentPlan=fixture; allPlans=[fixture];", ctx);
(async () => {
  const first = ctx.toggleItemCompleted(2, true);
  const duplicate = ctx.toggleItemCompleted(2, true);
  await Promise.all([first, duplicate]);
  assert.equal(requests.length, 1, "Repeated taps while saving must not double-submit");
  assert.equal(nodes.statActualSpent.textContent, "80.000 ₫");
  assert.equal(charts.at(-1).type, "doughnut");
  assert.deepEqual(Array.from(charts.at(-1).data.datasets[0].data), [80000, 0, 420000]);
  assert.equal(refreshed, 1, "Monthly overview must refresh after a checklist expense");
  ctx.switchChartType("bar");
  assert.equal(charts.at(-1).type, "bar");
  assert(
    charts.at(-1).data.datasets.some((d) => d.data.includes(80000)),
    "Bar chart must include actual expense",
  );
  await ctx.toggleItemCompleted(2, false);
  assert.equal(nodes.statActualSpent.textContent, "0 ₫");
  assert.equal(refreshed, 2);
  fail = true;
  await ctx.toggleItemCompleted(2, true);
  assert.equal(
    rendered.at(-1).items[0].is_completed,
    false,
    "Failed writes restore the confirmed checklist state",
  );
  assert.equal(nodes.statActualSpent.textContent, "0 ₫");
  assert(toasts.includes("Mất kết nối"));
  console.log(
    "Checklist completion, duplicate taps, monthly refresh, doughnut/bar totals and failed-write recovery: passed",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
