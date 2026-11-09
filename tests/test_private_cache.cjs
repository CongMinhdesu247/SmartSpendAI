// Runs the actual frontend scripts with an in-memory browser storage fixture.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const storage = {};
Object.defineProperties(storage, {
  getItem: { value: (key) => (Object.hasOwn(storage, key) ? storage[key] : null) },
  setItem: {
    value: (key, value) => {
      storage[key] = String(value);
    },
  },
  removeItem: {
    value: (key) => {
      delete storage[key];
    },
  },
  key: { value: (index) => Object.keys(storage)[index] || null },
  length: { get: () => Object.keys(storage).length },
});
const context = {
  localStorage: storage,
  Date,
  URL,
  Headers,
  Request,
  Promise,
  Map,
  console,
  fetch: async () => {
    throw new Error("Unexpected network request");
  },
  addEventListener() {},
  document: { addEventListener() {} },
  showToast() {},
  location: { href: "https://fixture.example/", origin: "https://fixture.example" },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync("frontend/auth.js", "utf8"), context);
vm.runInContext(fs.readFileSync("frontend/finance.js", "utf8"), context);
const run = (code) => vm.runInContext(code, context);

storage.setItem(
  "smartspend-outbox-v1:legacy",
  JSON.stringify({ client_id: "legacy", title: "Original owner" }),
);
run("window.smartspendUserId='alice'; queueExpense({client_id:'a', title:'Alice'});");
run("window.smartspendUserId='bob'; window.migrateLegacyExpenseOutbox();");
assert.equal(run("readExpenseOutbox().length"), 0);
run("queueExpense({client_id:'b',title:'Bob'});");
assert.equal(run("readExpenseOutbox()[0].title"), "Bob");
run("window.smartspendUserId='alice';");
assert.equal(run("readExpenseOutbox()[0].title"), "Alice");
assert.notEqual(
  run("window.smartspendStorageKey('smartspend-cache:2026-11')"),
  "smartspend-cache:2026-11:user:bob",
);
run("window.smartspendUserId='legacy-owner'; window.migrateLegacyExpenseOutbox();");
assert.equal(run("readExpenseOutbox()[0].title"), "Original owner");
assert.equal(storage.getItem("smartspend-outbox-v1:legacy"), null);
run("window.migrateLegacyExpenseOutbox();");
assert.equal(run("readExpenseOutbox().length"), 1);
run("window.smartspendUserId=null;");
assert.equal(run("readExpenseOutbox().length"), 0);
console.log("Private cache, offline queue and legacy-owner import: passed");
