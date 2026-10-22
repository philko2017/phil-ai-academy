// 本機預覽用的模擬後端：不連 LINE、不連 Make。網址加 ?state=pending｜member｜premium｜banned 可以直接看各身分的畫面
(() => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const st = new URLSearchParams(location.search).get("state") || "guest";
  const filled = st !== "guest";
  let me = { ok: true, state: st, line: "Phil Ko", name: filled ? "柯小明" : "", phone: filled ? "0912-345-678" : "",
             email: filled ? "ming@example.com" : "", note: "", plan: filled ? "首月 699" : "", pay5: filled ? "12345" : "",
             paydate: filled ? "2026-10-23" : "", expiry: st === "member" || st === "premium" ? "2026-11-23" : "" };
  window.MOCK_API = {
    async me() { await wait(400); return { ...me }; },
    async apply(f) { await wait(700); me = { ...me, ...f, state: me.state === "guest" ? "pending" : me.state }; return { ...me }; },
  };
})();
