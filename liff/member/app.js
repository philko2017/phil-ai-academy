// ===== 設定：LIFF ID 與 API 網址。正式網址（GitHub Pages）一律用真資料；本機預覽才載入 mock.js 的模擬資料 =====
// 會員頁面送到 Make 情境「AI學院｜會員 API」，用欄位 a 分辨動作：me 我的身分（順便校正選單）｜apply 申請入會｜profile 改基本資料
// 頁面上的文字、方案、收款帳戶都不放在這裡：Make 從 Notion「前台設定」「方案」讀出來，隨 me 一起回傳
const CONFIG = {
  liffId: "2012161136-mSmbv0VR",
  apiUrl: "https://hook.us2.make.com/vbwwyt6hjrveqmylu42gkovs2ulf9jdm",
};
const IN_LIFF_HOST = location.hostname.endsWith("github.io");

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = n => "NT$ " + Number(n || 0).toLocaleString("zh-TW");

// 申請表單欄位：代號、標題、必填、輸入型別（和 tools/make_blueprints.py 的 APPLY_FIELDS 對應）
const FIELDS = [
  ["name", "姓名", true, "text"], ["phone", "手機", true, "tel"], ["email", "Email", false, "email"],
  ["note", "想學什麼、怎麼認識學院的（選填）", false, "area"],
];
// 匯款回報欄位
const PAY_FIELDS = [["pay5", "匯款帳號末五碼", true, "text"], ["paydate", "匯款日期", true, "date"]];
// 頁面狀態 → 標籤：非會員、審核中、一般會員、高級會員、已到期、停權
const BADGE = { guest: ["guest", "非會員"], pending: ["pending", "審核中"], member: ["member", "一般會員"],
                premium: ["premium", "高級會員"], expired: ["expired", "已到期"], banned: ["banned", "暫停使用"] };
const IS_MEMBER = st => st === "member" || st === "premium";
// 到期前幾天開始在會員畫面提醒（提醒文字在 Notion「前台設定」的「到期提醒」）
const REMIND_DAYS = 7;
const daysLeft = d => Math.round((new Date(d + "T00:00:00") - new Date(new Date().toDateString())) / 86400000);

// ===== Notion 欄位：Make 把 Notion API 的原始資料轉成 JSON 交給頁面，這裡取出純文字、數字、勾選 =====
function nval(p) {
  if (!p) return "";
  const rich = a => (a || []).map(t => t.plain_text).join("");
  switch (p.type) {
    case "title": return rich(p.title);
    case "rich_text": return rich(p.rich_text);
    case "number": return p.number;
    case "checkbox": return p.checkbox;
    case "select": return p.select ? p.select.name : "";
    default: return "";
  }
}
const nobj = props => Object.fromEntries(Object.entries(props || {}).map(([k, v]) => [k, nval(v)]));
// 「{姓名}」「{身分}」「{到期日}」換成這位會員的資料
const fill = (tpl, me) => esc(tpl || "").replace(/\{姓名\}/g, esc(me.name || me.line || ""))
  .replace(/\{身分\}/g, esc((BADGE[me.state] || [])[1] || "")).replace(/\{到期日\}/g, esc(me.expiry || ""));

// ===== 正式後端：用表單格式送出，瀏覽器不會先送 CORS 預檢 =====
class ApiError extends Error { constructor(code) { super(code); this.code = code; } }
// 後端把自由文字 URL 編碼後才放進 JSON（Make 沒有 JSON 跳脫函式），這裡解碼
const ENC_KEYS = new Set(["name", "phone", "email", "note", "line", "message"]);
const safeDecode = s => { try { return decodeURIComponent(s); } catch (e) { return s; } };
async function post(fields) {
  const token = liff.getAccessToken();
  if (!token) throw new ApiError("no_token");
  const res = await fetch(CONFIG.apiUrl, { method: "POST", body: new URLSearchParams({ ...fields, t: token }) });
  let data;
  try { data = await res.json(); } catch (e) { throw new ApiError("server"); }
  if (!data.ok) throw new ApiError(data.error || "server");
  for (const k of Object.keys(data)) if (ENC_KEYS.has(k) && typeof data[k] === "string") data[k] = safeDecode(data[k]);
  return data;
}
let api = { me: () => post({ a: "me" }), apply: f => post({ a: "apply", ...f }), profile: f => post({ a: "profile", ...f }) };

// ===== 狀態與畫面 =====
const params = new URLSearchParams(location.search);
// 選單上的功能還在規劃，先顯示「即將推出」；說明文字在 Notion「前台設定」
const SOON = { courses: ["📚", "課程", "課程預告"], ai: ["✨", "AI 小幫手", "AI 小幫手預告"] };
const V = params.get("v");
const S = { view: V === "about" || SOON[V] ? V : "home", me: null, site: {}, plans: [], form: {}, busy: false, editing: false, profileEdit: false };
const planOf = name => S.plans.find(p => p.name === name);

