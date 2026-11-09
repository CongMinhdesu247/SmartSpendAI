// Regression: a protected QR must use the authenticated fetch, not an <img> GET.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const elements = {};
function node(id) {
  return elements[id] ||= {src:'',textContent:'',classList:{add(){},remove(){}},removeAttribute(name){delete this[name];}};
}
const calls = [];
const svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h10v10H0z"/></svg>';
let qrFails = false;
const context = {URL,Headers,Request,Response,Date,encodeURIComponent,console,
  location:{href:'https://app.example/',origin:'https://app.example'},
  document:{addEventListener(){},getElementById:node},addEventListener(){},
  fetch:async (url,options) => {
    calls.push({url,headers:options.headers});
    assert.equal(options.headers.get('X-SmartSpend-User'),'fixture-user');
    if (url === '/api/network-info') return new Response(JSON.stringify({app_url:'https://app.example',public_url:'https://app.example'}));
    assert.equal(url,'/api/network-qr');
    return new Response(qrFails ? '{}' : svg,{status:qrFails ? 503 : 200});
  }
};
context.window=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/auth.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/app.js','utf8'),context);
vm.runInContext("window.smartspendUserId='fixture-user'; showModal=()=>{};",context);
(async()=>{
  await vm.runInContext('openIphoneModal()',context);
  assert.equal(calls.length,2);
  assert.equal(decodeURIComponent(node('iphoneQrImg').src.split(',')[1]),svg);
  qrFails=true;
  await vm.runInContext('openIphoneModal()',context);
  assert.equal(node('iphoneLanUrlCode').textContent,'https://app.example');
  assert.match(node('iphoneConnectionNote').textContent,/sao chép đường link/);
  assert.equal(node('iphoneQrImg').src,undefined);
  console.log('Authenticated QR rendering and copy-link fallback: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
