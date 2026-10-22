// ===== 設定：LIFF ID 與 API 網址。正式網址（GitHub Pages）一律用真資料；本機預覽才載入 mock.js 的模擬資料 =====
// 會員頁面送到 Make 情境「AI學院｜會員 API」，用欄位 a 分辨動作：me 我的身分（順便校正選單）｜apply 申請入會
const CONFIG = {
  liffId: "2012161136-mSmbv0VR",
  apiUrl: "https://hook.us2.make.com/vbwwyt6hjrveqmylu42gkovs2ulf9jdm",
};
const IN_LIFF_HOST = location.hostname.endsWith("github.io");
// 學院名稱、介紹、方案、收款帳戶放在 assets/brand/brand.json
const BRAND_URL = "../../assets/brand/brand.json";

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = n => "NT$ " + Number(n || 0).toLocaleString("zh-TW");

// 申請表單欄位：代號、標題、必填、輸入型別（和 tools/make_blueprints.py 的 APPLY_FIELDS 對應）
const FIELDS = [
  ["name", "姓名", true, "text"], ["phone", "手機", true, "tel"], ["email", "Email", false, "email"],
  ["note", "想學什麼、怎麼認識學院的（選填）", false, "area"],
];
// 匯款回報欄位（範例，不會真的收錢）
const PAY_FIELDS = [["pay5", "匯款帳號末五碼", true, "text"], ["paydate", "匯款日期", true, "date"]];
// 頁面狀態 → 標籤：非會員、審核中、一般會員、高級會員、停權
const BADGE = { guest: ["guest", "非會員"], pending: ["pending", "審核中"], member: ["member", "一般會員"],
                premium: ["premium", "高級會員"], banned: ["banned", "暫停使用"] };
const IS_MEMBER = st => st === "member" || st === "premium";

// ===== 正式後端：用表單格式送出，瀏覽器不會先送 CORS 預檢 =====
class ApiError extends Error { constructor(code) { super(code); this.code = code; } }
// 後端把自由文字 URL 編碼後才放進 JSON（Make 沒有 JSON 跳脫函式），這裡解碼
const ENC_KEYS = new Set(["name", "phone", "email", "note", "line"]);
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
let api = { me: () => post({ a: "me" }), apply: f => post({ a: "apply", ...f }) };

// ===== 狀態與畫面 =====
const params = new URLSearchParams(location.search);
// 選單上的功能還在規劃，先顯示「即將推出」；做好之後在這裡換成真正的畫面
const SOON = {
  courses: ["📚", "課程", "學院的課程與直播，之後會列在這裡，也能直接報名。"],
  ai: ["✨", "AI 小幫手", "之後可以在這裡問課程、工具與入會的問題，AI 會幫你回答。"],
};
const V = params.get("v");
const S = { view: V === "about" || SOON[V] ? V : "home", me: null, brand: {}, form: {}, busy: false, editing: false };
const plans = () => S.brand.plans || [];
const planOf = id => plans().find(p => p.id === id);

function render() {
  const b = S.me && BADGE[S.me.state];
  $("#badge").className = b ? "badge " + b[0] : "";
  $("#badge").textContent = b ? b[1] : "";
  $("#bar").hidden = true;
  if (S.view === "about") return renderAbout();
  if (SOON[S.view]) return renderSoon(SOON[S.view]);
  if (!S.me) { $("#app").innerHTML = `<p class="blocked">讀取中…</p>`; return; }
  const st = S.me.state;
  if (IS_MEMBER(st)) return renderMember();
  if (st === "banned") return renderBanned();
  if (st === "pending" && !S.editing) return renderPending();
  renderApply();
}
function renderAbout() {
  const br = S.brand;
  $("#app").innerHTML = `<h1>${esc(br.name || "關於學院")}</h1>
    <div class="card"><p>${esc(br.about || "")}</p>${br.contact ? `<p class="lead" style="margin-top:10px">${esc(br.contact)}</p>` : ""}</div>
    <div class="links"><a class="link" href="?v=home"><span class="ic">📝</span><span><b>會員專區</b><small>申請入會、查看會員資料</small></span></a></div>`;
}
function renderSoon([icon, title, text]) {
  $("#app").innerHTML = `<div class="status"><div class="big">${icon}</div><h2>${title}</h2><p class="lead">${text}</p>
    <p class="lead" style="margin-top:14px;font-weight:700;color:var(--brand)">即將推出</p></div>
    <div class="links"><a class="link" href="?v=home"><span class="ic">🪪</span><span><b>會員專區</b><small>入會申請、我的會員資料</small></span></a></div>`;
}
const input = (k, label, req, type, f) => `<label class="f">${label}${req ? " <b>*</b>" : ""}${type === "area"
  ? `<textarea data-k="${k}">${esc(f[k])}</textarea>`
  : `<input data-k="${k}" type="${type}" value="${esc(f[k])}" ${k === "name" ? 'autocomplete="name"' : ""}${k === "pay5" ? ' inputmode="numeric" maxlength="5"' : ""}>`}</label>`;
