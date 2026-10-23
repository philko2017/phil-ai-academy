// 本機預覽用的模擬後端：不連 LINE、不連 Make。網址加 ?state=pending｜member｜premium｜expired｜banned 可以直接看各身分的畫面
// 前台設定和方案用 Notion API 的原始格式模擬；文字是範例，正式內容在 Notion，不放進 repo
(() => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const st = new URLSearchParams(location.search).get("state") || "guest";
  const filled = st !== "guest";
  // 模擬到期日：premium 五天後到期（看提醒），expired 四天前已到期（看續費畫面）
  const soon = n => { const d = new Date(); d.setDate(d.getDate() + n); return d.toLocaleDateString("sv-SE"); };
  const text = s => ({ type: "rich_text", rich_text: [{ plain_text: s }] });
  const site = {
    "名稱": { type: "title", title: [{ plain_text: "前台設定" }] },
    "學院名稱": text("範例學院"), "簡稱": text("範例"), "學院介紹": text("（學院介紹，正式內容在 Notion）"), "聯絡方式": text(""),
    "歡迎語": text("{姓名}，歡迎回來"), "會員說明": text("你是範例學院的{身分}。"), "申請說明": text("（申請說明）"),
    "審核中說明": text("{姓名}，我們已收到你的申請。"), "已到期說明": text("你的會籍已在 {到期日} 到期。"), "停權說明": text("（停權說明）"),
    "到期提醒": text("會籍將於 {到期日} 到期。"), "課程預告": text("（課程預告）"), "AI 小幫手預告": text("（AI 小幫手預告）"),
    "收款銀行": text("範例銀行"), "收款帳號": text("0000-0000"), "戶名": text("範例"), "匯款提醒": text("（匯款提醒）"),
    "範例帳戶": { type: "checkbox", checkbox: true }, "標誌文字": text("範"), "主色": text("#0CA678"),
  };
  const plan = (name, label, price, months, desc, order) => ({ properties: {
    "名稱": { type: "title", title: [{ plain_text: name }] }, "標籤": text(label), "價格": { type: "number", number: price },
    "會籍月數": { type: "number", number: months }, "說明": text(desc), "上架": { type: "checkbox", checkbox: true },
    "排序": { type: "number", number: order } } });
  const plans = [plan("方案 A", "方案 A", 100, 1, "（範例方案）", 1), plan("方案 B", "方案 B", 1000, 12, "（範例方案）", 2)];
  let me = { ok: true, state: st, line: "測試帳號", name: filled ? "柯小明" : "", phone: filled ? "0912-345-678" : "",
             email: filled ? "ming@example.com" : "", note: "", plan: filled ? "方案 A" : "", pay5: filled ? "12345" : "",
             paydate: filled ? "2026-10-23" : "", expiry: { member: "2026-11-23", premium: soon(5), expired: soon(-4) }[st] || "",
             message: st === "premium" ? "（管理者寫給這位會員的話）" : "" };
  // ?admin=1：以管理者身分預覽（看得到管理會員）
  const admin = new URLSearchParams(location.search).get("admin") === "1";
  // 圖片用 SVG 色塊代替，正式圖片在 Notion
  const pic = (label, color) => "data:image/svg+xml," + encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900"><rect width="1600" height="900" fill="${color}"/>` +
    `<text x="800" y="480" font-size="96" text-anchor="middle" fill="#fff" font-family="sans-serif">${label} 16:9</text></svg>`);
  const file = url => ({ type: "files", files: [{ type: "external", external: { url } }] });
  site["邀請圖"] = file(pic("邀請圖", "#3B5BDB"));
  const sel = v => ({ type: "select", select: v ? { name: v } : null });
  const row = (id, p) => ({ id, properties: p });
  const news = [
    row("n1", { "標題": { type: "title", title: [{ plain_text: "（範例）公開消息" }] }, "內文": text("所有人都看得到的公告。"),
                "發布日期": { type: "date", date: { start: "2026-10-23" } }, "對象": sel("公開"), "封面": file(pic("消息", "#0CA678")) }),
    row("n2", { "標題": { type: "title", title: [{ plain_text: "（範例）會員消息" }] }, "內文": text("只有會員看得到。"),
                "發布日期": { type: "date", date: { start: "2026-10-22" } }, "對象": sel("會員"), "封面": file("") }),
  ];
  const item = (id, title, type, aud, price, cov) => row(id, { "標題": { type: "title", title: [{ plain_text: title }] },
    "類型": sel(type), "開放對象": sel(aud), "價格": { type: "number", number: price }, "公開摘要": text("（公開摘要）"),
    "封面": cov ? file(pic(title, cov)) : { type: "files", files: [] } });
  const items = [item("c1", "免費入門課", "影片課程", "公開", null, "#F59F00"), item("c2", "會員課程", "影片課程", "一般會員", null, "#3B5BDB"),
                 item("c3", "高級課程", "影片課程", "高級會員", null, ""), item("c4", "範例電子書", "數位產品", "單獨購買", 299, "#7048E8")];
  const person = (id, name, ident, role) => row(id, { "姓名": { type: "title", title: [{ plain_text: name }] }, "身分": sel(ident),
    "電話": { type: "phone_number", phone_number: "0900-000-000" }, "方案": sel("方案 A"), "角色": { type: "multi_select", multi_select: role ? [{ name: role }] : [] },
    "到期日": { type: "date", date: ident.includes("會員") ? { start: "2026-11-23" } : null }, "匯款末五碼": text("12345") });
  const members = [person("m1", "王小明", "審核中"), person("m2", "陳大文", "一般會員"), person("m3", "林美美", "高級會員"),
                   person("m4", "張三", "已到期"), person("m5", "李四", "停權"), person("m6", "管理者", "一般會員", "管理者")];
  window.MOCK_API = {
    async me() { await wait(400); return { ...me, admin: admin ? "Y" : "N", site, plans }; },
    async apply(f) { await wait(700); me = { ...me, ...f, state: ["guest", "expired"].includes(me.state) ? "pending" : me.state }; return { ...me }; },
    async profile(f) { await wait(500); me = { ...me, ...f }; return { ok: true }; },
    async news() { await wait(400); return { news: news.filter(n => admin || ["member", "premium"].includes(st) || n.properties["對象"].select.name === "公開") }; },
    async courses() { await wait(400); return { items }; },
    async open() { await wait(400); return { link: "https://example.com/" }; },
    async adminList() { await wait(500); if (!admin) throw Object.assign(new Error("not_admin"), { code: "not_admin" }); return { members }; },
    async adminSet() { await wait(500); return { ok: true }; },
  };
})();
