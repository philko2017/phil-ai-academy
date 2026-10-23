// ===== 設定：LIFF ID 與 API 網址。正式網址（GitHub Pages）一律用真資料；本機預覽才載入 mock.js 的模擬資料 =====
// 會員通（LINE Member Kit）的會員頁面。送到 Make 情境「{專案}｜會員 API」，用欄位 a 分辨動作：me 我的身分（順便校正選單）｜apply 申請入會｜profile 改基本資料
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
    case "multi_select": return (p.multi_select || []).map(o => o.name);
    case "date": return p.date ? p.date.start : "";
    case "url": return p.url || "";
    case "email": return p.email || "";
    case "phone_number": return p.phone_number || "";
    // 檔案和媒體：取第一個檔案的網址（上傳到 Notion 的檔案網址約一小時後失效，每次打開都會重新拿）
    case "files": { const f = (p.files || [])[0]; return f ? (f.file ? f.file.url : f.external ? f.external.url : "") : ""; }
    default: return "";
  }
}
const nobj = props => Object.fromEntries(Object.entries(props || {}).map(([k, v]) => [k, nval(v)]));
// Notion 查詢結果（頁面陣列）→ { id, 欄位… }
const nrows = rows => (rows || []).map(r => ({ id: r.id, ...nobj(r.properties) }));
// 「{姓名}」「{身分}」「{到期日}」換成這位會員的資料
const fill = (tpl, me) => esc(tpl || "").replace(/\{姓名\}/g, esc(me.name || me.line || ""))
  .replace(/\{身分\}/g, esc((BADGE[me.state] || [])[1] || "")).replace(/\{到期日\}/g, esc(me.expiry || ""));

// ===== 正式後端：用表單格式送出，瀏覽器不會先送 CORS 預檢 =====
class ApiError extends Error { constructor(code) { super(code); this.code = code; } }
// 後端把自由文字 URL 編碼後才放進 JSON（Make 沒有 JSON 跳脫函式），這裡解碼
const ENC_KEYS = new Set(["name", "phone", "email", "note", "line", "message", "link", "trial"]);
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
let api = { me: () => post({ a: "me" }), apply: f => post({ a: "apply", ...f }), profile: f => post({ a: "profile", ...f }),
  news: () => post({ a: "news" }), courses: () => post({ a: "courses" }), open: id => post({ a: "course_open", id }),
  adminList: () => post({ a: "admin_list" }), adminSet: (id, op) => post({ a: "admin_set", id, op }) };

// ===== 狀態與畫面 =====
const params = new URLSearchParams(location.search);
// 還在規劃的功能先顯示「即將推出」；說明文字在 Notion「前台設定」
const SOON = { ai: ["✨", "AI 小幫手", "AI 小幫手預告"] };
const VIEWS = ["home", "about", "news", "courses", "admin", ...Object.keys(SOON)];
const V = params.get("v");
const S = { view: VIEWS.includes(V) ? V : "home", id: params.get("id") || "", me: null, site: {}, plans: [], form: {},
            busy: false, editing: false, profileEdit: false, news: null, items: null, members: null, q: "", sel: "" };
const IS_ADMIN = () => S.me && S.me.admin === "Y";
const planOf = name => S.plans.find(p => p.name === name);