function render() {
  const b = S.me && BADGE[S.me.state];
  $("#badge").className = b ? "badge " + b[0] : "";
  $("#badge").textContent = b ? b[1] : "";
  $("#bar").hidden = true;
  if (!S.me) { $("#app").innerHTML = `<p class="blocked">讀取中…</p>`; return; }
  if (S.view === "about") return renderAbout();
  if (SOON[S.view]) return renderSoon(SOON[S.view]);
  const st = S.me.state;
  if (S.profileEdit) return renderProfileEdit();
  if (IS_MEMBER(st)) return renderMember();
  if (st === "banned") return renderBanned();
  if (st === "pending" && !S.editing) return renderPending();
  renderApply();
}
function renderAbout() {
  const s = S.site;
  $("#app").innerHTML = `<h1>${esc(s["學院名稱"] || "關於學院")}</h1>
    <div class="card"><p>${esc(s["學院介紹"])}</p>${s["聯絡方式"] ? `<p class="lead" style="margin-top:10px">${esc(s["聯絡方式"])}</p>` : ""}</div>
    <div class="links"><a class="link" href="?v=home"><span class="ic">📝</span><span><b>會員專區</b><small>申請入會、查看會員資料</small></span></a></div>`;
}
function renderSoon([icon, title, key]) {
  $("#app").innerHTML = `<div class="status"><div class="big">${icon}</div><h2>${title}</h2><p class="lead">${esc(S.site[key])}</p>
    <p class="lead" style="margin-top:14px;font-weight:700;color:var(--brand)">即將推出</p></div>
    <div class="links"><a class="link" href="?v=home"><span class="ic">🪪</span><span><b>會員專區</b><small>入會申請、我的會員資料</small></span></a></div>`;
}
const input = (k, label, req, type, f) => `<label class="f">${label}${req ? " <b>*</b>" : ""}${type === "area"
  ? `<textarea data-k="${k}">${esc(f[k])}</textarea>`
  : `<input data-k="${k}" type="${type}" value="${esc(f[k])}" ${k === "name" ? 'autocomplete="name"' : ""}${k === "pay5" ? ' inputmode="numeric" maxlength="5"' : ""}>`}</label>`;
