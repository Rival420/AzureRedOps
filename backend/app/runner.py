"""Maps GUI operations to RedOpsService calls and handles token resolution."""

from sqlalchemy.orm import Session

from . import models
from .core.redops import RedOpsService, RedOpsError, decode_jwt
from .core import browser


# Activities that produce a token we may want to store in the vault.
TOKEN_PRODUCING = {"auth", "phish-capture", "refresh", "auth-app", "auth-interactive"}

# Activities that do not require an existing access token.
NO_TOKEN = {"id", "auth", "phish-start", "phish-capture", "refresh", "spray",
            "spray-refresh", "auth-app", "auth-interactive", "inspect-token"}


def resolve_access_token(params: dict, db: Session) -> str:
    token_id = params.get("token_id")
    if token_id:
        token = db.query(models.Token).get(token_id)
        if not token:
            raise RedOpsError(f"Vault token id {token_id} not found.")
        from .security import decrypt
        value = decrypt(token.enc_access_token)
        if not value:
            raise RedOpsError("Selected vault token has no access token.")
        return value
    if params.get("access_token"):
        return params["access_token"]
    raise RedOpsError("This activity requires an access token (provide token_id or access_token).")


def resolve_refresh(params: dict, db: Session):
    """Returns (refresh_token, tenant) honouring vault selection."""
    token_id = params.get("token_id")
    if token_id:
        token = db.query(models.Token).get(token_id)
        if not token:
            raise RedOpsError(f"Vault token id {token_id} not found.")
        from .security import decrypt
        return decrypt(token.enc_refresh_token), token.tenant_id
    return params.get("refresh_token"), params.get("tenant") or params.get("tenant_id")


def store_token_in_vault(db: Session, assessment_id: int, name: str, token: dict):
    from .security import encrypt
    record = models.Token(
        assessment_id=assessment_id,
        name=name,
        enc_access_token=encrypt(token.get("access_token")),
        enc_refresh_token=encrypt(token.get("refresh_token")),
        tenant_id=token.get("tenant_id"),
        username=token.get("username"),
        scope=token.get("scope"),
        audience=token.get("claims", {}).get("aud") if token.get("claims") else token.get("audience"),
        expires=token.get("expires"),
    )
    db.add(record)
    db.commit()
    return record


def execute(activity: str, params: dict, service: RedOpsService,
            db: Session, job: models.Job):
    """Dispatch a single activity. Returns a JSON-serialisable result."""
    p = params or {}

    if activity == "id":
        return service.get_tenant_id(p["tenant"])

    if activity == "inspect-token":
        return service.inspect_token(resolve_access_token(p, db))

    if activity == "auth":
        return service.auth_password(p["username"], p["password"],
                                     p.get("tenant") or p.get("tenant_id"),
                                     p.get("appid"), p.get("version", "v2.0"))

    if activity == "phish-start":
        return service.device_code_start(p.get("appid"), p.get("tenant") or p.get("tenant_id"))

    if activity == "phish-capture":
        return service.device_code_capture(p["device_code"], p.get("appid"),
                                           p.get("tenant") or p.get("tenant_id"))

    if activity == "refresh":
        refresh_token, tenant = resolve_refresh(p, db)
        return service.refresh(refresh_token, tenant, p.get("appid"), p.get("version", "v2.0"))

    if activity == "auth-app":
        server = browser.PkceCallbackServer(
            p.get("tenant") or p.get("tenant_id") or "common",
            p.get("appid", "8545b2fc-a69c-4851-9206-0f74a519fe5f"),
            port=int(p.get("port", 2342)),
            endpoint=service.microsoft_endpoint,
        )
        url = server.generate_url()
        service.success("Open this URL in your browser to authenticate:")
        service.log(url, "data")
        code, verifier, redirect_url = server.wait_for_code(int(p.get("timeout", 300)))
        service.action("Authorization code received, exchanging for tokens.")
        data = {"client_id": server.appid, "grant_type": "authorization_code", "code": code,
                "redirect_uri": redirect_url, "code_verifier": verifier,
                "scope": service.default_scope}
        response = service.http_request(
            f"https://login.{service.microsoft_endpoint}/{server.tenant}/oauth2/v2.0/token",
            data=data, send_json=False)
        return service._handle_token_response(response)

    if activity == "auth-interactive":
        tokens = browser.playwright_interactive_capture(
            p.get("url", "https://portal.azure.com"),
            endpoint=service.microsoft_endpoint,
            delay=int(p.get("delay", 75)),
            emit=service._emit,
        )
        return {"tokens": tokens}

    if activity == "spray":
        return service.spray_password(p["username"], p["password"],
                                      p.get("tenant") or p.get("tenant_id"),
                                      check_privileges=p.get("check_privileges", False))

    if activity == "spray-refresh":
        refresh_token, tenant = resolve_refresh(p, db)
        return service.spray_refresh(refresh_token, tenant,
                                     check_privileges=p.get("check_privileges", False))

    # ----- token-backed graph activities -----
    token = resolve_access_token(p, db)

    if activity == "self":
        return service.graph_self(token)
    if activity == "permission":
        return service.graph_permission(token)
    if activity == "email":
        return service.graph_read_email(token, p.get("filter", p.get("search", "")))
    if activity == "list-users":
        return service.graph_list_users(token, p.get("filter", ""))
    if activity == "list-applications":
        return service.graph_list_applications(token, p.get("filter", ""))
    if activity == "list-principals":
        return service.graph_list_principals(token)
    if activity == "gather-all":
        return service.graph_gather_all(token)
    if activity == "raw-url":
        return service.graph_raw_url(token, p["url"])
    if activity == "register-app":
        return service.graph_register_app(token, p["name"])
    if activity == "new-group":
        return service.graph_create_group(token, p["name"])
    if activity == "add-group":
        return service.graph_add_role(token, p["uid"], p.get("gid"))
    if activity == "push-file":
        return service.graph_push_file(token, p["name"], p["content"])
    if activity == "invite":
        return service.graph_invite_user(token, p["email"], p.get("url"))
    if activity == "magic-app":
        return service.graph_magic_app_finder(token)

    raise RedOpsError(f"Unknown activity '{activity}'.")
