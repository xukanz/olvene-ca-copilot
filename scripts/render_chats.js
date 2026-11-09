// Render each test case's conversation history as a WeChat-style chat screenshot.
// Usage: node scripts/render_chats.js [caseId ...]
// Reads test_set/cases.json, writes test_set/screenshots/<id>.png
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const cases = JSON.parse(fs.readFileSync(path.join(ROOT, 'test_set/cases.json'), 'utf8'));
const outDir = path.join(ROOT, 'test_set/screenshots');
fs.mkdirSync(outDir, { recursive: true });

const WEEK = ['日', '一', '二', '三', '四', '五', '六'];
const parse = (s) => {
  const [d, t] = s.split(' ');
  const [y, m, day] = d.split('-').map(Number);
  const [hh, mm] = t.split(':').map(Number);
  return new Date(y, m - 1, day, hh, mm);
};
// WeChat-like relative timestamp, seen from the case's "today"
function label(ts, today) {
  const hm = `${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}`;
  const d0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const d1 = new Date(ts.getFullYear(), ts.getMonth(), ts.getDate());
  const days = Math.round((d0 - d1) / 86400000);
  if (days === 0) return hm;
  if (days === 1) return `昨天 ${hm}`;
  if (days < 7) return `星期${WEEK[ts.getDay()]} ${hm}`;
  if (ts.getFullYear() === today.getFullYear()) return `${ts.getMonth() + 1}月${ts.getDate()}日 ${hm}`;
  return `${ts.getFullYear()}年${ts.getMonth() + 1}月${ts.getDate()}日 ${hm}`;
}
const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function html(c) {
  const today = new Date(c.today + 'T12:00:00');
  let prev = null;
  const rows = c.history.map((m) => {
    const ts = parse(m.time);
    let out = '';
    if (!prev || ts - prev > 5 * 60000) out += `<div class="time">${label(ts, today)}</div>`;
    prev = ts;
    const mine = m.from === 'ca';
    const avatar = mine
      ? `<div class="av ca">${esc(c.ca.name[0])}</div>`
      : `<div class="av cl">${esc(c.client.name[0])}</div>`;
    let body;
    if (m.text === '[图片]' || m.text === '[视频]') {
      body = `<div class="media">${m.text === '[视频]' ? '▶' : '🖼'}<span>${m.text === '[视频]' ? '视频' : '图片'}</span></div>`;
    } else {
      body = `<div class="bubble">${esc(m.text)}</div>`;
    }
    out += `<div class="row ${mine ? 'me' : 'them'}">${avatar}${body}</div>`;
    return out;
  }).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { width: 390px; font-family: "WenQuanYi Zen Hei", "PingFang SC", sans-serif; background: #ededed; }
  .bar { height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px;
         background: #ededed; border-bottom: 1px solid #d9d9d9; font-size: 17px; color: #111; }
  .bar .back { font-size: 26px; width: 30px; }
  .bar .more { width: 30px; text-align: right; letter-spacing: 1px; font-weight: bold; }
  .chat { padding: 6px 12px 16px; min-height: 320px; }
  .time { text-align: center; font-size: 12px; color: #999; margin: 16px 0 10px; }
  .row { display: flex; align-items: flex-start; margin: 10px 0; }
  .row.me { flex-direction: row-reverse; }
  .av { width: 40px; height: 40px; border-radius: 5px; flex: none; color: #fff; font-size: 18px;
        display: flex; align-items: center; justify-content: center; }
  .av.cl { background: #8a9bb4; }
  .av.ca { background: #b08d6e; }
  .bubble { max-width: 254px; padding: 9px 11px; border-radius: 5px; font-size: 15.5px; line-height: 1.5;
            color: #111; position: relative; word-break: break-word; }
  .them .bubble { background: #fff; margin-left: 10px; }
  .me .bubble { background: #95ec69; margin-right: 10px; }
  .them .bubble::before, .me .bubble::before { content: ""; position: absolute; top: 13px; border: 6px solid transparent; }
  .them .bubble::before { left: -11px; border-right-color: #fff; }
  .me .bubble::before { right: -11px; border-left-color: #95ec69; }
  .media { width: 120px; height: 150px; background: #c9c9c9; border-radius: 5px; color: #fff; font-size: 28px;
           display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; }
  .media span { font-size: 13px; }
  .me .media { margin-right: 10px; } .them .media { margin-left: 10px; }
  .input { height: 56px; background: #f7f7f7; border-top: 1px solid #ddd; display: flex; align-items: center;
           padding: 0 10px; gap: 10px; }
  .input .box { flex: 1; height: 38px; background: #fff; border-radius: 5px; }
  .input .ic { width: 28px; height: 28px; border: 1.5px solid #333; border-radius: 50%; }
</style></head><body>
  <div class="bar"><span class="back">‹</span><span>${esc(c.client.name)}</span><span class="more">···</span></div>
  <div class="chat">${rows}</div>
  <div class="input"><div class="ic"></div><div class="box"></div><div class="ic"></div><div class="ic"></div></div>
</body></html>`;
}

(async () => {
  const only = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 200 }, deviceScaleFactor: 2 });
  let n = 0;
  for (const c of cases) {
    if (only.length && !only.includes(c.id)) continue;
    await page.setContent(html(c), { waitUntil: 'load' });
    await page.screenshot({ path: path.join(outDir, `${c.id}.png`), fullPage: true });
    n++;
  }
  await browser.close();
  console.log(`rendered ${n} screenshots to test_set/screenshots/`);
})();
