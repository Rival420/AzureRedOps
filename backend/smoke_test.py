"""Offline smoke test: exercises the API end-to-end against SQLite.

Run from the backend/ directory:  python smoke_test.py
"""
import os
import time
import base64
import json

os.environ["DATABASE_URL"] = "sqlite:///./smoke.db"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "smoke-pass"
os.environ["SECRET_KEY"] = "smoke-secret"

# Point the core tool at the real bundled datasets.
os.environ["AZUREREDOPS_INCLUDES"] = os.path.abspath(os.path.join("..", "includes"))

from fastapi.testclient import TestClient
from app.main import app, on_startup

# Clean slate
if os.path.exists("smoke.db"):
    os.remove("smoke.db")
on_startup()

client = TestClient(app)
ok = 0
fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}")


# health
check("health", client.get("/api/health").json()["status"] == "ok")

# login
r = client.post("/api/auth/login", data={"username": "admin", "password": "smoke-pass"})
check("login", r.status_code == 200)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

check("bad login rejected",
      client.post("/api/auth/login", data={"username": "admin", "password": "nope"}).status_code == 401)
check("unauthed blocked", client.get("/api/assessments").status_code == 401)

# assessment CRUD
r = client.post("/api/assessments", json={"name": "Op Nightfall", "client": "ACME"}, headers=H)
check("create assessment", r.status_code == 201)
aid = r.json()["id"]
check("list assessments", len(client.get("/api/assessments", headers=H).json()) == 1)
check("patch assessment",
      client.patch(f"/api/assessments/{aid}", json={"description": "test"}, headers=H).json()["description"] == "test")
check("archive", client.post(f"/api/assessments/{aid}/archive", headers=H).json()["status"] == "archived")
check("archived filter",
      len(client.get("/api/assessments?status=archived", headers=H).json()) == 1)
check("restore", client.post(f"/api/assessments/{aid}/restore", headers=H).json()["status"] == "active")

# catalog
cat = client.get("/api/catalog", headers=H).json()
n_ops = sum(len(g["operations"]) for g in cat)
check("catalog has operations", n_ops >= 20)

# reference (bundled data)
ref = client.get("/api/reference/known-ids?search=azure&limit=5", headers=H).json()
check("reference known-ids", ref["total"] > 0 and len(ref["items"]) <= 5)
cats = client.get("/api/reference/interest/categories", headers=H).json()
check("reference categories", any(c["category"] == "v0" for c in cats))

# token vault (use a synthetic unsigned JWT)
def make_jwt(claims):
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg':'none','typ':'JWT'})}.{seg(claims)}.sig"

jwt_token = make_jwt({"upn": "victim@acme.com", "tid": "tenant-123",
                      "scp": "User.Read", "aud": "https://graph.microsoft.com",
                      "exp": int(time.time()) + 3600})
r = client.post(f"/api/assessments/{aid}/tokens",
                json={"name": "victim-graph", "access_token": jwt_token,
                      "refresh_token": "refresh-abc"}, headers=H)
check("add vault token", r.status_code == 201 and r.json()["username"] == "victim@acme.com")
tid = r.json()["id"]
check("token not expired", r.json()["is_expired"] is False)
reveal = client.get(f"/api/assessments/{aid}/tokens/{tid}/reveal", headers=H).json()
check("reveal decrypts token", reveal["access_token"] == jwt_token)
check("reveal refresh", reveal["refresh_token"] == "refresh-abc")

# run a job that needs no network: inspect-token via the vault token
r = client.post(f"/api/assessments/{aid}/operations",
                json={"activity": "inspect-token", "params": {"token_id": tid}}, headers=H)
check("launch job", r.status_code == 202)
jid = r.json()["id"]

# poll for completion
final = None
for _ in range(50):
    job = client.get(f"/api/jobs/{jid}", headers=H).json()
    if job["status"] in ("completed", "failed", "cancelled"):
        final = job
        break
    time.sleep(0.2)
check("job completed", final and final["status"] == "completed")
check("job result has claims", final and final["result"].get("upn") == "victim@acme.com")
logs = client.get(f"/api/jobs/{jid}/logs", headers=H).json()
check("job produced logs", len(logs) > 0)

# a failing job (missing token) should fail gracefully, not crash
r = client.post(f"/api/assessments/{aid}/operations",
                json={"activity": "self", "params": {}}, headers=H)
jid2 = r.json()["id"]
final2 = None
for _ in range(50):
    job = client.get(f"/api/jobs/{jid2}", headers=H).json()
    if job["status"] in ("completed", "failed", "cancelled"):
        final2 = job
        break
    time.sleep(0.2)
check("missing-token job fails cleanly", final2 and final2["status"] == "failed" and final2["error"])

print(f"\n{ok} passed, {fail} failed")
os.remove("smoke.db")
raise SystemExit(1 if fail else 0)
