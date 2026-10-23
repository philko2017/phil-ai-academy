"""會員通（LINE Member Kit）：產生會員模組的 Make 藍圖，輸出到 make/（最早改寫自 philko2017/line-namecard 的 tools/make_member_blueprint.py）。
情境名稱前綴、Notion 編號、LINE 編號都從 tools/config.local.json 讀，換客戶不用改這支程式。

- 會員_API.blueprint.json：「{專案}｜會員 API」（欄位 t 是 LINE Access Token）
    a=me 我的身分＋前台設定＋方案＋是否管理者（順便校正選單）｜a=apply 申請入會＋匯款回報｜a=profile 會員自己改基本資料
    a=news 最新消息（非會員只看公開）｜a=courses 內容庫列表（不含內容連結）｜a=course_open 依身分給內容連結
    a=admin_list 名冊｜a=admin_set 核准、升級高級會員、停權、恢復（只有名冊「角色」勾管理者的人能用）
    頁面上的文字、圖片、方案、收款帳戶都從 Notion「前台設定」「方案」讀，repo 裡不放。
    Notion 核准連結：a=approve 核准入會｜a=sync 依身分套用選單（欄位 k 是密鑰、id 是名冊頁面 ID）
- 會員_LINE事件.blueprint.json：「{專案}｜會員：LINE 事件」加好友就建一筆非會員；封鎖時標記
- 會員_建立圖文選單.blueprint.json：「{專案}｜會員：建立圖文選單（手動執行）」圖片讀 Notion「前台設定」的三個選單圖；
    訪客選單設為預設、會員選單設別名 member、管理者選單設別名 admin，清掉舊選單後把會員、管理者重新綁到新選單

身分與選單：名冊「角色」勾管理者 → 管理者選單（別名 admin）；一般會員、高級會員 → 會員選單（別名 member）；
非會員、審核中、已到期、停權 → 訪客選單（預設，不綁個人）。
所有換選單的動作最後都把「目前選單」「選單同步時間」寫回 Notion，打開會員頁面時發現對不上就自動校正。
核准時身分一律改成一般會員，到期日依方案算（月繳一個月、年繳一年）；升級、停權、恢復可在會員頁面「管理會員」做，
也可以在 Notion 手動改身分，再點「套用身分」。

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
# 前台設定（一列）與方案：會員頁面上的文字、收款帳戶、價格都從這兩張 Notion 表讀，repo 裡不放
SETTINGS_PAGE = CFG["notion"]["settings_page_id"]
PLANS_DS = CFG["notion"]["plans_data_source_id"]
NEWS_DS = CFG["notion"]["news_data_source_id"]          # 最新消息
CONTENT_DS = CFG["notion"]["content_data_source_id"]    # 內容庫（課程、數位產品）
# 內容庫列表回傳的欄位（Notion 欄位 ID）：除了「內容連結」都要，連結只在點開時依身分給
CONTENT_LIST_PROPS = CFG["notion"]["content_list_property_ids"]
NOTION_VERSION = "2025-09-03"   # 查詢 data source（/v1/data_sources/…/query）要這個版本
KEY = CFG["approve_key"]
CHANNEL = LN["login_channel_id"]
MEMBER_LIFF = f"https://liff.line.me/{LN['liff_id']}"
ORIGIN = CFG.get("page_origin") or "*"
REPO = CFG.get("repo", "phil-ai-academy")
# 情境名稱前面加專案名，例如「{專案}｜會員 API」（另外在 Make 用同名資料夾和標籤分類）
PREFIX = f"{CFG['project']}｜" if CFG.get("project") else ""
ALIAS, ALIAS_ADMIN = "member", "admin"   # 會員選單、管理者選單的別名；訪客選單是所有人的預設
# 選單是上下兩列、每列三欄（2500 × 1686）
COLS, ROW = [0, 833, 1667, 2500], 843
MEMBER_TIERS = ("一般會員", "高級會員")
# 身分 → 頁面上的狀態代號（liff/member/app.js 的 BADGE）
STATE = '{{switch(%s; "審核中"; "pending"; "一般會員"; "member"; "高級會員"; "premium"; "已到期"; "expired"; "停權"; "banned"; "guest")}}'
# 申請表單欄位：頁面代號、Notion 欄位、型別、長度上限（和 liff/member/app.js 的 FIELDS 對應）
APPLY_FIELDS = [("name", "姓名", "title", 60), ("phone", "電話", "phone_number", 40), ("email", "Email", "email", 120),
                ("note", "備註", "rich_text", 1000)]
# 會員可以自己改的欄位（寫入限制：身分、方案、到期日等都不能改）
PROFILE_FIELDS = APPLY_FIELDS
# 頁面送來的方案名稱拿去「方案」表找，找不到就不收（價格、會籍長度一律以 Notion 為準）。
# 名稱會放進送給 Notion 的 JSON，含引號或反斜線的直接拒收（Make 的公式不支援正規表示式的 [ ]，不能用 replace 清掉）
PLAN_IN = "{{substring(1.plan; 0; 40)}}"
PLANS_QUERY = '{"filter":{"and":[{"property":"上架","checkbox":{"equals":true}}]},"sorts":[{"property":"排序","direction":"ascending"}]}'


def plan_query(name_expr):
    return ('{"filter":{"and":[{"property":"名稱","title":{"equals":"' + name_expr + '"}},'
            '{"property":"上架","checkbox":{"equals":true}}]}}')


def np(mod, prop, path):
    """讀 Notion API 回傳的第一筆結果的欄位，例如 np(P, "價格", "number")"""
    return "{{" + f"{mod}.body.results[1].properties.`{prop}`.{path}" + "}}"

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

    def notion_api(self, name, url, method="GET", body=None, onerror=None):
        mapper = {"url": url, "version": NOTION_VERSION, "method": method,
                  "headers": [{"key": "Content-Type", "value": "application/json"}], "qs": []}
        if body is not None:
            mapper["body"] = body
        return self.notion("makeApiCall", name, mapper, onerror)

    def to_json(self, name, obj):
        return {"id": self.nid(), "module": "json:TransformToJSON", "version": 1, "parameters": {"space": ""},
                "mapper": {"object": obj}, "metadata": self.meta(name)}

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


def admin_of(mod):
    """名冊的「角色」有沒有勾「管理者」（Notion 模組輸出）→ "Y" / "N\""""
    return "{{if(contains(map(" + f"{mod}.properties_value.`角色`" + '; "name"); "管理者"); "Y"; "N")}}'


