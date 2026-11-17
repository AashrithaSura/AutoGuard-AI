/* Print docs/_report_build.html to docs/AutoGuard_AI_Capstone_Report.pdf via Chrome DevTools.
 *
 * Usage: node scripts/print_report_pdf.mjs
 * Requires Google Chrome at the default Windows path (override with CHROME_PATH).
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const input = process.env.REPORT_HTML || path.join(os.tmpdir(), 'autoguard_report.html');
const output = path.join(root, 'docs', 'AutoGuard_AI_Capstone_Report.pdf');
const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const port = Number(process.env.CDP_PORT || 9335);

if (!fs.existsSync(input)) {
  console.error(`Missing ${input} — run: python scripts/build_report_pdf.py`);
  process.exit(1);
}

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'anpr-pdf-'));
const browser = spawn(chrome, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function endpoint() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) return (await res.json()).webSocketDebuggerUrl;
    } catch { /* not ready */ }
    await sleep(250);
  }
  throw new Error('Chrome DevTools endpoint did not start');
}

const wsUrl = await endpoint();
const ws = new WebSocket(wsUrl);
let seq = 0;
const pending = new Map();
let closed = false;
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  }
};
ws.onclose = () => { closed = true; };
const send = (method, params = {}, sessionId) => new Promise((resolve) => {
  const id = ++seq;
  pending.set(id, resolve);
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
});
await new Promise((resolve) => { ws.onopen = resolve; });

const target = await send('Target.createTarget', { url: 'about:blank' });
const attached = await send('Target.attachToTarget', { targetId: target.result.targetId, flatten: true });
const session = attached.result.sessionId;

await send('Page.enable', {}, session);
await send('Emulation.setEmulatedMedia', { media: 'print' }, session);
const loaded = new Promise((resolve) => {
  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === 'Page.loadEventFired') resolve();
  });
});
await send('Page.navigate', { url: `file:///${input.replaceAll('\\', '/')}` }, session);
await loaded;
await sleep(700);

const footer = `<div style="width:100%;padding:0 0.75in;font-size:7.5px;color:#8b90a3;font-family:'Segoe UI',sans-serif;display:flex;justify-content:space-between;">
  <span>AutoGuard AI · Capstone project report</span>
  <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
</div>`;
const header = `<div style="width:100%;padding:0 0.75in;font-size:7.5px;color:#b3b7c6;font-family:'Segoe UI',sans-serif;">AutoGuard AI — Self-healing ANPR</div>`;

const pdf = await send('Page.printToPDF', {
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: header,
  footerTemplate: footer,
  paperWidth: 8.27,
  paperHeight: 11.69,
  marginTop: 0.55,
  marginBottom: 0.6,
  marginLeft: 0.75,
  marginRight: 0.75,
  preferCSSPageSize: false,
}, session);

if (!pdf.result?.data) {
  console.error('printToPDF failed', JSON.stringify(pdf).slice(0, 400));
  process.exit(1);
}
fs.writeFileSync(output, Buffer.from(pdf.result.data, 'base64'));
console.log(`saved ${output} (${(fs.statSync(output).size / 1024).toFixed(0)} KB)`);

ws.close();
browser.kill();
if (!closed) await sleep(200);
process.exit(0);
