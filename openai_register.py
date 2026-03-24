import os
import json
import re
import time
import random
import string
import base64
import hashlib
import secrets
import urllib.parse
import urllib.request
import urllib.error
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict
from dataclasses import dataclass

from curl_cffi import requests

# ====================== 强密码生成 ======================
def get_password() -> str:
    chars = string.ascii_letters + string.digits
    base_pwd = ''.join(random.choices(chars, k=10))
    return base_pwd + "Aa1@!"

# ====================== 【TempMail.lol 2026 完整版】邮箱模块（已修复代理） ======================
class Message:
    def __init__(self, data: dict):
        self.from_addr = data.get("from", "")
        self.subject = data.get("subject", "")
        self.body = data.get("body", "") or ""
        self.html_body = data.get("html", "") or ""

class EMail:
    def __init__(self, proxies: dict = None):
        self.s = requests.Session(proxies=proxies, impersonate="chrome")  # ← 关键修复：走代理 + chrome指纹
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        # 创建随机邮箱（官方 2026 API）
        r = self.s.post("https://api.tempmail.lol/v2/inbox/create", json={})
        r.raise_for_status()
        data = r.json()
        self.address = data["address"]
        self.token = data["token"]
        print(f"[+] 生成邮箱: {self.address} (TempMail.lol)")
        print(f"[*] 自动轮询已启动（token 已保存）")

    def _get_messages(self):
        r = self.s.get(f"https://api.tempmail.lol/v2/inbox?token={self.token}")
        r.raise_for_status()
        return r.json().get("emails", [])

    def wait_for_message(self, timeout=600, filter_func=None):
        print("[*] 等待 OpenAI 验证码（TempMail.lol 轮询，最多 10 分钟）")
        start = time.time()
        while time.time() - start < timeout:
            msgs = self._get_messages()
            print(f"[*] 已轮询 {int(time.time()-start)} 秒，收到 {len(msgs)} 封邮件...")
            for msg_data in msgs:
                msg = Message(msg_data)
                if not filter_func or filter_func(msg):
                    print(f"[+] 收到匹配邮件: {msg.subject}")
                    return msg
            time.sleep(2)
        raise TimeoutError("[-] 10 分钟内未收到 OpenAI 验证码")

def get_email(proxies=None):
    inbox = EMail(proxies=proxies)
    return inbox.address, inbox

# ====================== OAuth 模块（完整保留） ======================
AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_REDIRECT_URI = f"http://localhost:1455/auth/callback"
DEFAULT_SCOPE = "openid email profile offline_access"

def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _sha256_b64url_no_pad(s: str) -> str:
    return _b64url_no_pad(hashlib.sha256(s.encode("ascii")).digest())

def _random_state(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)

def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)

def _parse_callback_url(callback_url: str) -> Dict[str, str]:
    candidate = callback_url.strip()
    if not candidate:
        return {"code": "", "state": "", "error": "", "error_description": ""}
    if "://" not in candidate:
        if candidate.startswith("?"):
            candidate = f"http://localhost{candidate}"
        elif any(ch in candidate for ch in "/?#") or ":" in candidate:
            candidate = f"http://{candidate}"
        elif "=" in candidate:
            candidate = f"http://localhost/?{candidate}"
    parsed = urllib.parse.urlparse(candidate)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    fragment = urllib.parse.parse_qs(parsed.fragment, keep_blank_values=True)
    for key, values in fragment.items():
        if key not in query or not query[key] or not (query[key][0] or "").strip():
            query[key] = values
    def get1(k: str) -> str:
        v = query.get(k, [""])
        return (v[0] or "").strip()
    code = get1("code")
    state = get1("state")
    error = get1("error")
    error_description = get1("error_description")
    if code and not state and "#" in code:
        code, state = code.split("#", 1)
    if not error and error_description:
        error, error_description = error_description, ""
    return {"code": code, "state": state, "error": error, "error_description": error_description}

