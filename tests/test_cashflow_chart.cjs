const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const nodes = {};
let config,
  destroyed = 0;
const context = {
  Date,
  Intl,
  console,
  window: { addEventListener() {} },
  document: {
    addEventListener() {},
    getElementById: (id) => (nodes[id] ||= { innerHTML: "", classList: { toggle() {} } }),
  },
  escapeHtml: (s) => String(s),
  formatVND: (n) => n + " ₫",
  renderIcon: () => "",
  Chart: class {
    constructor(canvas, options) {
      config = options;
    }
    destroy() {
      destroyed++;
    }
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync("frontend/finance.js", "utf8"), context);
const rows = [
  { date: "2026-11-01", expense: 70000, income: 0 },
  { date: "2026-11-02", expense: 0, income: 20000 },
  { date: "2026-11-03", expense: 60000, income: 0 },
  { date: "2026-11-04", expense: 0, income: 30000 },
];
context.rows = rows;
let result = vm.runInContext("buildCashflowSeries('2026-11',rows,100000,'2026-11-04')", context);
assert.deepEqual(
  Array.from(
    result.points.filter((p) => Number.isInteger(p.x)),
    (p) => p.y,
  ),
  [0, 70000, 50000, 110000, 80000],
);
assert.equal(result.net, 80000);
assert.equal(result.over, false);
assert.equal(result.peak, 110000);
assert.equal(
  vm.runInContext(
    "buildCashflowSeries('2026-11',rows.slice(0,3),100000,'2026-11-03').over",
    context,
  ),
  true,
);
assert.equal(result.points.filter((p) => p.crossing).length, 2);
for (const p of result.points.filter((p) => p.crossing)) assert.equal(p.y, 100000);
const color = (a, b, budget) =>
  vm.runInContext(
    `cashflowSegmentColor({p0:{parsed:{y:${a}}},p1:{parsed:{y:${b}}}},${budget})`,
    context,
  );
assert.equal(color(100000, 110000, 100000), "#dc2626");
assert.equal(color(80000, 100000, 100000), "#6366f1");
assert.equal(color(80000, 100000, null), "#6366f1");
assert.equal(color(0, 1, 0), "#dc2626");
result = vm.runInContext("buildCashflowSeries('2026-11',rows,200000,'2026-12-01')", context);
assert.equal(result.maximum, 200000);
assert.equal(result.points.at(-1).x, 30);
result = vm.runInContext("buildCashflowSeries('2028-02',[],null,'2028-03-01')", context);
assert.equal(result.days, 29);
assert.equal(result.net, 0);
result = vm.runInContext("buildCashflowSeries('2027-01',[],100000,'2026-11-08')", context);
assert.equal(result.points.length, 1);
result = vm.runInContext(
  "buildCashflowSeries('2026-11',[{date:'2026-11-01',expense:0,income:20000}],100000,'2026-11-01')",
  context,
);
assert.equal(result.net, -20000);
assert(result.minimum < -20000);
vm.runInContext(
  "financeMonth='2026-11';financeState={overview:{daily_cashflow:rows,budget:100000}};renderDailySpending();",
  context,
);
assert.equal(config.type, "line");
assert.equal(config.data.datasets[1].borderDash.join(","), "6,5");
assert.equal(config.data.datasets[1].data[1].x, 30);
assert.equal(config.data.datasets[1].data[0].y, 100000);
assert(config.options.scales.y.max > 110000);
assert.match(nodes.monthBudgetStatus.innerHTML, /Chi ròng 80000/);
vm.runInContext("renderDailySpending()", context);
assert.equal(destroyed, 1);
console.log(
  "Monthly cashflow, exact budget crossings, income, zero budget, negative balances, month lengths and chart config: passed",
);
