"""產生 Phil 的 AI 學院會員模組的 Make 藍圖，輸出到 make/（改寫自 philko2017/line-namecard 的 tools/make_member_blueprint.py）：

- 會員_API.blueprint.json：「AI學院｜會員 API」
    LIFF 會員頁面：a=me 我的身分（順便校正選單）｜a=apply 申請入會＋匯款回報（欄位 t 是 LINE Access Token）
    Notion 核准連結：a=approve 核准入會｜a=sync 依身分套用選單（欄位 k 是密鑰、id 是名冊頁面 ID）
- 會員_LINE事件.blueprint.json：「AI學院｜會員：LINE 事件」加好友就建一筆非會員；封鎖時標記
- 會員_建立圖文選單.blueprint.json：「AI學院｜會員：建立圖文選單（手動執行）」訪客選單設為預設、會員選單設別名 member，
    清掉舊選單後把所有會員重新綁到新的會員選單

身分與選單：非會員、審核中、停權 → 訪客選單（預設，不綁個人）；一般會員、高級會員 → 會員選單（別名 member，綁個人）。
所有換選單的動作最後都把「目前選單」「選單同步時間」寫回 Notion，打開會員頁面時發現對不上就自動校正。
核准時身分一律改成一般會員，到期日依方案算（月繳一個月、年繳一年）；高級會員由管理者在 Notion 手動改，再點「套用身分」。

先在 Make 建好 Notion、LINE 兩個連線和兩個 webhook，把編號填進 tools/config.local.json，再執行：
    python3 tools/make_blueprints.py
產生的藍圖含連線編號，所以匯入 Make 時不用一個一個模組重選連線。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tools" / ("config.example.json" if "--example" in sys.argv else "config.local.json")).read_text(encoding="utf-8"))
MK, LN = CFG["make"], CFG["line"]
CONN_NOTION, CONN_LINE = MK["notion_connection_id"], MK["line_connection_id"]
DS = CFG["notion"]["data_source_id"]
KEY = CFG["approve_key"]
CHANNEL = LN["login_channel_id"]
MEMBER_LIFF = f"https://liff.line.me/{LN['liff_id']}"
ORIGIN = CFG.get("page_origin") or "*"
REPO = CFG.get("repo", "phil-ai-academy")
# 情境名稱前面加專案名，例如「AI學院｜會員 API」（另外在 Make 用同名資料夾和標籤分類）
PREFIX = f"{CFG['project']}｜" if CFG.get("project") else ""
ALIAS = "member"
# 選單是上下兩列、每列三欄（2500 × 1686）
COLS, ROW = [0, 833, 1667, 2500], 843
MEMBER_TIERS = ("一般會員", "高級會員")
# 身分 → 頁面上的狀態代號（liff/member/app.js 的 BADGE）
STATE = '{{switch(%s; "審核中"; "pending"; "一般會員"; "member"; "高級會員"; "premium"; "停權"; "banned"; "guest")}}'
# 申請表單欄位：頁面代號、Notion 欄位、型別、長度上限（和 liff/member/app.js 的 FIELDS 對應）
APPLY_FIELDS = [("name", "姓名", "title", 60), ("phone", "電話", "phone_number", 40), ("email", "Email", "email", 120),
                ("note", "備註", "rich_text", 1000)]
# 方案只接受這兩個值，其他一律當成月繳（頁面送來的值不直接寫進 Notion）
PLAN = '{{if(1.plan = "全年 3600"; "全年 3600"; "首月 699")}}'
AMOUNT = '{{if(1.plan = "全年 3600"; 3600; 699)}}'

# HTTP「Make a request」模組的必填設定。用 API 建立時不會自動帶入，少了會報 BundleValidationError（苗栗踩過）
HTTP_DEFAULTS = {"rejectUnauthorized": True, "followRedirect": True, "followAllRedirects": False, "useQuerystring": False,
                 "gzip": True, "useMtls": False}
LINE_META = [{"name": "__IMTCONN__", "type": "account:line2", "label": "Connection", "required": True}]
NOTION_META = [{"name": "__IMTCONN__", "type": "account:notion2,notion3", "label": "Connection", "required": True}]


def c(a, o, b=None):
    d = {"a": a, "o": o}
    if b is not None:
        d["b"] = b
    return d


def flt(name, groups):
    return {"name": name, "conditions": groups}


def sp(mod, prop, suffix=""):
    return "{{" + f"{mod}.properties_value.`{prop}`{suffix}" + "}}"


def cut(field, n):
    """頁面送來的文字限制長度（Notion 文字欄位上限 2000 字，也避免被灌大量內容）"""
    return "{{substring(" + field + "; 0; " + str(n) + ")}}"


def fv(k, typ, v):
    return {"key": k, "type": typ, "value": v}


def date(k, start, time=False):
    return {"key": k, "type": "date", "date": {"start": start, "includeTime": time}}


def now(k):
    return date(k, "{{now}}", True)


def enc(expr):
    """自由文字放進回應 JSON 前先 URL 編碼，頁面收到後解碼（Make 沒有 JSON 跳脫函式）"""
    return "{{encodeURL(" + expr[2:-2] + ")}}"


def is_member(ident, *extra):
    """身分是一般會員或高級會員（OR 條件組）"""
    return [[*extra, c(ident, "text:equal", t)] for t in MEMBER_TIERS]


def not_member(ident):
    return [c(ident, "text:notequal", t) for t in MEMBER_TIERS]


def webhook(hook, name):
    return {"id": 1, "module": "gateway:CustomWebHook", "version": 1, "parameters": {"hook": hook, "maxResults": 1},
            "mapper": {}, "metadata": {"designer": {"x": -300, "y": 0, "name": name}, "parameters": [
                {"name": "hook", "type": "hook:gateway-webhook", "label": "Webhook", "required": True},
                {"name": "maxResults", "type": "number", "label": "Maximum number of results"}]}}


def blueprint(name, flow):
    return {"name": name, "flow": flow, "metadata": {
        "instant": True, "version": 1, "designer": {"orphans": []},
        "scenario": {"dlq": True, "slots": None, "dataloss": False, "maxErrors": 3, "autoCommit": True,
                     "roundtrips": 1, "sequential": False, "confidential": False,
                     "freshVariables": False, "autoCommitTriggerLast": True}}}


class B:
    """藍圖組裝器：依序配發模組編號和畫布座標。"""

    def __init__(self, start=100):
        self.next_id = start
        self.y = 0

    def nid(self):
        self.next_id += 1
        return self.next_id

    def meta(self, name, params=None):
        self.y += 150
        m = {"designer": {"x": 900, "y": self.y, "name": name}}
        if params:
            m["parameters"] = params
        return m

    def ignore(self):
        return {"id": self.nid(), "module": "builtin:Ignore", "version": 1, "mapper": None,
                "metadata": {"designer": {"x": 1200, "y": self.y}}}

    def respond(self, name, body, status="200", html=False):
        ctype = "text/html; charset=utf-8" if html else "application/json; charset=utf-8"
        headers = [{"key": "Content-Type", "value": ctype}]
        if not html:
            headers.append({"key": "Access-Control-Allow-Origin", "value": ORIGIN})
        return {"id": self.nid(), "module": "gateway:WebhookRespond", "version": 1, "parameters": {},
                "mapper": {"status": status, "body": body, "headers": headers}, "metadata": self.meta(name)}

    def notion(self, module, name, mapper, onerror=None):
        d = {"id": self.nid(), "module": f"notion:{module}", "version": 1, "mapper": mapper,
             "metadata": self.meta(name, NOTION_META), "parameters": {"__IMTCONN__": CONN_NOTION}}
        if onerror:
            d["onerror"] = onerror
        return d

    def find_member(self, name, uid):
        return self.notion("searchObjects1", name, {"limit": "1", "select": "data_source_item", "data_source": DS,
                                                     "filter": [[c("LINE User ID |&*^%$#@| rich_text", "text:equals", uid)]]})

    def get(self, name, page, onerror=None):
        return self.notion("getADatabaseItem", name, {"page": page, "getBy": "data_source", "select": "map"}, onerror)

    def create(self, name, fields):
        return self.notion("createDataSourceItem", name, {"fields": fields, "select": "map", "data_source": DS})

    def update(self, name, page, fields):
        return self.notion("updateADatabaseItem", name,
                           {"page": page, "fields": fields, "select": "map", "updateBy": "data_source", "data_source": DS})

    def line(self, name, url, method="GET", body=None, onerror=None):
        mapper = {"url": url, "method": method, "headers": []}
        if body is not None:
            mapper["body"] = json.dumps(body)
            mapper["headers"] = [{"key": "Content-Type", "value": "application/json"}]
        d = {"id": self.nid(), "module": "line:makeApiCall", "version": 1, "parameters": {"__IMTCONN__": CONN_LINE},
             "mapper": mapper, "metadata": self.meta(name, LINE_META)}
        if onerror:
            d["onerror"] = onerror
        return d

    def router(self, name, routes):
        mid = self.nid()
        rs = []
        for f, mods in routes:
            mods = [dict(m) for m in mods]
            mods[0]["filter"] = f
            rs.append({"flow": mods})
        self.y += 150
        return {"id": mid, "module": "builtin:BasicRouter", "version": 1, "mapper": None,
                "metadata": {"designer": {"x": 600, "y": self.y, "name": name}}, "routes": rs}


def html(title, text):
    return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<body style="font-family:system-ui,sans-serif;max-width:520px;margin:40px auto;padding:0 20px;line-height:1.6">'
            f"<h2>{title}</h2><p>{text}</p><p style=\"color:#888\">可以關閉這個分頁，回到 Notion。</p></body>")


def link_member(b, uid, page, label, onfail_html=False):
    """綁定會員選單：先用別名取得選單編號，再綁給這個人；成功後把「目前選單」寫回 Notion。"""
    fail = [b.respond(f"回傳換選單失敗（{label}）", html("⚠ 選單沒有換成功", "LINE 上找不到會員選單。請先在 Make 執行「建立圖文選單」，再點一次「套用身分」。"), "500", True), b.ignore()] \
        if onfail_html else [b.ignore()]
    alias = b.line(f"取得會員選單編號（{label}）", f"/v2/bot/richmenu/alias/{ALIAS}", onerror=fail)
    return [alias,
            b.line(f"綁定會員選單（{label}）", f"/v2/bot/user/{uid}/richmenu/{{{{{alias['id']}.body.richMenuId}}}}", "POST"),
            b.update(f"記下目前選單：會員（{label}）", page, [fv("目前選單", "select", "會員"), now("選單同步時間")])]


def unlink(b, uid, page, label):
    """解除個人綁定，回到預設的訪客選單（本來就沒有綁定時 LINE 會回錯誤，略過）"""
    return [b.update(f"記下目前選單：訪客（{label}）", page, [fv("目前選單", "select", "訪客"), now("選單同步時間")]),
            b.line(f"解除會員選單（{label}）", f"/v2/bot/user/{uid}/richmenu", "DELETE", onerror=[b.ignore()])]


def build_api():
    b = B()
    respond_json = lambda name, body, status="200": b.respond(name, body, status)

    # ==== Notion 核准連結：GET ?a=approve|sync&k=密鑰&id=名冊頁面 ====
    def admin_flow(action):
        g = b.get(f"讀名冊（{action}）", "{{1.id}}",
                  onerror=[b.respond(f"回傳找不到（{action}）", html("⚠ 找不到這筆名冊", "連結可能不完整，請從 Notion 重新點一次。"), "404", True), b.ignore()])
        G = g["id"]
        ident, name, uid, page = sp(G, "身分", ".name"), sp(G, "姓名", "[].plain_text"), sp(G, "LINE User ID", "[].plain_text"), f"{{{{{G}.id}}}}"
        plan = sp(G, "方案", ".name")
        no_line = (flt(f"沒有 LINE 帳號（{action}）", [[c(uid, "notexist")]]), [
            b.respond(f"回傳沒有 LINE（{action}）", html("⚠ 這筆沒有 LINE 帳號", "這位不是從 LINE 加入的，無法換選單。"), "400", True)])
        if action == "approve":
            # 到期日從核准當天起算：年繳一年，其他（首月、續月）一個月
            expiry = "{{formatDate(if(" + plan[2:-2] + ' = "全年 3600"; addYears(now; 1); addMonths(now; 1)); "YYYY-MM-DD")}}'
            return [g, b.router("可否核准", [
                (flt("審核中，核准", [[c(ident, "text:equal", "審核中"), c(uid, "exist")]]), [
                    b.update("改成一般會員", page, [fv("身分", "select", "一般會員"), now("核准時間"), date("到期日", expiry)]),
                    *link_member(b, uid, page, "核准", onfail_html=True),
                    b.respond("回傳已核准", html(f"✅ 已核准 {name}", f"身分已改成一般會員（{plan}，到期日 {expiry}），LINE 選單已換成會員版。"), "200", True)]),
                (flt("不是審核中", [[c(ident, "text:notequal", "審核中"), c(uid, "exist")]]), [
                    b.respond("回傳不需核准", html("ℹ️ 不需要核准", f"{name} 目前的身分是「{ident}」。"), "200", True)]),
                no_line])]
        return [g, b.router("依身分套用選單", [
            (flt("會員：會員選單", is_member(ident, c(uid, "exist"))), [
                *link_member(b, uid, page, "套用", onfail_html=True),
                b.respond("回傳已套用會員選單", html(f"✅ {name}：會員選單", f"身分是「{ident}」，LINE 選單已換成會員版。"), "200", True)]),
            (flt("其他身分：訪客選單", [[*not_member(ident), c(uid, "exist")]]), [
                b.respond("回傳已套用訪客選單", html(f"✅ {name}：訪客選單", f"身分是「{ident}」，LINE 選單已換回訪客版。"), "200", True),
                *unlink(b, uid, page, "套用")]),
            no_line])]

    # ==== LIFF：先驗證 Access Token（屬於本系統的 LINE Login channel）再取得使用者編號 ====
    def line_get(mid, url, name, headers=()):
        return {"id": mid, "module": "http:ActionSendData", "version": 3, "parameters": {"handleErrors": False},
                "mapper": {"url": url, "method": "get", "serializeUrl": False, "shareCookies": False,
                           "parseResponse": True, "headers": list(headers), "qs": [], **HTTP_DEFAULTS},
                "metadata": {"designer": {"x": 0 if mid == 2 else 150, "y": 0 if mid == 2 else 150, "name": name}},
                "onerror": [respond_json(f"回傳驗證失敗（{name}）", '{"ok":false,"error":"auth"}', "401"), b.ignore()]}
    verify = line_get(2, "https://api.line.me/oauth2/v2.1/verify?access_token={{encodeURL(1.t)}}", "向 LINE 驗證 Access Token")
    profile = line_get(4, "https://api.line.me/v2/profile", "向 LINE 取得使用者編號", [{"name": "Authorization", "value": "Bearer {{1.t}}"}])
    UID, DISPLAY = "{{4.data.userId}}", "{{4.data.displayName}}"
    w = b.find_member("找我的名冊", UID)
    W = w["id"]
    w_ident, w_menu, w_page = sp(W, "身分", ".name"), sp(W, "目前選單", ".name"), f"{{{{{W}.id}}}}"
    exist, none = c(f"{{{{{W}.id}}}}", "exist"), c(f"{{{{{W}.id}}}}", "notexist")

    def body(state, src, extra):
        """回應頁面的會員資料。src(k) 給出申請欄位的 Make 運算式（自由文字要編碼）；extra 是方案、匯款、到期日（固定格式，不編碼）"""
        parts = ['"ok":true', f'"state":"{state}"', f'"line":"{{{{encodeURL({DISPLAY[2:-2]})}}}}"']
        parts += [f'"{k}":"{enc(src(k)) if src(k) else ""}"' for k, *_ in APPLY_FIELDS]
        parts += [f'"{k}":"{v}"' for k, v in extra.items()]
        return "{" + ",".join(parts) + "}"
    from_w = lambda k: sp(W, dict((a, n) for a, n, *_ in APPLY_FIELDS)[k], "" if k in ("phone", "email") else "[].plain_text")
    w_extra = {"plan": sp(W, "方案", ".name"), "pay5": sp(W, "匯款末五碼", "[].plain_text"),
               "paydate": sp(W, "匯款日期", ".start"), "expiry": sp(W, "到期日", ".start")}
    w_state = STATE % w_ident[2:-2]
    # 非會員的姓名是「（LINE）顯示名稱」，不是本名，不回給頁面
    me_body = body(w_state, lambda k: ('{{if(' + w_ident[2:-2] + ' = "非會員"; ""; ' + from_w(k)[2:-2] + ')}}') if k == "name" else from_w(k), w_extra)

    me_flow = [b.router("我的身分（順便校正選單）", [
        (flt("還沒有名冊", [[none]]), [
            b.create("新增非會員（頁面）", [fv("姓名", "title", "（LINE）" + DISPLAY), fv("身分", "select", "非會員"),
                                       fv("LINE 顯示名稱", "rich_text", DISPLAY), fv("LINE User ID", "rich_text", UID),
                                       fv("目前選單", "select", "訪客")]),
            respond_json("回傳非會員", body("guest", lambda k: "", {k: "" for k in w_extra}))]),
        # 先回應頁面再換選單：換選單出錯也不會讓頁面卡住
        (flt("會員但選單不是會員", is_member(w_ident, exist, c(w_menu, "text:notequal", "會員"))), [
            respond_json("回傳我的身分（校正成會員選單）", me_body), *link_member(b, UID, w_page, "校正")]),
        (flt("不是會員但選單是會員", [[exist, *not_member(w_ident), c(w_menu, "text:equal", "會員")]]), [
            respond_json("回傳我的身分（校正成訪客選單）", me_body), *unlink(b, UID, w_page, "校正")]),
        (flt("選單正確", is_member(w_ident, exist, c(w_menu, "text:equal", "會員"))
             + [[exist, *not_member(w_ident), c(w_menu, "text:notequal", "會員")]]), [
            respond_json("回傳我的身分", me_body)]),
    ])]

    apply_fields = [fv(n, t, cut(f"1.{k}", ln)) for k, n, t, ln in APPLY_FIELDS]
    apply_fields += [fv("方案", "select", PLAN), fv("應繳金額", "number", AMOUNT), fv("匯款末五碼", "rich_text", cut("1.pay5", 5)),
                     date("匯款日期", "{{1.paydate}}"), fv("身分", "select", "審核中"), now("申請時間"),
                     fv("LINE 顯示名稱", "rich_text", DISPLAY)]
    pending_body = body("pending", lambda k: f"{{{{1.{k}}}}}",
                        {"plan": PLAN, "pay5": "{{substring(1.pay5; 0; 5)}}", "paydate": "{{substring(1.paydate; 0; 10)}}", "expiry": ""})
    apply_flow = [b.router("申請入會", [
        (flt("新申請（還沒有名冊）", [[none]]), [
            b.create("新增名冊（審核中）", apply_fields + [fv("LINE User ID", "rich_text", UID), fv("目前選單", "select", "訪客")]),
            respond_json("回傳審核中（新）", pending_body)]),
        (flt("非會員或審核中：更新申請", [[exist, c(w_ident, "text:equal", "非會員")], [exist, c(w_ident, "text:equal", "審核中")]]), [
            b.update("更新申請資料（審核中）", w_page, apply_fields), respond_json("回傳審核中", pending_body)]),
        (flt("已是會員或停權", [[exist, c(w_ident, "text:notequal", "非會員"), c(w_ident, "text:notequal", "審核中")]]), [
            respond_json("回傳目前身分（申請）", me_body)]),
    ])]

    act = lambda a: c("{{1.a}}", "text:equal", a)
    PAGE_ACTS = ("me", "apply")
    key_ok = c("{{1.k}}", "text:equal", KEY)
    flow = [
        webhook(MK["api_hook_id"], "會員頁面與核准連結送來的請求"),
        b.router("請求種類", [
            (flt("核准連結：核准", [[act("approve"), key_ok, c("{{1.id}}", "exist")]]), admin_flow("approve")),
            (flt("核准連結：套用身分", [[act("sync"), key_ok, c("{{1.id}}", "exist")]]), admin_flow("sync")),
            (flt("核准連結：密鑰不對", [[act("approve"), c("{{1.k}}", "text:notequal", KEY)], [act("sync"), c("{{1.k}}", "text:notequal", KEY)]]), [
                b.respond("回傳密鑰不對", html("⛔ 連結無效", "請從 Notion 會員名冊重新點連結。"), "403", True)]),
            (flt("會員頁面", [[c("{{1.t}}", "exist"), act(a)] for a in PAGE_ACTS]), [
                verify,
                b.router("身分驗證", [
                    (flt("不是本系統的憑證", [[c("{{2.data.client_id}}", "text:notequal", CHANNEL)]]), [
                        respond_json("回傳驗證失敗", '{"ok":false,"error":"auth"}', "401")]),
                    (flt("身分驗證成功", [[c("{{2.data.client_id}}", "text:equal", CHANNEL)]]), [profile, w, b.router("依動作分流", [
                        (flt("我的身分", [[act("me")]]), me_flow),
                        (flt("申請入會", [[act("apply")]]), apply_flow),
                    ])]),
                ])]),
            (flt("格式不對", [[c("{{1.a}}", "notexist")],
                              [c("{{1.a}}", "text:notequal", a) for a in ("approve", "sync") + PAGE_ACTS],
                              *[[act(a), c("{{1.t}}", "notexist")] for a in PAGE_ACTS]]), [
                respond_json("回傳格式不對", '{"ok":false,"error":"bad_request"}', "400")]),
        ]),
    ]
    return blueprint(PREFIX + "會員 API", flow)


def build_events():
    """LINE 事件：加好友（follow）就在名冊建一筆非會員；封鎖（unfollow）時標記。只處理每次送來的第一個事件。"""
    b = B()
    uid, typ = "{{1.events[1].source.userId}}", "{{1.events[1].type}}"
    w = b.find_member("找名冊", uid)
    w["filter"] = flt("只處理加好友、封鎖", [[c(typ, "text:equal", "follow")], [c(typ, "text:equal", "unfollow")]])
    W = w["id"]
    exist, none = c(f"{{{{{W}.id}}}}", "exist"), c(f"{{{{{W}.id}}}}", "notexist")
    prof = b.line("取得 LINE 名稱", f"/v2/bot/profile/{uid}")
    flow = [
        {"id": 1, "module": "line:watchMessages", "version": 1, "mapper": {},
         "metadata": {"designer": {"x": -300, "y": 0, "name": "LINE 事件"},
                      "parameters": [{"name": "__IMTHOOK__", "type": "hook:line", "label": "Webhook", "required": True}]},
         "parameters": {"__IMTHOOK__": MK["events_hook_id"]}},
        w,
        b.router("依事件分流", [
            (flt("新好友", [[c(typ, "text:equal", "follow"), none]]), [
                prof,
                b.create("新增非會員", [fv("姓名", "title", f"（LINE）{{{{{prof['id']}.body.displayName}}}}"),
                                     fv("身分", "select", "非會員"), fv("好友狀態", "select", "好友中"),
                                     fv("LINE 顯示名稱", "rich_text", f"{{{{{prof['id']}.body.displayName}}}}"),
                                     fv("LINE User ID", "rich_text", uid), fv("目前選單", "select", "訪客"), now("加入好友時間")])]),
            (flt("重新加好友", [[c(typ, "text:equal", "follow"), exist]]), [
                b.update("改回好友中", f"{{{{{W}.id}}}}", [fv("好友狀態", "select", "好友中")])]),
            (flt("封鎖", [[c(typ, "text:equal", "unfollow"), exist]]), [
                b.update("標記已封鎖", f"{{{{{W}.id}}}}", [fv("好友狀態", "select", "已封鎖")])]),
        ]),
    ]
    return blueprint(PREFIX + "會員：LINE 事件", flow)


def build_menu():
    """建立訪客選單（設為所有人的預設）和會員選單（別名 member）；清掉其他舊選單；把所有會員重新綁到新的會員選單。
    圖片從 GitHub Pages 下載（assets/richmenu_guest.png、richmenu_member.png），LINE 規定 2500×1686、1MB 以內。
    選單內容還沒定案，先放：上列 課程｜AI 小幫手｜關於學院，下列 訪客是「申請加入」、會員是「會員專區」。"""
    b = B(10)
    uri = lambda u: {"type": "uri", "uri": u}

    def area(col, row, url, span=1):
        x = COLS[col]
        return {"bounds": {"x": x, "y": row * ROW, "width": COLS[col + span] - x, "height": ROW}, "action": uri(url)}
    top = [area(0, 0, MEMBER_LIFF + "?v=courses"), area(1, 0, MEMBER_LIFF + "?v=ai"), area(2, 0, MEMBER_LIFF + "?v=about")]
    guest_areas = top + [area(0, 1, MEMBER_LIFF, span=3)]     # 下列一整格：申請加入
    member_areas = top + [area(0, 1, MEMBER_LIFF, span=3)]    # 下列一整格：會員專區

    def make(name, img, areas, label):
        g = {"id": b.nid(), "module": "http:ActionGetFile", "version": 3, "parameters": {"handleErrors": False},
             "mapper": {"url": f"{ORIGIN}/{REPO}/assets/{img}", "method": "get", "serializeUrl": False, "shareCookies": False},
             "metadata": b.meta(f"下載{label}圖片")}
        m = {"id": b.nid(), "module": "line:createARichMenu", "version": 1, "parameters": {"__IMTCONN__": CONN_LINE},
             "mapper": {"name": name, "chatBarText": "選單", "selected": True, "height": 2 * ROW, "areas": areas,
                        "data": f"{{{{{g['id']}.data}}}}", "filename": img},
             "metadata": b.meta(f"建立{label}", LINE_META)}
        return g, m

    gg, gm = make("guest", "richmenu_guest.png", guest_areas, "訪客選單")
    mg, mm = make("member", "richmenu_member.png", member_areas, "會員選單")
    G, Mm = gm["id"], mm["id"]
    lst = b.line("列出所有圖文選單", "/v2/bot/richmenu/list")
    feed = {"id": b.nid(), "module": "builtin:BasicFeeder", "version": 1, "mapper": {"array": f"{{{{{lst['id']}.body.richmenus}}}}"},
            "metadata": b.meta("逐張檢查")}
    F = feed["id"]
    members = b.notion("searchObjects1", "找所有會員", {"limit": "1000", "select": "data_source_item", "data_source": DS,
                                                    "filter": [[c("身分 |&*^%$#@| select", "select:equals", t)] for t in MEMBER_TIERS]})
    MB = members["id"]
    # 預設選單一定要在兩張都建好之後才設：Make 的「Create a Rich Menu」勾了 selected（Set the Rich Menu by Default）
    # 會把剛建好的那張設成預設，朕宏 2026-10-21 會員選單因此蓋過訪客選單，所有好友都看到會員選單
    flow = [gg, gm, mg, mm,
            b.line("設為所有人的預設選單（訪客）", f"/v2/bot/user/all/richmenu/{{{{{G}.richMenuId}}}}", "POST"),
            b.router("設定會員選單別名", [
                # 已有別名時更新成功、新建失敗；第一次部署時相反，各自出錯就略過
                (flt("更新別名", [[c(f"{{{{{Mm}.richMenuId}}}}", "exist")]]), [
                    b.line(f"更新別名 {ALIAS}", f"/v2/bot/richmenu/alias/{ALIAS}", "POST", {"richMenuId": f"{{{{{Mm}.richMenuId}}}}"}, onerror=[b.ignore()])]),
                (flt("新建別名", [[c(f"{{{{{Mm}.richMenuId}}}}", "exist")]]), [
                    b.line(f"新建別名 {ALIAS}", "/v2/bot/richmenu/alias", "POST",
                           {"richMenuAliasId": ALIAS, "richMenuId": f"{{{{{Mm}.richMenuId}}}}"}, onerror=[b.ignore()])]),
            ]),
            b.router("收尾", [
                # 刪除舊選單時，LINE 會自動解除所有人身上的舊綁定（苗栗 10/14 舊選單卡住的教訓）
                (flt("清掉舊選單", [[c(f"{{{{{Mm}.richMenuId}}}}", "exist")]]), [
                    lst, feed,
                    b.line("刪除舊選單", f"/v2/bot/richmenu/{{{{{F}.richMenuId}}}}", "DELETE", onerror=[b.ignore()])]),
                (flt("會員重新綁定", [[c(f"{{{{{Mm}.richMenuId}}}}", "exist")]]), [
                    members,
                    b.line("綁定新的會員選單", "/v2/bot/user/" + sp(MB, "LINE User ID", "[].plain_text") + f"/richmenu/{{{{{Mm}.richMenuId}}}}",
                           "POST", onerror=[b.ignore()]),
                    b.update("記下目前選單：會員（重建）", f"{{{{{MB}.id}}}}", [fv("目前選單", "select", "會員"), now("選單同步時間")])]),
            ])]
    # 刪除舊選單要排除剛建好的兩張
    flow[-1]["routes"][0]["flow"][2]["filter"] = flt("不是新的兩張", [[
        c(f"{{{{{F}.richMenuId}}}}", "text:notequal", f"{{{{{G}.richMenuId}}}}"),
        c(f"{{{{{F}.richMenuId}}}}", "text:notequal", f"{{{{{Mm}.richMenuId}}}}")]])
    bp = blueprint(PREFIX + "會員：建立圖文選單（手動執行）", flow)
    bp["metadata"]["instant"] = False
    return bp


def main():
    out = ROOT / "make" / ("example" if "--example" in sys.argv else "")
    out.mkdir(parents=True, exist_ok=True)
    for fname, bp in (("會員_API.blueprint.json", build_api()), ("會員_LINE事件.blueprint.json", build_events()),
                      ("會員_建立圖文選單.blueprint.json", build_menu())):
        p = out / fname
        p.write_text(json.dumps(bp, ensure_ascii=False, indent=1), encoding="utf-8")
        print(p.relative_to(ROOT), p.stat().st_size)


if __name__ == "__main__":
    main()
