"""會員通（LINE Member Kit）：產生會員模組的 Make 藍圖，輸出到 make/（最早改寫自 philko2017/line-namecard 的 tools/make_member_blueprint.py）。
情境名稱前綴、Notion 編號、LINE 編號都從 tools/config.local.json 讀，換客戶不用改這支程式。

- 會員_API.blueprint.json：「{專案}｜會員 API（自動執行）」（欄位 t 是 LINE Access Token）
    a=me 我的身分＋前台設定＋方案＋是否管理者（順便校正選單）｜a=apply 申請入會＋匯款回報｜a=profile 會員自己改基本資料
    a=news 內容庫標籤「最新消息」｜a=courses 內容庫標籤「課程」（列表都不含內容連結，上鎖的也列出來）｜a=course_open 依身分給內容連結（有影片檔就給 Notion 一小時有效的檔案網址）
    a=admin_list 名冊｜a=admin_set 核准、升級高級會員、停權、恢復（只有名冊「角色」勾管理者的人能用）
    頁面上的文字、圖片、方案、收款帳戶都從 Notion「前台設定」「方案」讀，repo 裡不放。
    Notion 核准連結：a=approve 核准入會｜a=sync 依身分套用選單（欄位 k 是密鑰、id 是名冊頁面 ID）
- 會員_LINE事件.blueprint.json：「{專案}｜會員：LINE 事件（自動執行）」加好友就建一筆非會員；封鎖時標記
- 圖片_上傳到雲端硬碟.blueprint.json：「{專案}｜圖片：上傳到雲端硬碟（手動執行）」把 Notion 的邀請圖、內容庫封面複製到
    Google 雲端硬碟圖床（會員通圖床／專案名稱），網址寫回「邀請圖網址」「封面網址」，頁面再用縮圖網址顯示
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
from urllib.parse import quote
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tools" / ("config.example.json" if "--example" in sys.argv else "config.local.json")).read_text(encoding="utf-8"))
MK, LN = CFG["make"], CFG["line"]
CONN_NOTION, CONN_LINE = MK["notion_connection_id"], MK["line_connection_id"]
CONN_DRIVE = MK.get("gdrive_connection_id")
DRIVE_FOLDER = CFG.get("drive", {}).get("folder_id", "")   # 圖床：Google 雲端硬碟「會員通圖床／專案名稱」
# AI 小幫手：Gemini 連線、對話暫存（Make Data Store）、模型與關鍵字
CONN_GEMINI = MK.get("gemini_connection_id")
ASSIST_DS = MK.get("assistant_datastore_id")
AS = CFG.get("assistant", {})
GEMINI_MODEL = AS.get("model", "gemini-3.5-flash-lite")   # 用確切的模型 ID，「latest」別名有時找不到模型
GEMINI_FALLBACK = AS.get("fallback_model", "gemini-3.1-flash-lite")   # 主模型忙線（503）時改用
KEYWORD, END_WORD = AS.get("keyword", "AI小幫手"), AS.get("end_word", "結束")
DS = CFG["notion"]["data_source_id"]
# 前台設定（一列）與方案：會員頁面上的文字、收款帳戶、價格都從這兩張 Notion 表讀，repo 裡不放
SETTINGS_PAGE = CFG["notion"]["settings_page_id"]
PLANS_DS = CFG["notion"]["plans_data_source_id"]
CONTENT_DS = CFG["notion"]["content_data_source_id"]    # 內容庫（最新消息、課程、數位產品都在這裡，用「標籤」分）
# 內容庫列表回傳的欄位（Notion 欄位 ID）：除了「內容連結」都要，連結只在點開時依身分給
CONTENT_LIST_PROPS = CFG["notion"]["content_list_property_ids"]
RULES_DS = CFG["notion"].get("assistant_rules_data_source_id")   # 🤖 小幫手指示
FAQ_DS = CFG["notion"].get("faq_data_source_id")                 # 📖 FAQ 知識庫
LOG_DS = CFG["notion"].get("assistant_log_data_source_id")       # 💬 小幫手對話紀錄
# 欄位清單直接寫進網址：Make 的 qs 遇到同名參數只留最後一個（2026-10-23 列表只剩「標籤」一個欄位）
LIST_QS = "&".join("filter_properties=" + quote(pid, safe="") for pid in CONTENT_LIST_PROPS)
NOTION_VERSION = "2025-09-03"   # 查詢 data source（/v1/data_sources/…/query）要這個版本
KEY = CFG["approve_key"]
CHANNEL = LN["login_channel_id"]
MEMBER_LIFF = f"https://liff.line.me/{LN['liff_id']}"
ORIGIN = CFG.get("page_origin") or "*"
REPO = CFG.get("repo", "phil-ai-academy")
# 情境名稱前面加專案名、最後標明（自動執行）或（手動執行），例如「{專案}｜會員 API（自動執行）」（另外在 Make 用同名資料夾和標籤分類）
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

    def line_raw(self, name, url, body, onerror=None):
        """body 已經是 JSON 文字（自由文字先用 to_json 跳脫過）"""
        d = {"id": self.nid(), "module": "line:makeApiCall", "version": 1, "parameters": {"__IMTCONN__": CONN_LINE},
             "mapper": {"url": url, "method": "POST", "headers": [{"key": "Content-Type", "value": "application/json"}], "body": body},
             "metadata": self.meta(name, LINE_META)}
        if onerror:
            d["onerror"] = onerror
        return d

    def reply(self, name, token, text_json):
        """回覆一則文字訊息（不耗 LINE 訊息額度）；text_json 是含引號的 JSON 字串"""
        return self.line_raw(name, "/v2/bot/message/reply",
                             '{"replyToken":"' + token + '","messages":[{"type":"text","text":' + text_json + '}]}', onerror=[self.ignore()])

    def gemini(self, name, body, onerror=None, model=None, fallback=True):
        """Gemini 忙線（503）時改用備援模型再試一次，成功就當作原本的結果繼續（builtin:Resume）；兩個都失敗才走 onerror"""
        d = {"id": self.nid(), "module": "gemini-ai:makeApiCall", "version": 1, "parameters": {"__IMTCONN__": CONN_GEMINI},
             "mapper": {"url": f"/v1beta/models/{model or GEMINI_MODEL}:generateContent", "method": "POST",
                        "headers": [{"key": "Content-Type", "value": "application/json"}], "qs": [], "body": body},
             "metadata": self.meta(name, [{"name": "__IMTCONN__", "type": "account:gemini-ai-q9zyjp", "label": "Connection", "required": True}])}
        if fallback:
            fb = self.gemini(name + "（備援模型）", body, onerror=onerror, model=GEMINI_FALLBACK, fallback=False)
            d["onerror"] = [fb, {"id": self.nid(), "module": "builtin:Resume", "version": 1,
                                 "mapper": {"body": f"{{{{{fb['id']}.body}}}}", "statusCode": f"{{{{{fb['id']}.statusCode}}}}"},
                                 "metadata": {"designer": {"x": 1200, "y": self.y}}}]
        elif onerror:
            d["onerror"] = onerror
        return d

    def parse(self, name, text):
        return {"id": self.nid(), "module": "json:ParseJSON", "version": 1, "parameters": {"type": ""},
                "mapper": {"json": text}, "metadata": self.meta(name)}

    def ds_get(self, name, key):
        return {"id": self.nid(), "module": "datastore:GetRecord", "version": 1, "parameters": {"datastore": ASSIST_DS},
                "mapper": {"key": key, "returnWrapped": False}, "metadata": self.meta(name)}

    def ds_put(self, name, key, data):
        return {"id": self.nid(), "module": "datastore:AddRecord", "version": 1, "parameters": {"datastore": ASSIST_DS},
                "mapper": {"key": key, "data": data, "overwrite": True}, "metadata": self.meta(name)}

    def ds_update(self, name, key, data):
        return {"id": self.nid(), "module": "datastore:UpdateRecord", "version": 1, "parameters": {"datastore": ASSIST_DS},
                "mapper": {"key": key, "data": data, "insert": False}, "metadata": self.meta(name)}

    def sleep(self, name, seconds):
        return {"id": self.nid(), "module": "util:FunctionSleep", "version": 1, "parameters": {},
                "mapper": {"duration": seconds}, "metadata": self.meta(name)}

    def create_in(self, name, ds, fields):
        return self.notion("createDataSourceItem", name, {"fields": fields, "select": "map", "data_source": ds})

    def router(self, name, routes):
        mid = self.nid()
        rs = []
        for f, mods in routes:
            mods = [dict(m) for m in mods]
            if f:
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
    # ==== 最新消息、課程：同一張內容庫，用「標籤」決定出現在哪裡；列表不帶「內容連結」，點開時才依身分給連結 ====
    def list_flow(tag, key, sort):
        q = ('{"filter":{"and":[{"property":"上架狀態","select":{"equals":"上架"}},{"property":"標籤","multi_select":{"contains":"' + tag
             + '"}}]},"sorts":[' + sort + '],"page_size":100}')
        api = b.notion_api(f"讀內容庫（{tag}）", f"/v1/data_sources/{CONTENT_DS}/query?{LIST_QS}", "POST", q)
        js = b.to_json(f"{tag}轉 JSON", f"{{{{{api['id']}.body.results}}}}")
        return [api, js, respond_json(f"回傳{tag}", f'{{"ok":true,"{key}":{{{{{js["id"]}.json}}}}}}')]
    news_flow = list_flow("最新消息", "news", '{"property":"上架日期","direction":"descending"}')
    courses_flow = list_flow("課程", "items", '{"property":"排序","direction":"ascending"},{"property":"上架日期","direction":"descending"}')

    item = b.notion_api("讀要打開的內容", "/v1/pages/{{1.id}}",
                        onerror=[respond_json("回傳找不到內容", '{"ok":false,"error":"not_found"}', "404"), b.ignore()])
    I = item["id"]
    aud, status, parent = (f"{{{{{I}.body.properties.`開放對象`.select.name}}}}", f"{{{{{I}.body.properties.`上架狀態`.select.name}}}}",
                           f"{{{{{I}.body.parent.data_source_id}}}}")
    wi = "ifempty(" + w_ident[2:-2] + '; "非會員")'
    allow = ("{{if(" + parent[2:-2] + f' = "{CONTENT_DS}"; if(' + status[2:-2] + ' = "上架"; if(' + w_admin[2:-2] + ' = "Y"; "Y"; if('
             + aud[2:-2] + ' = "公開"; "Y"; if(' + aud[2:-2] + ' = "一般會員"; if(' + wi + ' = "一般會員"; "Y"; if(' + wi
             + ' = "高級會員"; "Y"; "N")); if(' + aud[2:-2] + ' = "高級會員"; if(' + wi + ' = "高級會員"; "Y"; "N"); "N")))); "N"); "N")}}')
    # 有上傳「影片檔」就給 Notion 的檔案網址（約一小時後失效，轉貼出去很快就看不到），頁面直接嵌入播放；沒有才給「內容連結」
    vid = f"{I}.body.properties.`影片檔`.files[1].file.url"
    link = "{{ifempty(" + vid + "; " + f"{I}.body.properties.`內容連結`.url" + ")}}"
    video = "{{if(" + vid + '; "Y"; "N")}}'
    trial = f"{{{{{I}.body.properties.`試看連結`.url}}}}"
    # 導讀：Phil 為 YouTube 等外部影片寫的三五百字說明，跟連結一樣有權限才給
    intro = "{{join(map(" + f"{I}.body.properties.`導讀`.rich_text" + '; "plain_text"); "")}}'
    open_flow = [b.router("檢查內容編號", [
        (flt("內容編號格式正確", [[c("{{1.id}}", "text:pattern", "^[0-9a-fA-F-]{32,36}$")]]), [item, b.router("可不可以看", [
            (flt("可以看", [[c(allow, "text:equal", "Y")]]), [
                respond_json("回傳內容連結", '{"ok":true,"link":"' + enc(link) + '","video":"' + video + '","intro":"' + enc(intro) + '","trial":"' + enc(trial) + '"}')]),
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
    return blueprint(PREFIX + "會員 API（自動執行）", flow)


# ==== AI 小幫手（LINE 聊天室）：按選單送出關鍵字叫醒，之後打字就由 Gemini 依 Notion 指示和 FAQ 回答 ====
# 對話進行中的狀態放 Make Data Store（每位會員一筆，key 是 LINE User ID）；每則訊息回覆後等閒置秒數，
# 期間沒有新訊息（seq 沒變）就結束，請 Gemini 整理對話分析，寫一筆「💬 小幫手對話紀錄」。
# 自由文字一律先經 json:TransformToJSON 跳脫，存進暫存的 transcript／blocks 是已跳脫、可直接放進 JSON 的文字。
TODAY = '{{formatDate(now; "YYYY-MM-DD"; "Asia/Taipei")}}'


def inner(mid):
    """to_json 輸出的 JSON 字串去掉前後引號，可以直接嵌進另一段 JSON 字串裡"""
    return "{{substring(" + f"{mid}.json; 1; length({mid}.json) - 1" + ")}}"


def para(prefix, text):
    """Notion 段落區塊（text 已跳脫）"""
    return ('{"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"'
            + prefix + text + '"}}]}}')


def qs_props(ids):
    return "?" + "&".join("filter_properties=" + quote(i, safe="") for i in ids)


def assistant_close(b, R, uid, reason, seq_cond):
    """結束一場對話：先關掉暫存；有問過問題才請 Gemini 整理分析，寫進對話紀錄（含全文）。R 是暫存紀錄的模組編號"""
    off = b.ds_update(f"關閉對話（{reason}）", uid, {"active": False})
    off["filter"] = flt(f"還在對話中（{reason}）", [[c(f"{{{{{R}.active}}}}", "text:equal", "true"), *seq_cond]])
    schema = ('{"type":"OBJECT","properties":{"summary":{"type":"STRING","description":"一句話摘要"},'
              '"need":{"type":"STRING","description":"會員想解決的問題"},'
              '"level":{"type":"STRING","enum":["高","中","低","無"],"description":"商機程度"},'
              '"next":{"type":"STRING","description":"建議 Phil 下一步怎麼跟進"}},"required":["summary","need","level","next"]}')
    an = b.gemini(f"整理對話分析（{reason}）",
                  '{"system_instruction":{"parts":[{"text":' + f"{{{{{R}.system}}}}" + '}]},'
                  '"contents":[{"role":"user","parts":[{"text":"請依照指示中的「對話分析」，整理下面這段對話。\\n' + f"{{{{{R}.transcript}}}}" + '"}]}],'
                  '"generationConfig":{"responseMimeType":"application/json","responseSchema":' + schema + '}}',
                  onerror=[b.ignore()])
    # 叫醒後一題都沒問成就只關掉對話，不整理分析、不寫紀錄（省點數）
    an["filter"] = flt(f"有問過問題（{reason}）", [[c(f"{{{{{R}.turns}}}}", "number:greater", "0")]])
    AP = b.parse(f"讀出分析（{reason}）", f"{{{{{an['id']}.body.candidates[1].content.parts[1].text}}}}")
    A = AP["id"]
    pg = b.create_in(f"寫對話紀錄（{reason}）", LOG_DS, [
        fv("標題", "title", f"{{{{{R}.name}}}}｜" + "{{formatDate(" + f"{R}.started" + '; "YYYY-MM-DD HH:mm"; "Asia/Taipei")}}'),
        fv("LINE User ID", "rich_text", uid), date("開始時間", f"{{{{{R}.started}}}}", True), now("結束時間"),
        fv("回合數", "number", f"{{{{{R}.turns}}}}"), fv("摘要", "rich_text", f"{{{{{A}.summary}}}}"),
        fv("需求", "rich_text", f"{{{{{A}.need}}}}"), fv("商機程度", "select", f"{{{{{A}.level}}}}"),
        fv("建議下一步", "rich_text", f"{{{{{A}.next}}}}"), fv("有找不到答案的問題", "checkbox", f"{{{{{R}.unanswered}}}}"),
        fv("結束方式", "select", reason), fv("跟進狀態", "select", "未處理")])
    P = pg["id"]
    rel = b.notion_api(f"連到會員（{reason}）", f"/v1/pages/{{{{{P}.id}}}}", "PATCH",
                       '{"properties":{"會員":{"relation":[{"id":"' + f"{{{{{R}.page}}}}" + '"}]}}}', onerror=[b.ignore()])
    body = b.notion_api(f"放入對話全文（{reason}）", f"/v1/blocks/{{{{{P}.id}}}}/children", "PATCH",
                        '{"children":[' + "{{substring(" + f"{R}.blocks" + "; 1)}}" + ']}', onerror=[b.ignore()])
    body["filter"] = flt(f"有對話內容（{reason}）", [[c(f"{{{{{R}.blocks}}}}", "exist")]])
    return [off, an, AP, pg, rel, body]


def assistant_flow(b, uid, text, token):
    S = b.ds_get("讀對話暫存", uid)
    I = S["id"]
    active = c(f"{{{{{I}.active}}}}", "text:equal", "true")
    inactive = c(f"{{{{{I}.active}}}}", "text:notequal", "true")
    day_turns = "if(" + f"{I}.day = " + TODAY[2:-2] + f"; {I}.day_turns; 0)"

    # --- 叫醒：只限會員（或管理者），讀指示與 FAQ 存進暫存，回開場白 ---
    m = b.find_member("找名冊（小幫手）", uid)
    M = m["id"]
    ident, adm = sp(M, "身分", ".name"), admin_of(M)
    mexist, mnone = c(f"{{{{{M}.id}}}}", "exist"), c(f"{{{{{M}.id}}}}", "notexist")
    ok = lambda *x: is_member(ident, mexist, *x) + [[mexist, c(adm, "text:equal", "Y"), *x]]
    no = [[mnone], [mexist, *not_member(ident), c(adm, "text:notequal", "Y")]]
    j = lambda v: '"' + v + '"'
    st = b.notion_api("讀前台設定（小幫手）", f"/v1/pages/{SETTINGS_PAGE}")
    rules = b.notion_api("讀小幫手指示", f"/v1/data_sources/{RULES_DS}/query", "POST",
                         '{"filter":{"property":"啟用","checkbox":{"equals":true}},"sorts":[{"property":"排序","direction":"ascending"}],"page_size":100}')
    faq = b.notion_api("讀 FAQ", f"/v1/data_sources/{FAQ_DS}/query", "POST",
                       '{"filter":{"property":"上架","checkbox":{"equals":true}},"page_size":100}')
    greet = b.notion_api("讀開場白與結束語", f"/v1/data_sources/{RULES_DS}/query", "POST",
                         '{"filter":{"and":[{"property":"啟用","checkbox":{"equals":true}},{"or":['
                         '{"property":"類型","select":{"equals":"開場白"}},{"property":"類型","select":{"equals":"結束語"}}]}]},'
                         '"sorts":[{"property":"排序","direction":"ascending"}]}')
    pick = lambda n: "join(map(" + f"{greet['id']}.body.results[{n}].properties.`內容`.rich_text" + '; "plain_text"); "")'
    rj = b.to_json("指示轉 JSON", "{{map(" + f"{rules['id']}.body.results" + '; "properties")}}')
    fj = b.to_json("FAQ 轉 JSON", "{{map(" + f"{faq['id']}.body.results" + '; "properties")}}')
    sysj = b.to_json("組成系統指示", "下面是 Notion 裡的設定（JSON），請照做。\n【小幫手指示】\n"
                     + f"{{{{{rj['id']}.json}}}}" + "\n【FAQ 知識庫】\n" + f"{{{{{fj['id']}.json}}}}"
                     + "\n回答一律用繁體中文。只回答與 FAQ 相關的內容，FAQ 沒有就依「找不到答案時」回覆，並把 found 設為 false。")
    sysj["mapper"]["object"] = sysj["mapper"]["object"].replace("\\n", "{{newline}}")
    hello = b.to_json("開場白", "{{replace(" + pick(1) + '; "{姓名}"; ' + sp(M, "姓名", "[1].plain_text")[2:-2] + ")}}")
    bye = b.to_json("結束語", "{{" + pick(2) + "}}")
    idle = "{{min(300; max(60; ifempty(" + f"{st['id']}.body.properties.`小幫手閒置分鐘`.number; 5) * 60))" + "}}"
    newseq = "{{ifempty(" + f"{I}.seq; 0) + 1" + "}}"
    put = b.ds_put("開始對話", uid, {
        "active": True, "seq": newseq, "turns": 0, "day": TODAY, "day_turns": "{{" + day_turns + "}}",
        "started": "{{now}}", "last": "{{now}}", "name": sp(M, "姓名", "[1].plain_text"), "page": f"{{{{{M}.id}}}}",
        "system": f"{{{{{sysj['id']}.json}}}}", "transcript": "", "unanswered": False, "bye": f"{{{{{bye['id']}.json}}}}",
        "limit": "{{ifempty(" + f"{st['id']}.body.properties.`小幫手每日回合上限`.number; 30)" + "}}", "idle": idle, "blocks": ""})
    G1 = b.ds_get("五分鐘後讀暫存（開場）", uid)
    start = [st, rules, faq, greet, rj, fj, sysj, hello, bye, put, b.reply("回開場白", token, f"{{{{{hello['id']}.json}}}}"),
             b.sleep("等閒置時間（開場）", idle), G1,
             *assistant_close(b, G1["id"], uid, "逾時", [c(f"{{{{{G1['id']}.seq}}}}", "text:equal", newseq)])]
    wake = [m, b.router("叫醒小幫手", [
        (flt("不是會員", no), [b.reply("回非會員", token, j("AI 小幫手目前只開放給會員使用。加入會員：" + MEMBER_LIFF + "?v=home"))]),
        (flt("已在對話中", ok(active)), [b.reply("回已在對話中", token, j("我在這裡，直接輸入你的問題就可以了。"))]),
        (flt("開始對話", ok(inactive)), start),
    ])]

    # --- 回答：檢查每日上限，Gemini 依指示和 FAQ 回答，記進暫存，等閒置時間後沒新訊息就結束 ---
    over = c("{{" + day_turns + "}}", "number:greaterorequal", f"{{{{{I}.limit}}}}")
    under = c("{{" + day_turns + "}}", "number:less", f"{{{{{I}.limit}}}}")
    Q = b.to_json("問題轉 JSON", "{{substring(" + text[2:-2] + "; 0; 800)}}")
    load = b.line("顯示輸入中", "/v2/bot/chat/loading/start", "POST", {"chatId": uid, "loadingSeconds": 20}, onerror=[b.ignore()])
    ans_schema = ('{"type":"OBJECT","properties":{"answer":{"type":"STRING","description":"給會員的回答"},'
                  '"found":{"type":"BOOLEAN","description":"FAQ 知識庫裡有沒有這個問題的答案"}},"required":["answer","found"]}')
    gem = b.gemini("Gemini 回答",
                   '{"system_instruction":{"parts":[{"text":' + f"{{{{{I}.system}}}}" + '}]},'
                   '"contents":[{"role":"user","parts":[{"text":"【之前的對話】' + f"{{{{{I}.transcript}}}}" + '\\n\\n【會員現在的問題】\\n' + inner(Q["id"]) + '"}]}],'
                   '"generationConfig":{"responseMimeType":"application/json","responseSchema":' + ans_schema + '}}',
                   onerror=[b.reply("回暫時無法回答", token, j("小幫手暫時無法回答，請稍後再問一次。")), b.ignore()])
    P = b.parse("讀出回答", f"{{{{{gem['id']}.body.candidates[1].content.parts[1].text}}}}")
    A = b.to_json("回答轉 JSON", "{{substring(" + f"{P['id']}.answer" + "; 0; 1800)}}")
    newseq2 = "{{" + f"{I}.seq + 1" + "}}"
    upd = b.ds_update("記下這一回合", uid, {
        "last": "{{now}}", "seq": newseq2, "turns": "{{" + f"{I}.turns + 1" + "}}", "day": TODAY,
        "day_turns": "{{" + day_turns + " + 1}}",
        "transcript": f"{{{{{I}.transcript}}}}" + "\\n會員：" + inner(Q["id"]) + "\\nAI：" + inner(A["id"]),
        "blocks": f"{{{{{I}.blocks}}}}," + para("會員：", inner(Q["id"])) + "," + para("AI：", inner(A["id"])),
        "unanswered": "{{if(" + f"{P['id']}.found; {I}.unanswered; true)" + "}}"})
    G2 = b.ds_get("五分鐘後讀暫存（回答）", uid)
    answer = [b.router("每日上限", [
        (flt("超過每日上限", [[over]]), [b.reply("回已達上限", token, j("今天的提問次數已經用完了，明天再來問我喔！"))]),
        (flt("還可以問", [[under]]), [Q, load, gem, P, A, b.reply("回覆答案", token, f"{{{{{A['id']}.json}}}}"), upd,
                                       b.sleep("等閒置時間（回答）", f"{{{{{I}.idle}}}}"), G2,
                                       *assistant_close(b, G2["id"], uid, "逾時", [c(f"{{{{{G2['id']}.seq}}}}", "text:equal", newseq2)])]),
    ])]

    # --- 輸入「結束」：回結束語，馬上整理紀錄 ---
    end = [b.reply("回結束語", token, f"{{{{{I}.bye}}}}"), *assistant_close(b, I, uid, "輸入結束", [])]

    return [S, b.router("小幫手", [
        (flt("叫醒小幫手", [[c(text, "text:equal", KEYWORD)]]), wake),
        (flt("結束對話", [[c(text, "text:equal", END_WORD), active]]), end),
        (flt("對話中的問題", [[active, c(text, "text:notequal", KEYWORD), c(text, "text:notequal", END_WORD)]]), answer),
    ])]


def build_events():
    """LINE 事件：加好友（follow）就在名冊建一筆非會員；封鎖（unfollow）時標記；
    文字訊息交給 AI 小幫手（按選單「AI 小幫手」送出關鍵字叫醒）。只處理每次送來的第一個事件。"""
    b = B()
    ev = "{{1.events[1]"
    uid, typ = ev + ".source.userId}}", ev + ".type}}"
    text, token = ev + ".message.text}}", ev + ".replyToken}}"
    w = b.find_member("找名冊", uid)
    W = w["id"]
    exist, none = c(f"{{{{{W}.id}}}}", "exist"), c(f"{{{{{W}.id}}}}", "notexist")
    prof = b.line("取得 LINE 名稱", f"/v2/bot/profile/{uid}")
    friend = [w, b.router("加好友或封鎖", [
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
    ])]
    flow = [
        {"id": 1, "module": "line:watchMessages", "version": 1, "mapper": {},
         "metadata": {"designer": {"x": -300, "y": 0, "name": "LINE 事件"},
                      "parameters": [{"name": "__IMTHOOK__", "type": "hook:line", "label": "Webhook", "required": True}]},
         "parameters": {"__IMTHOOK__": MK["events_hook_id"]}},
        b.router("依事件分流", [
            (flt("加好友、封鎖", [[c(typ, "text:equal", "follow")], [c(typ, "text:equal", "unfollow")]]), friend),
            (flt("文字訊息", [[c(typ, "text:equal", "message"), c(ev + ".message.type}}", "text:equal", "text")]]),
             assistant_flow(b, uid, text, token)),
        ]),
    ]
    bp = blueprint(PREFIX + "會員：LINE 事件（自動執行）", flow)
    # 小幫手每則訊息會等閒置時間，必須能同時處理多位會員
    bp["metadata"]["scenario"]["sequential"] = False
    return bp


def build_menu():
    """建立三張選單：訪客（設為所有人的預設）、會員（別名 member）、管理者（別名 admin）；清掉其他舊選單；
    再把會員、管理者重新綁到新的選單。圖片讀 Notion「前台設定」的訪客選單圖、會員選單圖、管理者選單圖
    （上傳的檔案或外部連結都可以），LINE 規定 2500×1686、1MB 以內。
    格子：上排 最新消息｜課程｜AI 小幫手（三張相同），下排一整塊：訪客「申請加入」、會員「會員專區」、管理者「管理會員」。"""
    b = B(10)
    uri = lambda u: {"type": "uri", "uri": u}

    def area(col, row, url, span=1, action=None):
        x = COLS[col]
        return {"bounds": {"x": x, "y": row * ROW, "width": COLS[col + span] - x, "height": ROW}, "action": action or uri(url)}
    # AI 小幫手：在聊天室送出關鍵字叫醒（LINE 事件情境接手）
    top = [area(0, 0, MEMBER_LIFF + "?v=news"), area(1, 0, MEMBER_LIFF + "?v=courses"),
           area(2, 0, None, action={"type": "message", "label": "AI 小幫手", "text": KEYWORD})]
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


def build_images():
    """圖床：把 Notion 上傳的封面、邀請圖複製到 Google 雲端硬碟（設成知道連結就能看），再把固定網址寫回 Notion。
    頁面用 lh3.googleusercontent.com/d/{檔案ID}=w640-h360-c-rw 這種網址，Google 會縮圖、轉 webp，手機也能暫存。
    網址最後的「#檔名」用來判斷換過圖沒有：檔名不同就重新上傳。內容放好之後手動執行。"""
    b = B(10)
    meta_drive = [{"name": "__IMTCONN__", "type": "account:google-restricted,google-drive", "label": "Connection", "required": True}]

    def to_drive(label, src, name, page, prop):
        dl = {"id": b.nid(), "module": "http:DownloadFile", "version": 4, "parameters": {"authenticationType": "noAuth"},
              "mapper": {"url": src, "shareCookies": False, "stopOnHttpError": True}, "metadata": b.meta(f"下載{label}")}
        up = {"id": b.nid(), "module": "google-drive:uploadAFile", "version": 4, "parameters": {"__IMTCONN__": CONN_DRIVE},
              "mapper": {"data": f"{{{{{dl['id']}.data}}}}", "select": "value", "convert": False,
                         "filename": f"{{{{{dl['id']}.fileName}}}}", "folderId": "/" + DRIVE_FOLDER, "destination": "drive"},
              "metadata": b.meta(f"{label}上傳到雲端硬碟", meta_drive)}
        share = {"id": b.nid(), "module": "google-drive:shareAFileFolder", "version": 4, "parameters": {"__IMTCONN__": CONN_DRIVE},
                 "mapper": {"file": f"{{{{{up['id']}.id}}}}", "role": "reader", "type": "anyone", "select": "file",
                            "destination": "drive", "allowFileDiscovery": False},
                 "metadata": b.meta(f"{label}設成知道連結就能看", meta_drive)}
        url = f"https://lh3.googleusercontent.com/d/{{{{{up['id']}.id}}}}#{{{{encodeURL({name})}}}}"
        save = b.notion_api(f"寫回{prop}", f"/v1/pages/{page}", "PATCH", '{"properties":{"' + prop + '":{"url":"' + url + '"}}}')
        return [dl, up, share, save]

    def need(label, url_prop, name):
        # 還沒有網址，或網址最後的檔名跟現在的圖不同（換過圖）
        return flt(f"{label}要上傳", [[c(name, "exist"), c(url_prop, "text:notcontain", "#{{encodeURL(" + name[2:-2] + ")}}")]])

    site = b.notion_api("讀前台設定", f"/v1/pages/{SETTINGS_PAGE}")
    S = site["id"]
    inv = f"{S}.body.properties.`邀請圖`.files[1]"
    inv_name, inv_src = f"{{{{{inv}.name}}}}", "{{ifempty(" + inv + ".file.url; " + inv + ".external.url)}}"
    inv_flow = to_drive("邀請圖", inv_src, inv_name[2:-2], SETTINGS_PAGE, "邀請圖網址")

    q = b.notion_api("找有封面的內容", f"/v1/data_sources/{CONTENT_DS}/query", "POST",
                     '{"filter":{"property":"封面","files":{"is_not_empty":true}},"page_size":100}')
    feed = {"id": b.nid(), "module": "builtin:BasicFeeder", "version": 1, "mapper": {"array": f"{{{{{q['id']}.body.results}}}}"},
            "metadata": b.meta("逐筆檢查封面")}
    X = feed["id"]
    cov = f"{X}.properties.`封面`.files[1]"
    cov_name, cov_src = f"{{{{{cov}.name}}}}", "{{ifempty(" + cov + ".file.url; " + cov + ".external.url)}}"
    cov_flow = to_drive("封面", cov_src, cov_name[2:-2], f"{{{{{X}.id}}}}", "封面網址")
    cov_flow[0]["filter"] = need("封面", f"{{{{{X}.properties.`封面網址`.url}}}}", cov_name)

    flow = [site, b.router("邀請圖與封面", [
        (need("邀請圖", f"{{{{{S}.body.properties.`邀請圖網址`.url}}}}", inv_name), inv_flow),
        (None, [q, feed, *cov_flow]),
    ])]
    bp = blueprint(PREFIX + "圖片：上傳到雲端硬碟（手動執行）", flow)
    bp["metadata"]["instant"] = False
    return bp


def main():
    out = ROOT / "make" / ("example" if "--example" in sys.argv else "")
    out.mkdir(parents=True, exist_ok=True)
    for fname, bp in (("會員_API.blueprint.json", build_api()), ("會員_LINE事件.blueprint.json", build_events()),
                      ("會員_建立圖文選單.blueprint.json", build_menu()), ("圖片_上傳到雲端硬碟.blueprint.json", build_images())):
        p = out / fname
        p.write_text(json.dumps(bp, ensure_ascii=False, indent=1), encoding="utf-8")
        print(p.relative_to(ROOT), p.stat().st_size)


if __name__ == "__main__":
    main()