function render() {
  const b = S.me && BADGE[S.me.state];
  $("#badge").className = b ? "badge " + b[0] : "";
  $("#badge").textContent = b ? b[1] : "";
  $("#bar").hidden = true;
  if (!S.me) { $("#app").innerHTML = loading(); return; }
  if (S.view === "about") return renderAbout();
  if (LISTS[S.view]) return S.id ? renderItem(S.view) : renderList(S.view);
  if (S.view === "admin") return renderAdmin();
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
    <div class="links">${navLink("home", "🪪", "會員專區", "入會申請、我的會員資料")}</div>`;
}
// 等待中：文字後面三個點輪流跳動（動畫在 index.html 的 .dots）
const DOTS = `<span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>`;
const loading = (text = "讀取中") => `<p class="blocked" role="status">${text}${DOTS}</p>`;
const navLink = (v, ic, title, sub, id = "") => `<a class="link" href="?v=${v}${id ? "&id=" + id : ""}" data-nav="${v}" data-id="${esc(id)}"><span class="ic">${ic}</span><span><b>${esc(title)}</b><small>${esc(sub)}</small></span></a>`;
// 圖片：有雲端硬碟圖床網址（Make「圖片：上傳到雲端硬碟」寫回的）就用 Google 縮圖：裁成 16:9、JPEG 品質 80，手機會暫存一天。
// 不用 webp：PNG 原圖轉出來是無損 webp，1280 寬還有 1MB（2026-10-23 實測）。還沒上傳的先用 Notion 原圖（網址每小時換一次，不能暫存）
const SIZES = { list: "w640-h360-c-rj-l80", full: "w1280-h720-c-rj-l80" };
const pic = (hosted, original, size) => hosted ? hosted.split("#")[0] + "=" + SIZES[size] : original;
const cover = (url, alt) => url ? `<img class="cover" src="${esc(url)}" alt="${esc(alt || "")}" loading="lazy" decoding="async">` : "";
// 有沒有權限看某個開放對象的內容（Make 點開時會再檢查一次）
function canSee(aud) {
  if (IS_ADMIN() || aud === "公開") return true;
  const st = S.me.state;
  if (aud === "一般會員") return IS_MEMBER(st);
  if (aud === "高級會員") return st === "premium";
  return false;
}
// 進一步的資料（消息、課程、名冊）切換畫面時才讀，讀過就留著，不必重新整理頁面
async function need(key, call, pick) {
  if (S[key]) return true;
  try { S[key] = nrows(pick(await call())); return true; }
  catch (e) { if (!handleApiError(e)) $("#app").innerHTML = `<div class="blocked"><h2>暫時無法讀取</h2><p>請稍後再開一次。</p></div>`; return false; }
}
// 切換畫面記進瀏覽紀錄，左上角「‹」和手機的返回鍵都能回上一頁；replace 用在沒有上一頁時的退路
let depth = 0;
function go(view, id = "", replace = false) {
  S.view = view; S.id = id; S.profileEdit = false; S.editing = false;
  const url = `?v=${view}${id ? "&id=" + id : ""}`;
  if (replace) history.replaceState({ depth }, "", url); else history.pushState({ depth: ++depth }, "", url);
  render(); scrollTo(0, 0);
}

// ===== 最新消息、課程：同一張 Notion 內容庫，用「標籤」決定出現在哪裡；卡片一律是縮圖、標題、一行簡介 =====
const LISTS = { news: ["news", api => api.news, r => r.news, "最新消息"], courses: ["items", api => api.courses, r => r.items, ""] };
function loadList(view) {
  const [key, call, pick] = LISTS[view];
  if (S[key]) return S[key];
  $("#app").innerHTML = loading();
  need(key, call(api), pick).then(ok => ok && render());
  return null;
}
const thumb = (it, size = "list") => cover(pic(it["封面網址"], it["封面"], size), it["標題"]) || `<div class="cover ph">${esc(it["類型"])}</div>`;
const lockText = it => it["開放對象"] === "單獨購買" ? money(it["價格"]) : it["開放對象"] + "專屬";
function itemCard(it, view) {
  return `<a class="card item" href="?v=${view}&id=${it.id}" data-nav="${view}" data-id="${it.id}">
    <div class="cover-wrap">${thumb(it)}${canSee(it["開放對象"]) ? "" : `<span class="lock">🔒 ${esc(lockText(it))}</span>`}</div>
    <h2>${esc(it["標題"])}</h2><p class="lead">${esc(it["公開摘要"])}</p></a>`;
}
function renderList(view) {
  const list = loadList(view); if (!list) return;
  const title = view === "news" ? "最新消息" : IS_MEMBER(S.me.state) || IS_ADMIN() ? "我的課程" : "課程介紹";
  const empty = view === "news" ? "目前沒有消息" : S.site["課程預告"] || "課程準備中";
  $("#app").innerHTML = `<h1>${title}</h1>${list.length ? `<div class="grid">${list.map(it => itemCard(it, view)).join("")}</div>`
    : `<p class="blocked">${esc(empty)}</p>`}`;
}
function renderItem(view) {
  const list = loadList(view); if (!list) return;
  const back = navLink(view, view === "news" ? "📰" : "📚", view === "news" ? "回最新消息" : "回課程列表", "");
  const it = list.find(x => x.id.replace(/-/g, "") === S.id.replace(/-/g, ""));
  if (!it) { $("#app").innerHTML = `<div class="blocked"><h2>找不到這個內容</h2></div><div class="links">${back}</div>`; return; }
  const aud = it["開放對象"], ok = canSee(aud), st = S.me.state;
  // 公告只顯示內容，不放按鈕；其他類型依身分給「開始觀看／下載」或解鎖方式
  const cta = it["類型"] === "公告" && ok ? ""
    : ok ? `<button class="primary" id="openItem">${it["類型"] === "數位產品" ? "下載" : "開始觀看"}</button>`
    : aud === "單獨購買" ? `<button class="primary" disabled>購買 ${money(it["價格"])}（即將推出）</button>`
    : IS_MEMBER(st) ? `<p class="notice">這是高級會員專屬內容，升級請洽管理者。</p>`
    : `<a class="primary btn" href="?v=home" data-nav="home">申請加入，解鎖內容</a>`;
  $("#app").innerHTML = `<div class="detail">${thumb(it, "full")}
    <p class="meta">${esc([it["類型"], aud, it["上架日期"]].filter(Boolean).join(" · "))}</p><h1>${esc(it["標題"])}</h1><p class="lead">${esc(it["公開摘要"])}</p>
    <div class="cta">${cta}${!ok && it["試看連結"] ? `<a class="ghost" href="${esc(it["試看連結"])}" target="_blank" rel="noopener">先試看 →</a>` : ""}</div></div>
    <div class="links">${back}</div>`;
}
async function openItem() {
  if (S.busy) return;
  S.busy = true; $("#openItem").disabled = true; $("#openItem").innerHTML = "開啟中" + DOTS;
  try {
    const r = await api.open(S.id);
    if (!r.link) throw new ApiError("no_link");
    if (window.liff && liff.isInClient && liff.isInClient()) liff.openWindow({ url: r.link, external: false }); else location.href = r.link;
  } catch (e) {
    if (!handleApiError(e)) toast(e.code === "locked" ? "這個內容需要更高的身分才能看" : e.code === "no_link" ? "這個內容還沒放連結" : "開啟失敗，請再試一次");
  }
  S.busy = false; render();
}

// ===== 管理會員（名冊「角色」勾管理者的人才看得到；Make 每個動作都會再檢查）=====
const IDENTS = ["非會員", "審核中", "一般會員", "高級會員", "已到期", "停權"];
const OPS = { 審核中: [["approve", "核准入會"]], 一般會員: [["premium", "升級高級會員"], ["ban", "停權"]],
              高級會員: [["ban", "停權"]], 已到期: [["ban", "停權"]], 停權: [["restore", "恢復為一般會員"]], 非會員: [["ban", "停權"]] };
const OP_DONE = { approve: "一般會員", premium: "高級會員", ban: "停權", restore: "一般會員" };
function renderAdmin() {
  if (!IS_ADMIN()) { $("#app").innerHTML = `<div class="blocked"><h2>只有管理者可以使用</h2></div>`; return; }
  if (!S.members) { $("#app").innerHTML = loading("讀取名冊中"); need("members", api.adminList, r => r.members).then(ok => ok && render()); return; }
  const m = S.members;
  const count = id => m.filter(x => x["身分"] === id).length;
  $("#app").innerHTML = `<h1>管理會員</h1>
    <div class="stats"><div class="stat total"><b>${m.length}</b><small>全部</small></div>${IDENTS.map(i => `<div class="stat${i === "審核中" && count(i) ? " hot" : ""}"><b>${count(i)}</b><small>${i}</small></div>`).join("")}</div>
    <label class="f search"><input id="q" type="search" placeholder="搜尋姓名、電話、Email、LINE 名稱" value="${esc(S.q)}"></label>
    <div class="rows" id="rows">${adminRows()}</div>
    <div class="links">${navLink("home", "🪪", "回會員專區", "")}</div>`;
  // 打字時只換名冊，不重畫搜尋框，中文輸入法選字才不會被打斷
  $("#q").oninput = e => { S.q = e.target.value; $("#rows").innerHTML = adminRows(); };
}
function adminRows() {
  const q = S.q.trim().toLowerCase();
  const hit = x => !q || ["姓名", "電話", "Email", "LINE 顯示名稱"].some(k => String(x[k] || "").toLowerCase().includes(q));
  const order = x => (x["身分"] === "審核中" ? 0 : 1);
  return S.members.filter(hit).sort((a, b) => order(a) - order(b)).map(x => `<div class="row${x.id === S.sel ? " open" : ""}" data-sel="${x.id}">
      <div class="row-head"><b>${esc(x["姓名"])}</b><span class="badge ${badgeOf(x["身分"])}">${esc(x["身分"])}</span>${(x["角色"] || []).includes("管理者") ? `<span class="tag">管理者</span>` : ""}</div>
      <small>${esc([x["電話"], x["方案"], x["到期日"] && "到期 " + x["到期日"]].filter(Boolean).join(" · "))}</small>
      ${x.id === S.sel ? adminDetail(x) : ""}</div>`).join("") || `<p class="blocked">找不到符合的人</p>`;
}
const badgeOf = id => ({ 非會員: "guest", 審核中: "pending", 一般會員: "member", 高級會員: "premium", 已到期: "expired", 停權: "banned" }[id] || "guest");
function adminDetail(x) {
  const info = [["LINE 名稱", x["LINE 顯示名稱"]], ["Email", x["Email"]], ["方案", x["方案"]], ["應繳", x["應繳金額"] ? money(x["應繳金額"]) : ""],
                ["末五碼", x["匯款末五碼"]], ["匯款日期", x["匯款日期"]], ["申請", (x["申請時間"] || "").slice(0, 10)], ["到期日", x["到期日"]],
                ["好友狀態", x["好友狀態"]], ["備註", x["備註"]]].filter(([, v]) => v);
  return `<dl class="info">${info.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    <div class="ops">${(OPS[x["身分"]] || []).map(([op, label]) => `<button class="op ${op}" data-op="${op}" data-id="${x.id}">${label}</button>`).join("")}</div>`;
}
async function adminOp(id, op) {
  const x = S.members.find(m => m.id === id);
  const label = (OPS[x["身分"]] || []).find(o => o[0] === op)[1];
  if (!confirm(`${label}：${x["姓名"]}？`)) return;
  try { await api.adminSet(id, op); x["身分"] = OP_DONE[op]; toast(`已${label}`); render(); }
  catch (e) { if (!handleApiError(e)) toast(e.code === "not_allowed" ? "這個身分不能做這個動作，請重新整理" : "操作失敗，請再試一次"); }
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
  $("#app").innerHTML = `${editing ? "" : cover(pic(s["邀請圖網址"], s["邀請圖"], "full"), "邀請加入")}<h1>${editing ? "修改申請" : renew ? "續費" : "申請入會"}</h1>
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
  $("#barIn").innerHTML = `<button class="primary" id="send" ${S.busy ? "disabled" : ""}>${S.busy ? "送出中" + DOTS : editing ? "送出修改" : renew ? "送出續費" : "送出申請"}</button>`;
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
      ${IS_ADMIN() ? navLink("admin", "🛠", "管理會員", "核准、升級、停權、恢復") : ""}
      ${navLink("news", "📰", "最新消息", "公告與活動")}
      ${navLink("courses", "📚", "我的課程", "影片與數位產品")}
      ${navLink("ai", "✨", "AI 小幫手", "即將推出")}
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
  $("#barIn").innerHTML = `<button class="primary" id="saveProfile" ${S.busy ? "disabled" : ""}>${S.busy ? "儲存中" + DOTS : "儲存"}</button>`;
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
// 左上角「‹」：先離開編輯狀態；有上一頁就回上一頁；直接從選單打開的話，內容頁回列表、其他回會員專區，會員專區再按就關閉
function goBack() {
  if (S.profileEdit) { S.profileEdit = false; for (const [k] of FIELDS) S.form[k] = S.me[k] || ""; render(); return; }
  if (S.editing) { S.editing = false; render(); return; }
  if (depth > 0) { history.back(); return; }
  if (S.id) return go(S.view, "", true);
  if (S.view !== "home") return go("home", "", true);
  if (window.liff && liff.isInClient && liff.isInClient()) liff.closeWindow(); else history.back();
}
addEventListener("popstate", e => {
  const p = new URLSearchParams(location.search), v = p.get("v");
  depth = (e.state && e.state.depth) || 0;
  S.view = VIEWS.includes(v) ? v : "home"; S.id = p.get("id") || ""; S.profileEdit = false; S.editing = false;
  render(); scrollTo(0, 0);
});
document.addEventListener("click", async e => {
  // 頁面內切換畫面：不重新整理，省下重新讀身分的 Make 點數
  const nav = e.target.closest("[data-nav]");
  if (nav) { e.preventDefault(); go(nav.dataset.nav, nav.dataset.id || ""); return; }
  const op = e.target.closest("[data-op]");
  if (op) { adminOp(op.dataset.id, op.dataset.op); return; }
  const row = e.target.closest("[data-sel]");
  if (row && !e.target.closest("button, input")) { S.sel = S.sel === row.dataset.sel ? "" : row.dataset.sel; $("#rows").innerHTML = adminRows(); return; }
  const t = e.target.closest("button"); if (!t) return;
  if (t.id === "back") { goBack(); return; }
  if (t.id === "openItem") { openItem(); return; }
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
// 標誌文字與主色來自 Notion「前台設定」：深色模式和淺底色由主色換算，換客戶不用改程式
function mixHex(a, b, t) {
  const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const [x, y] = [p(a), p(b)];
  return "#" + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, "0")).join("");
}
function applyBrand(site) {
  if (site["標誌文字"]) { $("#mark").textContent = site["標誌文字"]; $("#mark").hidden = false; }
  const c = String(site["主色"] || "").trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(c)) return;
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const [r, g, b] = [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const light = (r * 299 + g * 587 + b * 114) / 1000 > 150;   // 主色太亮時，按鈕字改深色
  const root = document.documentElement.style;
  root.setProperty("--brand", dark ? mixHex(c, "#FFFFFF", 0.45) : c);
  root.setProperty("--on-brand", dark || light ? "#13151C" : "#FFFFFF");
  root.setProperty("--brand-bg", dark ? mixHex(c, "#13151C", 0.75) : mixHex(c, "#FFFFFF", 0.88));
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
    applyBrand(S.site);
    if (S.site["學院名稱"]) { $("#brand").textContent = S.site["學院名稱"]; document.title = `${S.site["簡稱"] || S.site["學院名稱"]}｜會員專區`; }
    render();
  } catch (e) {
    if (!handleApiError(e)) $("#app").innerHTML = `<div class="blocked"><h2>暫時無法讀取</h2><p>請稍後再開一次。</p></div>`;
  }
}
(async () => {
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
  loadMe();
})();
