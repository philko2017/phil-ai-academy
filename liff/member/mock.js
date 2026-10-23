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
  window.MOCK_API = {
    async me() { await wait(400); return { ...me, site, plans }; },
    async apply(f) { await wait(700); me = { ...me, ...f, state: ["guest", "expired"].includes(me.state) ? "pending" : me.state }; return { ...me }; },
    async profile(f) { await wait(500); me = { ...me, ...f }; return { ok: true }; },
  };
})();