def want_menu(admin, ident):
    """這個人應該看到的選單：管理者 → 管理者；一般會員、高級會員 → 會員；其他 → 訪客"""
    i = ident[2:-2]
    return ("{{if(" + admin[2:-2] + ' = "Y"; "管理者"; if(' + i + ' = "一般會員"; "會員"; if(' + i
            + ' = "高級會員"; "會員"; "訪客")))}}')


def link_menu(b, uid, page, label, alias, menu):
    """綁定個人選單：先用別名取得選單編號，再綁給這個人；成功後把「目前選單」寫回 Notion。別名不存在就略過（先執行建立圖文選單）"""
    a = b.line(f"取得{menu}選單編號（{label}）", f"/v2/bot/richmenu/alias/{alias}", onerror=[b.ignore()])
    return [a,
            b.line(f"綁定{menu}選單（{label}）", f"/v2/bot/user/{uid}/richmenu/{{{{{a['id']}.body.richMenuId}}}}", "POST", onerror=[b.ignore()]),
            b.update(f"記下目前選單：{menu}（{label}）", page, [fv("目前選單", "select", menu), now("選單同步時間")])]


def unlink(b, uid, page, label):
    """解除個人綁定，回到預設的訪客選單（本來就沒有綁定時 LINE 會回錯誤，略過）"""
    return [b.update(f"記下目前選單：訪客（{label}）", page, [fv("目前選單", "select", "訪客"), now("選單同步時間")]),
            b.line(f"解除個人選單（{label}）", f"/v2/bot/user/{uid}/richmenu", "DELETE", onerror=[b.ignore()])]


def apply_menu(b, uid, page, want, label):
    """依 want_menu 的結果換成三種選單之一"""
    return b.router(f"換選單（{label}）", [
        (flt(f"管理者選單（{label}）", [[c(want, "text:equal", "管理者")]]), link_menu(b, uid, page, label, ALIAS_ADMIN, "管理者")),
        (flt(f"會員選單（{label}）", [[c(want, "text:equal", "會員")]]), link_menu(b, uid, page, label, ALIAS, "會員")),
        (flt(f"訪客選單（{label}）", [[c(want, "text:equal", "訪客")]]), unlink(b, uid, page, label)),
    ])


def plan_expiry(b, plan, label, onerror):
    """到期日從今天起算，月數讀「方案」表的「會籍月數」（找不到就算一個月）"""
    pl = b.notion_api(f"讀方案的會籍月數（{label}）", f"/v1/data_sources/{PLANS_DS}/query", "POST", plan_query(plan), onerror=onerror)
    months = np(pl["id"], "會籍月數", "number")
    return pl, "{{formatDate(addMonths(now; ifempty(" + months[2:-2] + "; 1)); \"YYYY-MM-DD\")}}"