function renderApply() {
  const editing = S.me.state === "pending";
  const f = S.form, bank = S.brand.bank || {};
  if (!planOf(f.plan) && plans()[0]) f.plan = plans()[0].id;
  const plan = planOf(f.plan);
  $("#app").innerHTML = `<h1>${editing ? "修改入會申請" : "申請入會"}</h1>
    <p class="lead">${editing ? "修改後重新送出，管理者會看到最新的資料。" : `歡迎加入${esc(S.brand.name || "")}。選擇方案、完成匯款並填寫資料，管理者確認入帳後，下方選單會換成會員版。`}</p>
    <div class="card"><h2>① 選擇方案</h2><div class="plans">${plans().map(p => `<label class="plan ${p.id === f.plan ? "on" : ""}">
      <input type="radio" name="plan" value="${esc(p.id)}" ${p.id === f.plan ? "checked" : ""}>
      <span><b>${esc(p.label)}　${money(p.price)}</b><small>${esc(p.desc)}</small></span></label>`).join("")}</div></div>
    <div class="card"><h2>② 匯款${bank.demo ? `<span class="demo">範例</span>` : ""}</h2>
      <p class="lead">請匯 <b style="color:var(--text)">${money(plan && plan.price)}</b> 到下面的帳戶，再填末五碼與日期。</p>
      <div class="bank"><dl><dt>銀行</dt><dd>${esc(bank.name)}</dd><dt>帳號</dt><dd>${esc(bank.account)}</dd><dt>戶名</dt><dd>${esc(bank.holder)}</dd></dl></div>
      ${bank.demo ? `<p class="lead" style="margin-top:8px;font-size:14px">這是示範帳戶，請不要真的匯款；末五碼隨便填 5 個數字即可。</p>` : ""}
      ${PAY_FIELDS.map(([k, label, req, type]) => input(k, label, req, type, f)).join("")}</div>
    <div class="card"><h2>③ 基本資料</h2>${FIELDS.map(([k, label, req, type]) => input(k, label, req, type, f)).join("")}</div>
    ${editing ? `<button class="ghost" id="cancelEdit">← 不修改了</button>` : ""}`;
  $("#bar").hidden = false;
  $("#barIn").innerHTML = `<button class="primary" id="send" ${S.busy ? "disabled" : ""}>${S.busy ? "送出中…" : editing ? "送出修改" : "送出申請"}</button>`;
}
function renderPending() {
  $("#app").innerHTML = `<div class="status"><div class="big">⏳</div><h2>入會申請審核中</h2>
    <p class="lead">${esc(S.me.name)}，我們已收到你的申請。管理者確認入帳後，下方選單會自動換成會員版。</p></div>
    <div class="card"><h2>方案與匯款</h2>${payInfo()}</div>
    <div class="card"><h2>申請資料</h2>${profile()}</div>
    <button class="ghost" id="edit">修改申請資料</button>`;
}
function renderMember() {
  $("#app").innerHTML = `<h1>${esc(S.me.name)}，歡迎回來</h1>
    <p class="lead">你是${esc(S.brand.name || "")}的${BADGE[S.me.state][1]}，下方選單是會員版。</p>
    <div class="links">
      <a class="link" href="?v=courses"><span class="ic">📚</span><span><b>課程</b><small>即將推出</small></span></a>
      <a class="link" href="?v=ai"><span class="ic">✨</span><span><b>AI 小幫手</b><small>即將推出</small></span></a>
    </div>
    <div class="card"><h2>會籍</h2><dl><dt>方案</dt><dd>${esc(S.me.plan) || "—"}</dd><dt>到期日</dt><dd>${esc(S.me.expiry) || "—"}</dd></dl></div>
    <div class="card"><h2>我的會員資料</h2>${profile()}<p class="lead" style="margin-top:10px;font-size:14px">資料要修改請洽管理者。</p></div>`;
}
function renderBanned() {
  $("#app").innerHTML = `<div class="status"><div class="big">⛔</div><h2>會員功能暫停使用</h2>
    <p class="lead">如有疑問請洽學院管理者。</p></div>`;
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

// ===== 操作 =====
document.addEventListener("input", e => { if (e.target.dataset.k) S.form[e.target.dataset.k] = e.target.value; });
document.addEventListener("change", e => { if (e.target.name === "plan") { S.form.plan = e.target.value; render(); } });
document.addEventListener("click", async e => {
  const t = e.target.closest("button"); if (!t) return;
  if (t.id === "edit") { S.editing = true; render(); return; }
  if (t.id === "cancelEdit") { S.editing = false; render(); return; }
  if (t.id === "send" && !S.busy) {
    const f = { plan: S.form.plan || "" };
    if (!planOf(f.plan)) { toast("請選擇方案"); return; }
    for (const [k, label, req] of [...PAY_FIELDS, ...FIELDS]) {
      f[k] = (S.form[k] || "").trim();
      if (req && !f[k]) { toast(`請填「${label}」`); return; }
    }
    if (!/^\d{5}$/.test(f.pay5)) { toast("匯款末五碼請填 5 個數字"); return; }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f.paydate)) { toast("請選擇匯款日期"); return; }
    if (f.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email)) { toast("Email 格式不對，請再檢查一次"); return; }
    if (!/^[0-9+\-()#\s]{8,}$/.test(f.phone)) { toast("手機號碼格式不對，請再檢查一次"); return; }
    S.busy = true; render();
    try { S.me = await api.apply(f); S.busy = false; S.editing = false; toast("已送出，等待審核"); render(); scrollTo(0, 0); }
    catch (x) { S.busy = false; if (!handleApiError(x)) { toast("送出失敗，請再按一次"); render(); } }
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
async function loadMe() {
  try {
    S.me = await api.me();
    for (const [k] of [...FIELDS, ...PAY_FIELDS]) S.form[k] = S.me[k] || "";
    S.form.plan = S.me.plan || "";
    render();
  } catch (e) {
    if (!handleApiError(e)) $("#app").innerHTML = `<div class="blocked"><h2>暫時無法讀取</h2><p>請稍後再開一次。</p></div>`;
  }
}
(async () => {
  try { S.brand = await (await fetch(BRAND_URL, { cache: "no-cache" })).json(); } catch (e) { S.brand = {}; }
  if (S.brand.name) { document.title = `${S.brand.short || S.brand.name}｜會員專區`; $("#brand").textContent = S.brand.name; }
  if (IN_LIFF_HOST) {
    if (!CONFIG.liffId || !CONFIG.apiUrl) { $("#app").innerHTML = `<div class="blocked"><h2>建置中</h2><p>會員頁面還沒接上 LINE 與 Make。</p></div>`; return; }
    try {
      await liff.init({ liffId: CONFIG.liffId });
      if (!liff.isLoggedIn()) { liff.login({ redirectUri: location.href }); return; }
    } catch (e) { $("#app").innerHTML = `<div class="blocked"><h2>無法開啟</h2><p>請從 LINE 開啟這個頁面。</p></div>`; return; }
  } else {
    await loadScript("mock.js"); api = window.MOCK_API;
  }
  render();
  // 「即將推出」畫面和學院介紹不需要身分；其他畫面讀取身分（順便讓後端校正選單）
  if (S.view === "home") loadMe();
})();