function renderApply() {
  const editing = S.me.state === "pending", renew = S.me.state === "expired";
  const f = S.form, s = S.site;
  if (!planOf(f.plan) && S.plans[0]) f.plan = S.plans[0].name;
  const plan = planOf(f.plan);
  const lead = editing ? "修改後重新送出，管理者會看到最新的資料。" : fill(renew ? s["已到期說明"] : s["申請說明"], S.me);
  $("#app").innerHTML = `<h1>${editing ? "修改申請" : renew ? "續費" : "申請入會"}</h1>
    <p class="lead">${lead}</p>
    <div class="card"><h2>① 選擇方案</h2><div class="plans">${S.plans.map(p => `<label class="plan ${p.name === f.plan ? "on" : ""}">
      <input type="radio" name="plan" value="${esc(p.name)}" ${p.name === f.plan ? "checked" : ""}>
      <span><b>${esc(p.label || p.name)}　${money(p.price)}</b><small>${esc(p.desc)}</small></span></label>`).join("")}</div></div>
    <div class="card"><h2>② 匯款${s["範例帳戶"] ? `<span class="demo">範例</span>` : ""}</h2>
      <p class="lead">請匯 <b style="color:var(--text)">${money(plan && plan.price)}</b> 到下面的帳戶，再填末五碼與日期。</p>
      <div class="bank"><dl><dt>銀行</dt><dd>${esc(s["收款銀行"])}</dd><dt>帳號</dt><dd>${esc(s["收款帳號"])}</dd><dt>戶名</dt><dd>${esc(s["戶名"])}</dd></dl></div>
      ${s["匯款提醒"] ? `<p class="lead" style="margin-top:8px;font-size:14px">${esc(s["匯款提醒"])}</p>` : ""}
      ${PAY_FIELDS.map(([k, label, req, type]) => input(k, label, req, type, f)).join("")}</div>
    <div class="card"><h2>③ 基本資料</h2>${FIELDS.map(([k, label, req, type]) => input(k, label, req, type, f)).join("")}</div>
    ${editing ? `<button class="ghost" id="cancelEdit">← 不修改了</button>` : ""}`;
  $("#bar").hidden = false;
  $("#barIn").innerHTML = `<button class="primary" id="send" ${S.busy ? "disabled" : ""}>${S.busy ? "送出中…" : editing ? "送出修改" : renew ? "送出續費" : "送出申請"}</button>`;
}
function renderPending() {
  $("#app").innerHTML = `<div class="status"><div class="big">⏳</div><h2>入會申請審核中</h2>
    <p class="lead">${fill(S.site["審核中說明"], S.me)}</p></div>
    <div class="card"><h2>方案與匯款</h2>${payInfo()}</div>
    <div class="card"><h2>申請資料</h2>${profile()}</div>
    <button class="ghost" id="edit">修改申請資料</button>`;
}
function renderMember() {
  const s = S.site;
  $("#app").innerHTML = `<h1>${fill(s["歡迎語"] || "{姓名}，你好", S.me)}</h1>
    <p class="lead">${fill(s["會員說明"], S.me)}</p>
    ${expiryNotice()}
    ${S.me.message ? `<div class="card"><h2>給你的話</h2><p>${esc(S.me.message)}</p></div>` : ""}
    <div class="links">
      <a class="link" href="?v=courses"><span class="ic">📚</span><span><b>課程</b><small>即將推出</small></span></a>
      <a class="link" href="?v=ai"><span class="ic">✨</span><span><b>AI 小幫手</b><small>即將推出</small></span></a>
    </div>
    <div class="card"><h2>會籍</h2><dl><dt>方案</dt><dd>${esc(S.me.plan) || "—"}</dd><dt>到期日</dt><dd>${esc(S.me.expiry) || "—"}</dd></dl></div>
    <div class="card"><h2>我的會員資料</h2>${profile()}</div>
    <button class="ghost" id="profileEdit">編輯我的資料</button>`;
}
function renderProfileEdit() {
  $("#app").innerHTML = `<h1>編輯我的資料</h1>
    <p class="lead">改完按「儲存」。身分、方案、到期日由管理者處理，這裡不能改。</p>
    <div class="card">${FIELDS.map(([k, label, req, type]) => input(k, label, req, type, S.form)).join("")}</div>
    <button class="ghost" id="cancelProfile">← 不修改了</button>`;
  $("#bar").hidden = false;
  $("#barIn").innerHTML = `<button class="primary" id="saveProfile" ${S.busy ? "disabled" : ""}>${S.busy ? "儲存中…" : "儲存"}</button>`;
}
// 到期前 REMIND_DAYS 天開始提醒；不推播，只在會員畫面上顯示
function expiryNotice() {
  if (!S.me.expiry || daysLeft(S.me.expiry) > REMIND_DAYS || !S.site["到期提醒"]) return "";
  return `<div class="notice">${fill(S.site["到期提醒"], S.me)}</div>`;
}
function renderBanned() {
  $("#app").innerHTML = `<div class="status"><div class="big">⛔</div><h2>會員功能暫停使用</h2>
    <p class="lead">${fill(S.site["停權說明"], S.me)}</p></div>`;
}
function profile() {
  const m = S.me;
  return `<dl>${FIELDS.filter(([k]) => k !== "note").map(([k, label]) => `<dt>${label}</dt><dd>${esc(m[k]) || "—"}</dd>`).join("")}</dl>`;
}
function payInfo() {
  const m = S.me, p = planOf(m.plan);
  return `<dl><dt>方案</dt><dd>${esc(m.plan) || "—"}</dd><dt>金額</dt><dd>${p ? money(p.price) : "—"}</dd>
    <dt>末五碼</dt><dd>${esc(m.pay5) || "—"}</dd><dt>匯款日期</dt><dd>${esc(m.paydate) || "—"}</dd></dl>`;
}
function toast(msg) {
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg;
  document.body.append(t); setTimeout(() => t.remove(), 2400);
}
// 基本資料的檢查：申請和自己改資料共用
function checkBasic(f) {
  for (const [k, label, req] of FIELDS) {
    f[k] = (S.form[k] || "").trim();
    if (req && !f[k]) { toast(`請填「${label}」`); return false; }
  }
  if (f.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email)) { toast("Email 格式不對，請再檢查一次"); return false; }
  if (!/^[0-9+\-()#\s]{8,}$/.test(f.phone)) { toast("手機號碼格式不對，請再檢查一次"); return false; }
  return true;
}

// ===== 操作 =====
document.addEventListener("input", e => { if (e.target.dataset.k) S.form[e.target.dataset.k] = e.target.value; });
document.addEventListener("change", e => { if (e.target.name === "plan") { S.form.plan = e.target.value; render(); } });
document.addEventListener("click", async e => {
  const t = e.target.closest("button"); if (!t) return;
  if (t.id === "edit") { S.editing = true; render(); return; }
  if (t.id === "cancelEdit") { S.editing = false; render(); return; }
  if (t.id === "profileEdit") { S.profileEdit = true; render(); scrollTo(0, 0); return; }
  if (t.id === "cancelProfile") { S.profileEdit = false; for (const [k] of FIELDS) S.form[k] = S.me[k] || ""; render(); return; }
  if (t.id === "saveProfile" && !S.busy) {
    const f = {};
    if (!checkBasic(f)) return;
    S.busy = true; render();
    try { await api.profile(f); Object.assign(S.me, f); S.busy = false; S.profileEdit = false; toast("已儲存"); render(); scrollTo(0, 0); }
    catch (x) { S.busy = false; if (!handleApiError(x)) { toast("儲存失敗，請再按一次"); render(); } }
    return;
  }
  if (t.id === "send" && !S.busy) {
    const f = { plan: S.form.plan || "" };
    if (!planOf(f.plan)) { toast("請選擇方案"); return; }
    for (const [k, label, req] of PAY_FIELDS) {
      f[k] = (S.form[k] || "").trim();
      if (req && !f[k]) { toast(`請填「${label}」`); return; }
    }
    if (!/^\d{5}$/.test(f.pay5)) { toast("匯款末五碼請填 5 個數字"); return; }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f.paydate)) { toast("請選擇匯款日期"); return; }
    if (!checkBasic(f)) return;
    S.busy = true; render();
    try { Object.assign(S.me, await api.apply(f)); S.busy = false; S.editing = false; toast("已送出，等待審核"); render(); scrollTo(0, 0); }
    catch (x) {
      S.busy = false;
      if (x.code === "bad_plan") { toast("這個方案已經下架，請重新整理頁面"); render(); }
      else if (!handleApiError(x)) { toast("送出失敗，請再按一次"); render(); }
    }
  }
});