def build_api():
    b = B()
    respond_json = lambda name, body, status="200": b.respond(name, body, status)
    lit = lambda s: '{{"' + s + '"}}'   # 固定值也包成運算式，方便和 want_menu 組合

    # ==== Notion 核准連結：GET ?a=approve|sync&k=密鑰&id=名冊頁面（管理者在電腦上用）====
    def notion_link_flow(action):
        g = b.get(f"讀名冊（{action}）", "{{1.id}}",
                  onerror=[b.respond(f"回傳找不到（{action}）", html("⚠ 找不到這筆名冊", "連結可能不完整，請從 Notion 重新點一次。"), "404", True), b.ignore()])
        G = g["id"]
        ident, name, uid, page = sp(G, "身分", ".name"), sp(G, "姓名", "[].plain_text"), sp(G, "LINE User ID", "[].plain_text"), f"{{{{{G}.id}}}}"
        admin, plan = admin_of(G), sp(G, "方案", ".name")
        no_line = (flt(f"沒有 LINE 帳號（{action}）", [[c(uid, "notexist")]]), [
            b.respond(f"回傳沒有 LINE（{action}）", html("⚠ 這筆沒有 LINE 帳號", "這位不是從 LINE 加入的，無法換選單。"), "400", True)])
        if action == "approve":
            pl, expiry = plan_expiry(b, plan, "核准連結", [b.respond("回傳讀不到方案", html("⚠ 讀不到方案", "請確認 Notion「方案」表有開放給 Make，再點一次核准。"), "500", True), b.ignore()])
            return [g, b.router("可否核准", [
                (flt("審核中，核准", [[c(ident, "text:equal", "審核中"), c(uid, "exist")]]), [
                    pl,
                    b.update("改成一般會員", page, [fv("身分", "select", "一般會員"), now("核准時間"), date("到期日", expiry)]),
                    b.respond("回傳已核准", html(f"✅ 已核准 {name}", f"身分已改成一般會員（{plan}，到期日 {expiry}），LINE 選單正在更新。"), "200", True),
                    apply_menu(b, uid, page, want_menu(admin, lit("一般會員")), "核准連結")]),
                (flt("不是審核中", [[c(ident, "text:notequal", "審核中"), c(uid, "exist")]]), [
                    b.respond("回傳不需核准", html("ℹ️ 不需要核准", f"{name} 目前的身分是「{ident}」。"), "200", True)]),
                no_line])]
        return [g, b.router("可否套用", [
            (flt("有 LINE 帳號", [[c(uid, "exist")]]), [
                b.respond("回傳已套用", html(f"✅ {name}：選單更新中", f"身分是「{ident}」，LINE 選單會換成對應的版本。"), "200", True),
                apply_menu(b, uid, page, want_menu(admin, ident), "套用身分連結")]),
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
    w_admin = admin_of(W)
    exist, none = c(f"{{{{{W}.id}}}}", "exist"), c(f"{{{{{W}.id}}}}", "notexist")
    is_admin = c(w_admin, "text:equal", "Y")

    # ==== 前台設定與方案：每次打開頁面都從 Notion 讀，原樣轉成 JSON 交給頁面解析 ====
    site_api = b.notion_api("讀前台設定", f"/v1/pages/{SETTINGS_PAGE}")
    site_json = b.to_json("前台設定轉 JSON", f"{{{{{site_api['id']}.body.properties}}}}")
    plans_api = b.notion_api("讀上架的方案", f"/v1/data_sources/{PLANS_DS}/query", "POST", PLANS_QUERY)
    plans_json = b.to_json("方案轉 JSON", f"{{{{{plans_api['id']}.body.results}}}}")
    SITE = f'"site":{{{{{site_json["id"]}.json}}}},"plans":{{{{{plans_json["id"]}.json}}}}'

    def body(state, src, extra, site=False):
        """回應頁面的會員資料。src(k) 給出申請欄位的 Make 運算式（自由文字要編碼）；extra 是方案、匯款、到期日、管理者（固定格式，不編碼）"""
        parts = ['"ok":true', f'"state":"{state}"', f'"line":"{{{{encodeURL({DISPLAY[2:-2]})}}}}"']
        parts += [f'"{k}":"{enc(src(k)) if src(k) else ""}"' for k, *_ in APPLY_FIELDS]
        parts += [f'"{k}":"{v}"' for k, v in extra.items()]
        if site:
            parts.append(SITE)
        return "{" + ",".join(parts) + "}"
    from_w = lambda k: sp(W, dict((a, n) for a, n, *_ in APPLY_FIELDS)[k], "" if k in ("phone", "email") else "[].plain_text")
    w_extra = {"plan": sp(W, "方案", ".name"), "pay5": sp(W, "匯款末五碼", "[].plain_text"),
               "paydate": sp(W, "匯款日期", ".start"), "expiry": sp(W, "到期日", ".start"), "admin": w_admin}
    w_state = STATE % w_ident[2:-2]
    # 非會員的姓名是「（LINE）顯示名稱」，不是本名，不回給頁面；「給會員的話」由管理者在名冊填
    me_src = lambda k: ('{{if(' + w_ident[2:-2] + ' = "非會員"; ""; ' + from_w(k)[2:-2] + ')}}') if k == "name" else from_w(k)
    me_body = body(w_state, me_src, w_extra)
    message = '"message":"' + enc(sp(W, "給會員的話", "[].plain_text")) + '"'
    me_site_body = body(w_state, me_src, w_extra, site=True)[:-1] + "," + message + "}"
    w_want = want_menu(w_admin, w_ident)

    me_flow = [site_api, site_json, plans_api, plans_json, b.router("我的身分（順便校正選單）", [
        (flt("還沒有名冊", [[none]]), [
            b.create("新增非會員（頁面）", [fv("姓名", "title", "（LINE）" + DISPLAY), fv("身分", "select", "非會員"),
                                       fv("LINE 顯示名稱", "rich_text", DISPLAY), fv("LINE User ID", "rich_text", UID),
                                       fv("目前選單", "select", "訪客")]),
            respond_json("回傳非會員", body("guest", lambda k: "", {**{k: "" for k in w_extra}, "admin": "N"}, site=True))]),
        # 先回應頁面再換選單：換選單出錯也不會讓頁面卡住
        (flt("選單和身分對不上", [[exist, c(w_want, "text:notequal", w_menu)]]), [
            respond_json("回傳我的身分（校正選單）", me_site_body), apply_menu(b, UID, w_page, w_want, "校正")]),
        (flt("選單正確", [[exist, c(w_want, "text:equal", w_menu)]]), [respond_json("回傳我的身分", me_site_body)]),
    ])]

    # ==== 申請入會：方案到「方案」表查，名稱、價格以 Notion 為準 ====
    pl = b.notion_api("查申請的方案", f"/v1/data_sources/{PLANS_DS}/query", "POST", plan_query(PLAN_IN),
                      onerror=[respond_json("回傳查不到方案", '{"ok":false,"error":"bad_plan"}', "400"), b.ignore()])
    P = pl["id"]
    plan_name, plan_price = np(P, "名稱", "title[1].plain_text"), np(P, "價格", "number")
    has_plan = c(f"{{{{{P}.body.results[1].id}}}}", "exist")
    apply_fields = [fv(n, t, cut(f"1.{k}", ln)) for k, n, t, ln in APPLY_FIELDS]
    apply_fields += [fv("方案", "select", plan_name), fv("應繳金額", "number", plan_price), fv("匯款末五碼", "rich_text", cut("1.pay5", 5)),
                     date("匯款日期", "{{1.paydate}}"), fv("身分", "select", "審核中"), now("申請時間"),
                     fv("LINE 顯示名稱", "rich_text", DISPLAY)]
    pending_body = body("pending", lambda k: f"{{{{1.{k}}}}}",
                        {"plan": plan_name, "pay5": "{{substring(1.pay5; 0; 5)}}", "paydate": "{{substring(1.paydate; 0; 10)}}", "expiry": ""})
    apply_route = [pl, b.router("申請入會", [
        (flt("方案不存在或已下架", [[c(f"{{{{{P}.body.results[1].id}}}}", "notexist")]]), [
            respond_json("回傳方案不對", '{"ok":false,"error":"bad_plan"}', "400")]),
        (flt("新申請（還沒有名冊）", [[has_plan, none]]), [
            b.create("新增名冊（審核中）", apply_fields + [fv("LINE User ID", "rich_text", UID), fv("目前選單", "select", "訪客")]),
            respond_json("回傳審核中（新）", pending_body)]),
        # 已到期的人用同一張表續費：送出後變審核中，核准時重新寫到期日
        (flt("非會員、審核中或已到期：更新申請", [[has_plan, exist, c(w_ident, "text:equal", t)] for t in ("非會員", "審核中", "已到期")]), [
            b.update("更新申請資料（審核中）", w_page, apply_fields), respond_json("回傳審核中", pending_body)]),
        (flt("已是會員或停權", [[has_plan, exist, *[c(w_ident, "text:notequal", t) for t in ("非會員", "審核中", "已到期")]]]), [
            respond_json("回傳目前身分（申請）", me_body)]),
    ])]
    plan_safe = [[c("{{1.plan}}", "text:notcontain", '"'), c("{{1.plan}}", "text:notcontain", "\\")]]
    plan_unsafe = [[c("{{1.plan}}", "text:contain", '"')], [c("{{1.plan}}", "text:contain", "\\")]]
    apply_flow = [b.router("檢查方案名稱", [
        (flt("方案名稱有引號或反斜線", plan_unsafe), [respond_json("回傳方案不對（格式）", '{"ok":false,"error":"bad_plan"}', "400")]),
        (flt("方案名稱正常", plan_safe), apply_route),
    ])]

    # ==== 會員自己改基本資料：只寫姓名、電話、Email、備註；停權的人不能改 ====
    profile_flow = [b.router("改基本資料", [
        (flt("可以改", [[exist, c(w_ident, "text:notequal", "停權")]]), [
            b.update("更新基本資料", w_page, [fv(n, t, cut(f"1.{k}", ln)) for k, n, t, ln in PROFILE_FIELDS]),
            respond_json("回傳已更新", '{"ok":true}')]),
        (flt("不能改", [[none], [exist, c(w_ident, "text:equal", "停權")]]), [
            respond_json("回傳不能改", '{"ok":false,"error":"not_allowed"}', "403")]),
    ])]

    # ==== 最新消息：會員和管理者看全部，其他人只看「公開」 ====
    news_q = lambda public: ('{"filter":{"and":[{"property":"上架","checkbox":{"equals":true}}'
                             + (',{"property":"對象","select":{"equals":"公開"}}' if public else "")
                             + ']},"sorts":[{"property":"發布日期","direction":"descending"}],"page_size":30}')

    def news_route(label, public):
        api = b.notion_api(f"讀最新消息（{label}）", f"/v1/data_sources/{NEWS_DS}/query", "POST", news_q(public))
        js = b.to_json(f"最新消息轉 JSON（{label}）", f"{{{{{api['id']}.body.results}}}}")
        return [api, js, respond_json(f"回傳最新消息（{label}）", f'{{"ok":true,"news":{{{{{js["id"]}.json}}}}}}')]
    member_or_admin = is_member(w_ident, exist) + [[exist, is_admin]]
    news_flow = [b.router("最新消息給誰看", [
        (flt("會員或管理者：全部", member_or_admin), news_route("全部", False)),
        (flt("其他人：只有公開", [[none], [exist, *not_member(w_ident), c(w_admin, "text:notequal", "Y")]]), news_route("公開", True)),
    ])]

    # ==== 課程與數位產品：列表不帶「內容連結」，點開時才依身分給連結 ====
    courses_api = b.notion_api("讀上架的內容", f"/v1/data_sources/{CONTENT_DS}/query", "POST",
                               '{"filter":{"property":"上架狀態","select":{"equals":"上架"}},"sorts":[{"property":"排序","direction":"ascending"}],"page_size":100}')
    courses_api["mapper"]["qs"] = [{"key": "filter_properties[]", "value": pid} for pid in CONTENT_LIST_PROPS]
    courses_json = b.to_json("內容轉 JSON", f"{{{{{courses_api['id']}.body.results}}}}")
    courses_flow = [courses_api, courses_json, respond_json("回傳內容列表", f'{{"ok":true,"items":{{{{{courses_json["id"]}.json}}}}}}')]

    item = b.notion_api("讀要打開的內容", "/v1/pages/{{1.id}}",
                        onerror=[respond_json("回傳找不到內容", '{"ok":false,"error":"not_found"}', "404"), b.ignore()])
    I = item["id"]
    aud, status, parent = (f"{{{{{I}.body.properties.`開放對象`.select.name}}}}", f"{{{{{I}.body.properties.`上架狀態`.select.name}}}}",
                           f"{{{{{I}.body.parent.data_source_id}}}}")
    wi = "ifempty(" + w_ident[2:-2] + '; "非會員")'
    allow = ("{{if(" + parent[2:-2] + f' = "{CONTENT_DS}"; if(' + status[2:-2] + ' = "上架"; if(' + w_admin[2:-2] + ' = "Y"; "Y"; if('
             + aud[2:-2] + ' = "公開"; "Y"; if(' + aud[2:-2] + ' = "一般會員"; if(' + wi + ' = "一般會員"; "Y"; if(' + wi
             + ' = "高級會員"; "Y"; "N")); if(' + aud[2:-2] + ' = "高級會員"; if(' + wi + ' = "高級會員"; "Y"; "N"); "N")))); "N"); "N")}}')
    link, trial = f"{{{{{I}.body.properties.`內容連結`.url}}}}", f"{{{{{I}.body.properties.`試看連結`.url}}}}"
    open_flow = [b.router("檢查內容編號", [
        (flt("內容編號格式正確", [[c("{{1.id}}", "text:pattern", "^[0-9a-fA-F-]{32,36}$")]]), [item, b.router("可不可以看", [
            (flt("可以看", [[c(allow, "text:equal", "Y")]]), [
                respond_json("回傳內容連結", '{"ok":true,"link":"' + enc(link) + '","trial":"' + enc(trial) + '"}')]),
            (flt("不能看", [[c(allow, "text:notequal", "Y")]]), [
                respond_json("回傳上鎖", '{"ok":false,"error":"locked","trial":"' + enc(trial) + '"}', "403")]),
        ])]),
        (flt("內容編號格式不對", [[c("{{1.id}}", "text:notpattern", "^[0-9a-fA-F-]{32,36}$")]]), [
            respond_json("回傳內容編號不對", '{"ok":false,"error":"bad_request"}', "400")]),
    ])]

    # ==== 管理會員（只有名冊「角色」勾管理者的人）：列表＋核准、升級、停權、恢復 ====
    roster_api = b.notion_api("讀全部名冊", f"/v1/data_sources/{DS}/query", "POST",
                              '{"sorts":[{"timestamp":"created_time","direction":"descending"}],"page_size":100}')
    roster_json = b.to_json("名冊轉 JSON", f"{{{{{roster_api['id']}.body.results}}}}")
    admin_list_flow = [roster_api, roster_json, respond_json("回傳名冊", f'{{"ok":true,"members":{{{{{roster_json["id"]}.json}}}}}}')]

    t = b.get("讀要管理的會員", "{{1.id}}", onerror=[respond_json("回傳找不到會員", '{"ok":false,"error":"not_found"}', "404"), b.ignore()])
    T = t["id"]
    t_ident, t_uid, t_page, t_admin = sp(T, "身分", ".name"), sp(T, "LINE User ID", "[].plain_text"), f"{{{{{T}.id}}}}", admin_of(T)
    op = lambda o: c("{{1.op}}", "text:equal", o)
    ok_body = lambda s: f'{{"ok":true,"state":"{s}"}}'
    t_pl, t_expiry = plan_expiry(b, sp(T, "方案", ".name"), "管理會員", [respond_json("回傳讀不到方案（管理）", '{"ok":false,"error":"bad_plan"}', "500"), b.ignore()])
    i = t_ident[2:-2]
    op_ok = ('{{if(1.op = "approve"; if(' + i + ' = "審核中"; "Y"; "N"); if(1.op = "premium"; if(' + i + ' = "一般會員"; "Y"; "N"); if(1.op = "ban"; if('
             + i + ' = "停權"; "N"; "Y"); if(1.op = "restore"; if(' + i + ' = "停權"; "Y"; "N"); "N"))))}}')
    admin_set_flow = [b.router("檢查會員編號", [
        (flt("會員編號格式正確", [[c("{{1.id}}", "text:pattern", "^[0-9a-fA-F-]{32,36}$")]]), [t, b.router("管理動作", [
            (flt("核准（審核中）", [[op("approve"), c(op_ok, "text:equal", "Y")]]), [
                t_pl, b.update("管理：改成一般會員", t_page, [fv("身分", "select", "一般會員"), now("核准時間"), date("到期日", t_expiry)]),
                respond_json("回傳已核准（管理）", ok_body("member")), apply_menu(b, t_uid, t_page, want_menu(t_admin, lit("一般會員")), "管理核准")]),
            (flt("升級高級會員", [[op("premium"), c(op_ok, "text:equal", "Y")]]), [
                b.update("管理：改成高級會員", t_page, [fv("身分", "select", "高級會員")]),
                respond_json("回傳已升級", ok_body("premium")), apply_menu(b, t_uid, t_page, want_menu(t_admin, lit("高級會員")), "管理升級")]),
            (flt("停權", [[op("ban"), c(op_ok, "text:equal", "Y")]]), [
                b.update("管理：停權", t_page, [fv("身分", "select", "停權")]),
                respond_json("回傳已停權", ok_body("banned")), apply_menu(b, t_uid, t_page, want_menu(t_admin, lit("停權")), "管理停權")]),
            (flt("恢復（停權 → 一般會員）", [[op("restore"), c(op_ok, "text:equal", "Y")]]), [
                b.update("管理：恢復一般會員", t_page, [fv("身分", "select", "一般會員")]),
                respond_json("回傳已恢復", ok_body("member")), apply_menu(b, t_uid, t_page, want_menu(t_admin, lit("一般會員")), "管理恢復")]),
            (flt("這個動作不適用", [[c(op_ok, "text:notequal", "Y")]]), [
                respond_json("回傳不適用", '{"ok":false,"error":"not_allowed"}', "409")]),
        ])]),
        (flt("會員編號格式不對", [[c("{{1.id}}", "text:notpattern", "^[0-9a-fA-F-]{32,36}$")]]), [
            respond_json("回傳會員編號不對", '{"ok":false,"error":"bad_request"}', "400")]),
    ])]
    not_admin = [[none], [exist, c(w_admin, "text:notequal", "Y")]]

    act = lambda a: c("{{1.a}}", "text:equal", a)
    PAGE_ACTS = ("me", "apply", "profile", "news", "courses", "course_open", "admin_list", "admin_set")
    key_ok = c("{{1.k}}", "text:equal", KEY)
    flow = [
        webhook(MK["api_hook_id"], "會員頁面與核准連結送來的請求"),
        b.router("請求種類", [
            (flt("核准連結：核准", [[act("approve"), key_ok, c("{{1.id}}", "exist")]]), notion_link_flow("approve")),
            (flt("核准連結：套用身分", [[act("sync"), key_ok, c("{{1.id}}", "exist")]]), notion_link_flow("sync")),
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
                        (flt("改基本資料", [[act("profile"), c("{{1.name}}", "exist"), c("{{1.phone}}", "exist")]]), profile_flow),
                        (flt("最新消息", [[act("news")]]), news_flow),
                        (flt("課程列表", [[act("courses")]]), courses_flow),
                        (flt("打開內容", [[act("course_open"), c("{{1.id}}", "exist")]]), open_flow),
                        (flt("管理：名冊", [[act("admin_list"), exist, is_admin]]), admin_list_flow),
                        (flt("管理：動作", [[act("admin_set"), exist, is_admin, c("{{1.id}}", "exist"), c("{{1.op}}", "exist")]]), admin_set_flow),
                        (flt("管理：不是管理者", [[act("admin_list"), *g] for g in not_admin] + [[act("admin_set"), *g] for g in not_admin]), [
                            respond_json("回傳不是管理者", '{"ok":false,"error":"not_admin"}', "403")]),
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
    """建立三張選單：訪客（設為所有人的預設）、會員（別名 member）、管理者（別名 admin）；清掉其他舊選單；
    再把會員、管理者重新綁到新的選單。圖片讀 Notion「前台設定」的訪客選單圖、會員選單圖、管理者選單圖
    （上傳的檔案或外部連結都可以），LINE 規定 2500×1686、1MB 以內。
    格子：上排 最新消息｜課程｜AI 小幫手（三張相同），下排一整塊：訪客「申請加入」、會員「會員專區」、管理者「管理會員」。"""
    b = B(10)
    uri = lambda u: {"type": "uri", "uri": u}

    def area(col, row, url, span=1):
        x = COLS[col]
        return {"bounds": {"x": x, "y": row * ROW, "width": COLS[col + span] - x, "height": ROW}, "action": uri(url)}
    top = [area(0, 0, MEMBER_LIFF + "?v=news"), area(1, 0, MEMBER_LIFF + "?v=courses"), area(2, 0, MEMBER_LIFF + "?v=ai")]
    site = b.notion_api("讀前台設定（選單圖）", f"/v1/pages/{SETTINGS_PAGE}")
    S = site["id"]

    def img(prop):
        f = f"{S}.body.properties.`{prop}`.files[1]"
        return "{{ifempty(" + f + ".file.url; " + f + ".external.url)}}"

    def make(name, prop, areas, label):
        g = {"id": b.nid(), "module": "http:ActionGetFile", "version": 3, "parameters": {"handleErrors": False},
             "mapper": {"url": img(prop), "method": "get", "serializeUrl": False, "shareCookies": False},
             "metadata": b.meta(f"下載{label}圖片")}
        m = {"id": b.nid(), "module": "line:createARichMenu", "version": 1, "parameters": {"__IMTCONN__": CONN_LINE},
             "mapper": {"name": name, "chatBarText": "選單", "selected": True, "height": 2 * ROW, "areas": areas,
                        "data": f"{{{{{g['id']}.data}}}}", "filename": f"{name}.png"},
             "metadata": b.meta(f"建立{label}", LINE_META)}
        return g, m

    gg, gm = make("guest", "訪客選單圖", top + [area(0, 1, MEMBER_LIFF + "?v=home", span=3)], "訪客選單")
    mg, mm = make("member", "會員選單圖", top + [area(0, 1, MEMBER_LIFF + "?v=home", span=3)], "會員選單")
    ag, am = make("admin", "管理者選單圖", top + [area(0, 1, MEMBER_LIFF + "?v=admin", span=3)], "管理者選單")
    G, Mm, A = gm["id"], mm["id"], am["id"]
    created = c(f"{{{{{A}.richMenuId}}}}", "exist")

    def alias_router(alias, menu_id):
        rid = f"{{{{{menu_id}.richMenuId}}}}"
        return b.router(f"設定別名 {alias}", [
            # 已有別名時更新成功、新建失敗；第一次部署時相反，各自出錯就略過
            (flt(f"更新別名 {alias}", [[created]]), [
                b.line(f"更新別名 {alias}", f"/v2/bot/richmenu/alias/{alias}", "POST", {"richMenuId": rid}, onerror=[b.ignore()])]),
            (flt(f"新建別名 {alias}", [[created]]), [
                b.line(f"新建別名 {alias}", "/v2/bot/richmenu/alias", "POST", {"richMenuAliasId": alias, "richMenuId": rid}, onerror=[b.ignore()])]),
        ])

    lst = b.line("列出所有圖文選單", "/v2/bot/richmenu/list")
    feed = {"id": b.nid(), "module": "builtin:BasicFeeder", "version": 1, "mapper": {"array": f"{{{{{lst['id']}.body.richmenus}}}}"},
            "metadata": b.meta("逐張檢查")}
    F = feed["id"]
    drop = b.line("刪除舊選單", f"/v2/bot/richmenu/{{{{{F}.richMenuId}}}}", "DELETE", onerror=[b.ignore()])
    drop["filter"] = flt("不是新的三張", [[c(f"{{{{{F}.richMenuId}}}}", "text:notequal", f"{{{{{x}.richMenuId}}}}") for x in (G, Mm, A)]])

    def rebind(label, query, menu_id, menu):
        q = b.notion_api(f"找所有{label}", f"/v1/data_sources/{DS}/query", "POST", query)
        fd = {"id": b.nid(), "module": "builtin:BasicFeeder", "version": 1, "mapper": {"array": f"{{{{{q['id']}.body.results}}}}"},
              "metadata": b.meta(f"逐位{label}")}
        X = fd["id"]
        uid = f"{{{{{X}.properties.`LINE User ID`.rich_text[1].plain_text}}}}"
        bind = b.line(f"綁定新的{menu}選單", f"/v2/bot/user/{uid}/richmenu/{{{{{menu_id}.richMenuId}}}}", "POST", onerror=[b.ignore()])
        bind["filter"] = flt(f"有 LINE 帳號（{label}）", [[c(uid, "exist")]])
        return [q, fd, bind, b.update(f"記下目前選單：{menu}（重建）", f"{{{{{X}.id}}}}", [fv("目前選單", "select", menu), now("選單同步時間")])]
    members_q = ('{"filter":{"and":[{"or":[{"property":"身分","select":{"equals":"一般會員"}},{"property":"身分","select":{"equals":"高級會員"}}]},'
                 '{"property":"角色","multi_select":{"does_not_contain":"管理者"}}]},"page_size":100}')
    admins_q = '{"filter":{"property":"角色","multi_select":{"contains":"管理者"}},"page_size":100}'

    # 預設選單一定要在三張都建好之後才設：Make 的「Create a Rich Menu」勾了 selected 會把剛建好的那張設成預設
    # （朕宏 2026-10-21 會員選單因此蓋過訪客選單，所有好友都看到會員選單）
    flow = [site, gg, gm, mg, mm, ag, am,
            b.line("設為所有人的預設選單（訪客）", f"/v2/bot/user/all/richmenu/{{{{{G}.richMenuId}}}}", "POST"),
            alias_router(ALIAS, Mm), alias_router(ALIAS_ADMIN, A),
            b.router("收尾", [
                # 刪除舊選單時，LINE 會自動解除所有人身上的舊綁定（苗栗 10/14 舊選單卡住的教訓）
                (flt("清掉舊選單", [[created]]), [lst, feed, drop]),
                (flt("會員重新綁定", [[created]]), rebind("會員", members_q, Mm, "會員")),
                (flt("管理者重新綁定", [[created]]), rebind("管理者", admins_q, A, "管理者")),
            ])]
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
