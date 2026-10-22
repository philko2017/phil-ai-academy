// 本機預覽用的模擬後端：不連 LINE、不連 Make。網址加 ?state=pending｜member｜premium｜expired｜banned 可以直接看各身分的畫面
(() => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const st = new URLSearchParams(location.search).get("state") || "guest";
  const filled = st !== "guest";
  // 模擬到期日：premium 五天後到期（看提醒），expired 四天前已到期（看續費畫面）
  const soon = n => { const d = new Date(); d.setDate(d.getDate() + n); return d.toLocaleDateString("sv-SE"); };
  let me = { ok: true, state: st, line: "Phil Ko", name: filled ? "柯小明" : "", phone: filled ? "0912-345-678" : "",
             email: filled ? "ming@example.com" : "", note: "", plan: filled ? "月繳 699" : "", pay5: filled ? "12345" : "",
             paydate: filled ? "2026-10-23" : "", expiry: { member: "2026-11-23", premium: soon(5), expired: soon(-4) }[st] || "" };
  window.MOCK_API = {
    async me() { await wait(400); return { ...me }; },
    async apply(f) { await wait(700); me = { ...me, ...f, state: ["guest", "expired"].includes(me.state) ? "pending" : me.state }; return { ...me }; },
  };
})();
