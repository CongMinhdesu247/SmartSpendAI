const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");
const events = {},
  nodes = {},
  requests = [];
let save, markup;
const ctx = {
  Date,
  Intl,
  URLSearchParams,
  Set,
  Promise,
  AbortController,
  Event,
  setTimeout,
  clearTimeout,
  console,
  crypto: webcrypto,
  navigator: {},
  document: {
    activeElement: null,
    addEventListener(type, handler) {
      (events[type] ||= []).push(handler);
    },
    getElementById(id) {
      return (nodes[id] ||= input(""));
    },
    querySelectorAll() {
      return [];
    },
  },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("frontend/app.js", "utf8"), ctx);
vm.runInContext(fs.readFileSync("frontend/finance.js", "utf8"), ctx);
function input(value, min = "0", max = "9000000000000") {
  return {
    value,
    dataset: { moneyMin: min, moneyMax: max },
    selectionStart: value.length,
    selectionEnd: value.length,
    error: "",
    matches: () => true,
    classList: { add() {}, remove() {}, toggle() {} },
    setCustomValidity(message) {
      this.error = message;
    },
    setSelectionRange(start, end) {
      this.selectionStart = start;
      this.selectionEnd = end;
    },
    setRangeText(text, start, end) {
      this.value = this.value.slice(0, start) + text + this.value.slice(end);
      this.setSelectionRange(start + text.length, start + text.length);
    },
    dispatchEvent() {
      ctx.formatMoneyInput(this);
    },
  };
}
function format(value, caret = value.length) {
  const field = input(value);
  field.setSelectionRange(caret, caret);
  ctx.document.activeElement = field;
  ctx.formatMoneyInput(field);
  return field;
}
for (const [raw, expected] of [
  ["1000", "1.000"],
  ["1000000", "1.000.000"],
  ["1.000.000", "1.000.000"],
  ["9000000000000", "9.000.000.000.000"],
  ["0", "0"],
  ["", ""],
]) {
  const field = format(raw);
  assert.equal(field.value, expected);
  assert.equal(field.error, "");
  if (raw) assert.equal(ctx.parseMoneyInput(expected), Number(raw.replaceAll(".", "")));
}
for (const invalid of ["1.5", "1,5", "-100", "1e6", "abc", "9007199254740993"])
  assert(Number.isNaN(ctx.parseMoneyInput(invalid)), invalid);
assert.equal(
  format("12.934.567", 4).selectionStart,
  4,
  "Editing inside a number preserves the caret",
);
const pasted = input("");
ctx.document.activeElement = pasted;
events.paste[0]({
  target: pasted,
  clipboardData: { getData: () => "1.000.000" },
  preventDefault() {},
});
assert.equal(pasted.value, "1.000.000");
const invalidPaste = input("");
events.paste[0]({
  target: invalidPaste,
  clipboardData: { getData: () => "1.5" },
  preventDefault() {},
});
assert.equal(invalidPaste.value, "1.5");
assert(invalidPaste.error, "Pasting a decimal must not silently turn it into another amount");
const deletion = input("1.000.000");
deletion.setSelectionRange(6, 6);
ctx.document.activeElement = deletion;
events.beforeinput[0]({
  target: deletion,
  inputType: "deleteContentBackward",
  preventDefault() {},
});
assert.equal(deletion.value, "100.000", "Backspace beside a separator removes a digit");
const forwardDeletion = input("1.000.000");
forwardDeletion.setSelectionRange(1, 1);
ctx.document.activeElement = forwardDeletion;
events.beforeinput[0]({
  target: forwardDeletion,
  inputType: "deleteContentForward",
  preventDefault() {},
});
assert.equal(forwardDeletion.value, "100.000", "Delete beside a separator removes a digit");
const limited = input("2.000.000.001", "0", "2000000000");
ctx.formatMoneyInput(limited);
assert(limited.error);
limited.value = "2.000.000.000";
ctx.formatMoneyInput(limited);
assert.equal(limited.error, "");
nodes.budgetInput = input("", "20000", "2000000000");
nodes.budgetPreviewBadge = {};
ctx.setQuickBudget(1000000);
assert.equal(nodes.budgetInput.value, "1.000.000");
assert.equal(nodes.budgetPreviewBadge.textContent, "1.000.000 ₫");
ctx.openFinanceEditor = (_title, html, handler) => {
  markup = html;
  save = handler;
};
ctx.financeApi = async (path, options) => {
  requests.push({ path, payload: JSON.parse(options.body) });
  return {};
};
ctx.refreshFinance = ctx.refreshActivePlan = async () => {};
ctx.loadPlansFromDB = async () => {};
ctx.showToast = () => {};
vm.runInContext(
  "financeState.categories=[{id:1,name:'Khác',archived:false}];financeState.overview={budgets:[{category_id:null,amount:1000000}]};financeState.goals=[{id:1,name:'Tiết kiệm'}];",
  ctx,
);
(async () => {
  const cases = [
    [
      () => ctx.openTransactionEditor(),
      {
        entryAmount: "1.234.567",
        entryTitle: "Mua sắm",
        entryKind: "expense",
        entryCategory: "1",
        entryDate: "2026-11-09",
      },
      "amount",
    ],
    [() => ctx.openBudgetEditor(), { budgetAmount: "1.234.567", budgetCategory: "" }, "amount"],
    [
      () => ctx.openBillEditor(),
      {
        billAmount: "1.234.567",
        billName: "Tiền nhà",
        billCategory: "1",
        billDue: "2026-11-09",
        billFrequency: "monthly",
      },
      "amount",
    ],
    [
      () => ctx.openGoalEditor(),
      { goalTarget: "1.234.567", goalName: "Tiết kiệm", goalDeadline: "" },
      "target",
    ],
    [
      () => ctx.openContributionEditor(1),
      { savedAmount: "1.234.567", savedOn: "2026-11-09" },
      "amount",
    ],
  ];
  for (const [open, values, key] of cases) {
    open();
    assert(markup.includes("data-money"));
    assert(markup.includes('inputmode="numeric"'));
    await save(new Map(Object.entries(values)));
    assert.equal(requests.at(-1).payload[key], 1234567, "Money must reach the API as integer VND");
  }
  ctx.fillBudgetAmount("");
  assert.equal(nodes.budgetAmount.value, "1.000.000");
  const html = fs.readFileSync("frontend/index.html", "utf8");
  assert.match(html, /<option value="Hà Nội" selected>/);
  assert.match(html, /id="budgetInput"[\s\S]*?value="500\.000"/);
  console.log(
    "Money grouping, parsing, paste, caret, limits, five financial forms and Hanoi default: passed",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
