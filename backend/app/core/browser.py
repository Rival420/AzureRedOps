# Browser-based authentication flows for the GUI:
#   * PKCE authorization-code flow (auth-app) with a local callback listener
#   * HAR token extraction (auth-interactive) from an uploaded session or a
#     Playwright-driven capture.
#
# Adapted from includes/Webserver.py (Mr.Un1k0d3r).

import os
import ssl
import time
import json
import base64
import hashlib
import threading
import urllib.parse
import http.server
from http import HTTPStatus

from .redops import decode_jwt, RedOpsError

WEB_DIR = os.environ.get(
    "AZUREREDOPS_WEB",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "includes", "web"),
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce():
    verifier = _b64url(os.urandom(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


class _AuthHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence default logging
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "error" in params:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            self.server.auth_result = {"error": True, "parameters": params}
            return
        code = params.get("code", [None])[0]
        if not code:
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.end_headers()
            self.server.auth_result = {"error": True, "parameters": params}
            return
        self.send_response(HTTPStatus.OK)
        self.end_headers()
        self.wfile.write(b"You may close this window. Authentication captured by AzureRedOps.")
        self.server.auth_result = {"error": False, "code": code}


class PkceCallbackServer:
    """Generates a consent URL and listens for the authorization-code redirect."""

    def __init__(self, tenant, appid, host="0.0.0.0", port=2342, endpoint="microsoftonline.com"):
        self.tenant = tenant
        self.appid = appid
        self.host = host
        self.port = port
        self.endpoint = endpoint
        self.scope = ["openid", "profile", "offline_access",
                      "https://graph.microsoft.com/.default"]
        self.redirect_url = f"https://localhost:{port}/getAuth"
        self.verifier, self.challenge = generate_pkce()

    def generate_url(self):
        url = f"https://login.{self.endpoint}/common/oauth2/v2.0/authorize"
        data = {
            "client_id": self.appid, "response_type": "code",
            "redirect_uri": self.redirect_url, "response_mode": "query",
            "scope": " ".join(self.scope), "code_challenge": self.challenge,
            "code_challenge_method": "S256",
        }
        return f"{url}?{urllib.parse.urlencode(data)}"

    def wait_for_code(self, timeout=300):
        certfile = os.path.join(WEB_DIR, "cert.pem")
        keyfile = os.path.join(WEB_DIR, "key.pem")
        if not (os.path.exists(certfile) and os.path.exists(keyfile)):
            raise RedOpsError("TLS certificate or key file missing in includes/web.")

        server = http.server.HTTPServer((self.host, self.port), _AuthHandler)
        server.auth_result = None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.timeout = 1

        def serve():
            while server.auth_result is None:
                server.handle_request()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        start = time.time()
        while server.auth_result is None and (time.time() - start) < timeout:
            time.sleep(1)
        try:
            server.server_close()
        except Exception:
            pass
        if not server.auth_result or server.auth_result.get("error"):
            raise RedOpsError("Did not receive a valid authorization code before timeout.")
        return server.auth_result["code"], self.verifier, self.redirect_url


def extract_tokens_from_har(har_text: str):
    """Parse access/refresh tokens out of a HAR file's /oauth2/v2.0/token responses."""
    tokens = []
    har = json.loads(har_text)
    for entry in har.get("log", {}).get("entries", []):
        url = entry.get("request", {}).get("url", "")
        if "/oauth2/v2.0/token" in url or "/oauth2/token" in url:
            try:
                body = json.loads(entry["response"]["content"]["text"])
            except (KeyError, ValueError):
                continue
            access_token = body.get("access_token")
            if not access_token:
                continue
            try:
                claims = decode_jwt(access_token)
            except Exception:
                continue
            tokens.append({
                "access_token": access_token,
                "refresh_token": body.get("refresh_token"),
                "username": claims.get("upn") or claims.get("unique_name"),
                "tenant_id": claims.get("tid"),
                "scope": claims.get("scp"),
                "expires": claims.get("exp"),
                "audience": claims.get("aud"),
            })
    return tokens


def playwright_interactive_capture(urls, endpoint="microsoftonline.com", delay=75, emit=None):
    """Spawn a browser, let the operator authenticate, then scrape tokens from the HAR.

    Requires a display (headed) in the container; intended for the VNC-enabled
    Playwright image. Returns a list of captured token dicts.
    """
    emit = emit or (lambda message, level="info": None)
    from playwright.sync_api import sync_playwright

    har_path = "/tmp/azureredops_session.har"
    emit(f"Spawning browser. You have {delay}s to authenticate.", "action")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.environ.get("PLAYWRIGHT_HEADLESS", "0") == "1")
        context = browser.new_context(record_har_path=har_path)
        page = context.new_page()
        page.goto(f"https://login.{endpoint}", wait_until="networkidle")
        time.sleep(delay)
        for u in [u.strip() for u in urls.split(",") if u.strip()]:
            emit(f"Redirecting to {u}", "action")
            page.goto(u, wait_until="networkidle")
            time.sleep(10)
        context.close()
        browser.close()

    with open(har_path, "r", encoding="utf-8") as handle:
        tokens = extract_tokens_from_har(handle.read())
    try:
        os.unlink(har_path)
    except OSError:
        pass
    emit(f"Captured {len(tokens)} token(s).", "success")
    return tokens