// ===== LIFF 與錯誤處理（沿用朕宏會員模組的做法） =====
function handleApiError(e) {
  if (!(e instanceof ApiError)) return false;
  if (e.code === "auth" || e.code === "no_token") {
    // 只自動重新登入一次；兩分鐘內又失敗就停下來顯示原因，避免無限重新整理、一直消耗 Make 額度
    let last = 0;
    try { last = +sessionStorage.getItem("relogin") || 0; } catch (x) {}
    if (e.code === "auth" && Date.now() - last > 120000) {
      try { sessionStorage.setItem("relogin", String(Date.now())); } catch (x) {}
      if (liff.isInClient()) location.reload(); else { liff.logout(); liff.login({ redirectUri: location.href }); }
      return true;
    }
    $("#app").innerHTML = `<div class="blocked"><h2>無法確認你的身分</h2><p>請關閉頁面，從 LINE 重新開啟。</p></div>`;
    return true;
  }
  return false;
}
function loadScript(src) {
  return new Promise((ok, fail) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = fail; document.body.append(s); });
}
// 每個畫面都先讀 me：身分、前台設定、方案一次拿齊（順便讓後端校正選單）
async function loadMe() {
  try {
    const r = await api.me();
    S.site = nobj(r.site);
    S.plans = (r.plans || []).map(x => nobj(x.properties)).filter(p => p["名稱"] && p["上架"] !== false)
      .map(p => ({ name: p["名稱"], label: p["標籤"], price: p["價格"], months: p["會籍月數"], desc: p["說明"], order: p["排序"] || 0 }))
      .sort((a, b) => a.order - b.order);
    delete r.site; delete r.plans;
    S.me = r;
    for (const [k] of [...FIELDS, ...PAY_FIELDS]) S.form[k] = S.me[k] || "";
    S.form.plan = S.me.plan || "";
    if (S.site["學院名稱"]) { $("#brand").textContent = S.site["學院名稱"]; document.title = `${S.site["簡稱"] || S.site["學院名稱"]}｜會員專區`; }
    render();
  } catch (e) {
    if (!handleApiError(e)) $("#app").innerHTML = `<div class="blocked"><h2>暫時無法讀取</h2><p>請稍後再開一次。</p></div>`;
  }
}
(async () => {
  if (IN_LIFF_HOST) {
    try {
      await liff.init({ liffId: CONFIG.liffId });
      if (!liff.isLoggedIn()) { liff.login({ redirectUri: location.href }); return; }
    } catch (e) { $("#app").innerHTML = `<div class="blocked"><h2>無法開啟</h2><p>請從 LINE 開啟這個頁面。</p></div>`; return; }
  } else {
    await loadScript("mock.js"); api = window.MOCK_API;
  }
  render();
  loadMe();
})();