def _jwt_claims_no_verify(id_token: str) -> Dict[str, Any]:
    if not id_token or id_token.count(".") < 2:
        return {}
    payload_b64 = id_token.split(".")[1]
    pad = "=" * ((4 - (len(payload_b64) % 4)) % 4)
    try:
        payload = base64.urlsafe_b64decode((payload_b64 + pad).encode("ascii"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}

def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0

def _post_form(url: str, data: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.status != 200:
                raise RuntimeError(f"Token 交换失败: {resp.status}: {raw.decode('utf-8', 'replace')}")
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raise RuntimeError(f"Token 交换失败: {exc.code}: {raw.decode('utf-8', 'replace')}") from exc

@dataclass(frozen=True)
class OAuthStart:
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str

def generate_oauth_url(*, redirect_uri: str = DEFAULT_REDIRECT_URI, scope: str = DEFAULT_SCOPE) -> OAuthStart:
    state = _random_state()
    code_verifier = _pkce_verifier()
    code_challenge = _sha256_b64url_no_pad(code_verifier)
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return OAuthStart(auth_url=auth_url, state=state, code_verifier=code_verifier, redirect_uri=redirect_uri)

def submit_callback_url(*, callback_url: str, expected_state: str, code_verifier: str, redirect_uri: str = DEFAULT_REDIRECT_URI, session=None) -> str:
    cb = _parse_callback_url(callback_url)
    if cb["error"]:
        desc = cb["error_description"]
        raise RuntimeError(f"OAuth 错误: {cb['error']}: {desc}".strip())
    if not cb["code"]: raise ValueError("Callback URL 缺少 ?code=")
    if not cb["state"]: raise ValueError("Callback URL 缺少 ?state=")
    if cb["state"] != expected_state: raise ValueError("State 校验不匹配")
    token_data = {"grant_type": "authorization_code", "client_id": CLIENT_ID, "code": cb["code"], "redirect_uri": redirect_uri, "code_verifier": code_verifier}
    if session is not None:
        r = session.post(TOKEN_URL, data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        if r.status_code != 200:
            raise RuntimeError(f"Token 交换失败: {r.status_code}: {r.text}")
        token_resp = r.json()
    else:
        token_resp = _post_form(TOKEN_URL, token_data)
    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    expires_in = _to_int(token_resp.get("expires_in"))
    claims = _jwt_claims_no_verify(id_token)
    email = str(claims.get("email") or "").strip()
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()
    now = int(time.time())
    expired_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + max(expires_in, 0)))
    now_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    config = {"id_token": id_token, "access_token": access_token, "refresh_token": refresh_token, "account_id": account_id, "last_refresh": now_rfc3339, "email": email, "type": "codex", "expired": expired_rfc3339}
    return json.dumps(config, ensure_ascii=False, indent=2)

# ====================== 核心主逻辑（注册 + 登录换 Token） ======================
def _get_sentinel(s, did):
    """获取 Sentinel PoW Token"""
    sen_req = json.dumps({"p": "", "id": did, "flow": "authorize_continue"})
    r = s.post("https://sentinel.openai.com/backend-api/sentinel/req", headers={"origin": "https://sentinel.openai.com", "referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6", "content-type": "text/plain;charset=UTF-8"}, data=sen_req)
    if r.status_code != 200:
        raise RuntimeError(f"Sentinel 验证失败: {r.text}")
    return json.dumps({"p": "", "t": "", "c": r.json().get("token", ""), "id": did, "flow": "authorize_continue"})

def check_ip(proxy: str):
    """检测代理 IP 地区，受限地区直接抛异常，含 TLS 重试"""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(3):
        try:
            s = requests.Session(proxies=proxies, impersonate="chrome")
            trace = s.get("https://cloudflare.com/cdn-cgi/trace", timeout=10)
            ip_re = re.search(r"^ip=(.+)$", trace.text, re.MULTILINE)
            loc_re = re.search(r"^loc=(.+)$", trace.text, re.MULTILINE)
            ip = ip_re.group(1) if ip_re else "Unknown"
            loc = loc_re.group(1) if loc_re else "Unknown"
            print(f"[*] 当前节点信息 -> Location: {loc}, IP: {ip}")
            if loc in ("CN", "HK", "RU"):
                raise RuntimeError("当前 IP 位于受限地区，请切换代理节点。")
            return
        except RuntimeError:
            raise
        except Exception as e:
            if attempt == 2:
                print(f"[!] IP 检测 3 次均失败: {e}")
            else:
                print(f"[!] IP 检测失败，重试 ({attempt+1}/3): {e}")
                time.sleep(2)

def run(proxy: str) -> str:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    s = requests.Session(proxies=proxies, impersonate="chrome")

    # 1. 生成邮箱
    print("[*] 正在生成随机私有域名邮箱...")
    email, inbox = get_email(proxies=proxies)
    print(f"[+] 成功生成邮箱: {email}")

    # 3. OAuth 初始化（注册用）
    print("[*] 正在初始化 OAuth 流程...")
    oauth = generate_oauth_url()
    s.get(oauth.auth_url)
    did = s.cookies.get("oai-did")
    if not did:
        return "[!] 错误：未能获取 oai-did Cookie"
    print(f"[+] 获取到 oai-did: {did}")

    # 4. Sentinel + SignUp
    print("[*] 正在提交注册...")
    signup_body = json.dumps({"username": {"value": email, "kind": "email"}, "screen_hint": "signup"})
    signup_resp = s.post("https://auth.openai.com/api/accounts/authorize/continue", headers={"referer": "https://auth.openai.com/create-account", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": _get_sentinel(s, did)}, data=signup_body)
    if signup_resp.status_code != 200:
        return f"[!] SignUp 失败: {signup_resp.text}"

    # 5. 设置密码 + 发送注册 OTP
    openai_pwd = get_password()
    reg_resp = s.post("https://auth.openai.com/api/accounts/user/register", headers={"referer": "https://auth.openai.com/create-account/password", "accept": "application/json", "content-type": "application/json"}, json={"password": openai_pwd, "username": email})
    if reg_resp.status_code != 200:
        return f"[!] 密码注册失败: {reg_resp.text}"
    print(f"[+] 密码设置成功（{openai_pwd}）")

    s.get("https://auth.openai.com/create-account/password")
    otp_send = s.get("https://auth.openai.com/api/accounts/email-otp/send", headers={"referer": "https://auth.openai.com/create-account/password", "accept": "application/json"})
    if otp_send.status_code != 200:
        return f"[!] OTP 发送失败: {otp_send.text}"

    # 6. 等待并验证注册 OTP
    print("[*] 正在等待邮箱 OTP 验证码...")
    def otp_filter(obj):
        subj = getattr(obj, "subject", "") or ""
        return any(kw in subj.lower() for kw in ["openai", "验证码", "verification", "code", "otp"])
    msg = inbox.wait_for_message(timeout=300, filter_func=otp_filter)
    code_match = re.search(r'\b(\d{6})\b', msg.body or msg.html_body or msg.subject or "")
    if not code_match:
        return "[!] 未在邮件中找到 6 位验证码"
    otp_code = code_match.group(1)
    print(f"[+] 提取到注册 OTP: {otp_code}")

    validate_resp = s.post("https://auth.openai.com/api/accounts/email-otp/validate", headers={"referer": "https://auth.openai.com/email-verification", "accept": "application/json", "content-type": "application/json"}, json={"code": otp_code})
    if validate_resp.status_code != 200:
        return f"[!] OTP 验证失败: {validate_resp.text}"
    print("[+] 注册 OTP 验证成功")

    # 7. 创建账号（需要 Sentinel Token）
    print("[*] 正在创建账号信息...")
    first_names = ["James", "Emma", "Liam", "Olivia", "Noah", "Ava", "Sophia", "Mason", "Lucas", "Mia"]
    last_names = ["Smith", "Johnson", "Brown", "Davis", "Wilson", "Moore", "Taylor", "Clark", "Lee", "Hall"]
    rand_name = f"{random.choice(first_names)} {random.choice(last_names)}"
    rand_year = random.randint(1985, 2003)
    rand_month = random.randint(1, 12)
    rand_day = random.randint(1, 28)
    rand_birthdate = f"{rand_year}-{rand_month:02d}-{rand_day:02d}"
    create_resp = s.post("https://auth.openai.com/api/accounts/create_account", headers={"referer": "https://auth.openai.com/about-you", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": _get_sentinel(s, did)}, data=json.dumps({"name": rand_name, "birthdate": rand_birthdate}))
    if create_resp.status_code != 200:
        return f"[!] 创建账号失败: {create_resp.text}"
    print("[+] 账号创建成功")

    # ===== 8. 新建会话登录（绕过 add-phone 步骤，含 TLS 重试） =====
    for login_attempt in range(3):
      try:
        print(f"[*] 正在通过登录流程获取 Token...{f' (重试 {login_attempt}/3)' if login_attempt else ''}")
        s2 = requests.Session(proxies=proxies, impersonate="chrome")
        oauth2 = generate_oauth_url()
        s2.get(oauth2.auth_url)
        did2 = s2.cookies.get("oai-did")
        if not did2:
            return "[!] 登录会话未能获取 oai-did"

        # 8a. 登录 authorize/continue
        lc = s2.post("https://auth.openai.com/api/accounts/authorize/continue", headers={"referer": "https://auth.openai.com/log-in", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": _get_sentinel(s2, did2)}, data=json.dumps({"username": {"value": email, "kind": "email"}, "screen_hint": "login"}))
        if lc.status_code != 200:
            return f"[!] 登录失败: {lc.text}"
        s2.get(lc.json().get("continue_url", ""))

        # 8b. 密码验证
        pw = s2.post("https://auth.openai.com/api/accounts/password/verify", headers={"referer": "https://auth.openai.com/log-in/password", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": _get_sentinel(s2, did2)}, json={"password": openai_pwd})
        if pw.status_code != 200:
            return f"[!] 密码验证失败: {pw.text}"

        # 8c. 登录 OTP（导航到 email-verification 页面自动触发发送）
        s2.get("https://auth.openai.com/email-verification", headers={"referer": "https://auth.openai.com/log-in/password"})
        print("[*] 正在等待登录 OTP...")
        time.sleep(2)

        otp2 = None
        for attempt in range(40):
            try:
                msgs = inbox._get_messages()
            except Exception:
                time.sleep(2)
                continue
            all_codes = []
            for m_data in msgs:
                m = Message(m_data)
                body = m.body or m.html_body or m.subject or ""
                codes = re.findall(r'\b(\d{6})\b', body)
                if codes:
                    all_codes.append(codes[-1])
            new_codes = [c for c in all_codes if c != otp_code]
            if new_codes:
                otp2 = new_codes[-1]
                break
            time.sleep(2)

        if not otp2:
            return "[!] 未收到登录 OTP"
        print(f"[+] 提取到登录 OTP: {otp2}")

        val = s2.post("https://auth.openai.com/api/accounts/email-otp/validate", headers={"referer": "https://auth.openai.com/email-verification", "accept": "application/json", "content-type": "application/json"}, json={"code": otp2})
        if val.status_code != 200:
            return f"[!] 登录 OTP 验证失败: {val.text}"
        val_data = val.json()
        print("[+] 登录 OTP 验证成功")

        # 9. Consent + Workspace
        consent_url = val_data.get("continue_url", "")
        s2.get(consent_url)

        auth_cookie = s2.cookies.get("oai-client-auth-session", domain=".auth.openai.com")
        if not auth_cookie:
            return "[!] 登录后未能获取 oai-client-auth-session"
        auth_data = base64.b64decode(auth_cookie.split(".")[0])
        auth_json = json.loads(auth_data)

        if "workspaces" not in auth_json or not auth_json["workspaces"]:
            return f"[!] Cookie 中无 workspaces: {list(auth_json.keys())}"
        workspace_id = auth_json["workspaces"][0]["id"]
        print(f"[+] Workspace ID: {workspace_id}")

        select_resp = s2.post("https://auth.openai.com/api/accounts/workspace/select", headers={"referer": consent_url, "accept": "application/json", "content-type": "application/json"}, json={"workspace_id": workspace_id})
        sel_data = select_resp.json()

        # 处理 organization 选择（如需要）
        if sel_data.get("page", {}).get("type", "") == "organization_select":
            orgs = sel_data.get("page", {}).get("payload", {}).get("data", {}).get("orgs", [])
            if orgs:
                org_sel = s2.post("https://auth.openai.com/api/accounts/organization/select", headers={"accept": "application/json", "content-type": "application/json"}, json={"org_id": orgs[0].get("id", ""), "project_id": orgs[0].get("default_project_id", "")})
                sel_data = org_sel.json()

        if "continue_url" not in sel_data:
            return f"[!] 未能获取 continue_url: {json.dumps(sel_data, ensure_ascii=False)[:500]}"

        # 10. 跟踪重定向获取 Callback
        print("[*] 正在跟踪重定向获取 Token...")
        r = s2.get(sel_data["continue_url"], allow_redirects=False)
        cbk = None
        for _ in range(20):
            loc = r.headers.get("Location", "")
            if loc.startswith("http://localhost"):
                cbk = loc
                break
            if r.status_code not in (301, 302, 303) or not loc:
                break
            r = s2.get(loc, allow_redirects=False)

        if not cbk:
            return "[!] 未能获取到 Callback URL"

        # 11. 交换 Token
        print("[+] 流程完成，正在交换 Token...")
        return submit_callback_url(callback_url=cbk, code_verifier=oauth2.code_verifier, redirect_uri=oauth2.redirect_uri, expected_state=oauth2.state, session=s2)

      except Exception as e:
        if login_attempt == 2:
            return f"[!] 登录重试 3 次均失败: {e}"
        print(f"[!] 登录失败，重试 ({login_attempt+1}/3): {e}")
        time.sleep(2)


def parse_accounts(filepath: str) -> list[dict]:
    """解析 accounts.json（每行一个 JSON 对象，对象之间没有逗号分隔）"""
    raw = open(filepath, "r", encoding="utf-8").read()
    accounts = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(raw):
        match = re.match(r'\s*', raw[idx:])
        if match:
            idx += match.end()
        if idx >= len(raw):
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
            accounts.append(obj)
            idx += end - idx if end > idx else 1
        except json.JSONDecodeError:
            idx += 1
    return accounts


def extract_user_info_from_token(token: str) -> dict:
    """从 access_token 或 id_token 中提取用户信息"""
    claims = _jwt_claims_no_verify(token)
    if not claims:
        return {}

    info = {}
    # 提取 chatgpt 相关信息
    auth_info = claims.get("https://api.openai.com/auth", {})
    if auth_info:
        if auth_info.get("chatgpt_account_id"):
            info["chatgpt_account_id"] = auth_info["chatgpt_account_id"]
        if auth_info.get("chatgpt_user_id"):
            info["chatgpt_user_id"] = auth_info["chatgpt_user_id"]

    # 提取 client_id
    if claims.get("client_id"):
        info["client_id"] = claims["client_id"]

    # 提取过期时间
    if claims.get("exp"):
        info["expires_at"] = claims["exp"]
        info["expires_in"] = claims["exp"] - claims.get("iat", int(time.time()))

    # 提取 organization_id
    orgs = auth_info.get("organizations", [])
    if orgs and len(orgs) > 0:
        info["organization_id"] = orgs[0].get("id", "")
    else:
        info["organization_id"] = ""

    return info


def convert_account(account: dict, index: int) -> dict:
    """将单个 codex 账号转换为 sub2api DataAccount 格式"""
    email = account.get("email", "")

    # 从 access_token 中提取用户信息
    token_info = extract_user_info_from_token(account.get("access_token", ""))

    # 构建 credentials（与参考文件格式一致）
    credentials = {}

    # access_token
    if account.get("access_token"):
        credentials["access_token"] = account["access_token"]

    # chatgpt_account_id（优先从 token 提取，然后用原始数据兜底）
    credentials["chatgpt_account_id"] = token_info.get(
        "chatgpt_account_id", account.get("account_id", "")
    )

    # chatgpt_user_id
    if token_info.get("chatgpt_user_id"):
        credentials["chatgpt_user_id"] = token_info["chatgpt_user_id"]

    # client_id
    credentials["client_id"] = token_info.get("client_id", "app_EMoamEEZ73f0CkXaXp7hrann")

    # expires_at / expires_in
    if token_info.get("expires_at"):
        credentials["expires_at"] = token_info["expires_at"]
    if token_info.get("expires_in"):
        credentials["expires_in"] = token_info["expires_in"]

    # model_mapping（codex 类型的免费账号）
    credentials["model_mapping"] = {
        "gpt-5.4": "gpt-5.4",
        "gpt-5.3-codex": "gpt-5.3-codex"
    }

    # organization_id
    credentials["organization_id"] = token_info.get("organization_id", "")

    # refresh_token（最关键的凭证）
    if account.get("refresh_token"):
        credentials["refresh_token"] = account["refresh_token"]

    # 构建 extra（email 放在这里）
    extra = {}
    if email:
        extra["email"] = email

    # 构建账号名称
    name = email if email else f"codex-account-{index + 1}"

    return {
        "name": name,
        "platform": "openai",
        "type": "oauth",
        "credentials": credentials,
        "extra": extra,
        "concurrency": 1,
        "priority": 0,
        "rate_multiplier": 1,
        "auto_pause_on_expired": True,
    }


def convert_to_sub2api(input_file: str, output_file: str):
    """主转换逻辑"""
    print(f"[*] 正在读取 {input_file}...")
    accounts = parse_accounts(input_file)
    print(f"[+] 共解析到 {len(accounts)} 个账号")

    if not accounts:
        print("[-] 没有找到任何账号数据，请检查输入文件")
        return

    # 构建 sub2api DataPayload 格式（直接导入格式，不带外层 data 包裹）
    data_accounts = []
    for i, acc in enumerate(accounts):
        converted = convert_account(acc, i)
        data_accounts.append(converted)
        print(f"  [{i + 1}] {converted['name']}")

    # 构建最终的导入数据（直接 DataPayload 格式）
    import_data = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "proxies": [],
        "accounts": data_accounts,
    }

    # 写入输出文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(import_data, f, ensure_ascii=False, indent=2)

    print(f"\n[+] 转换完成！已生成 {output_file}")
    print(f"[+] 共 {len(data_accounts)} 个账号可导入 sub2api")
    print(f"\n[*] 导入方法:")
    print(f"    1. 登录 sub2api 管理后台")
    print(f"    2. 进入「数据管理」页面")
    print(f"    3. 点击「导入数据」按钮")
    print(f"    4. 选择 {output_file} 文件上传即可")



# ====================== 并发注册 ======================
CONCURRENT_WORKERS = 3  # 并发线程数

if __name__ == "__main__":
    PROXY_URL = "http://127.0.0.1:7890"   # ← 改成你的 US/JP 住宅代理
    OUTPUT_FILE = "accounts.json"

    print("\n[*] 开始自动化并发注册 OpenAI Codex 账号...")
    print(f"[*] 并发数: {CONCURRENT_WORKERS}")
    print("[*] 停止方法: Ctrl+C\n")

    # IP 检测只做一次
    check_ip(PROXY_URL)

    counter = [0]  # 用列表包装以便在闭包中修改
    file_lock = threading.Lock()
    stop_event = threading.Event()

    def run_and_save():
        while not stop_event.is_set():
            try:
                config = run(PROXY_URL)
                if config and config.startswith("{"):
                    with file_lock:
                        counter[0] += 1
                        n = counter[0]
                        print(f"[+] 第 {n} 个账号注册成功！")
                        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                            f.write(config + "\n")
                        try:
                            convert_to_sub2api(OUTPUT_FILE, "sub2api_import.json")
                        except Exception as ce:
                            print(f"[-] 转换次级格式错误: {ce}")
                else:
                    print(f"[-] 注册未成功: {(config or '')[:200]}")
            except Exception as e:
                print(f"[-] 本次失败: {e}，3秒后重试...")
                time.sleep(3)
            # 控制提交速率，避免邮箱 API 429
            time.sleep(2)

    try:
        with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as pool:
            futures = [pool.submit(run_and_save) for _ in range(CONCURRENT_WORKERS)]
            # 阻塞等待，Ctrl+C 触发 KeyboardInterrupt
            for f in futures:
                f.result()
    except KeyboardInterrupt:
        print("\n[*] 收到 Ctrl+C，正在优雅退出...")
        stop_event.set()