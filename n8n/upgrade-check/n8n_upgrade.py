"""The upgrade test's data check of Woow n8n (pipeline #138), rewritten from the manual test/smoke-upgrade.py.

The Store's upgrade test (Woow_HA_App_Store .addon-sync/upgrade_runtime.py)
runs `seed` on the comparison target and `verify` on the new version, on the
same data directories, from the mock Supervisor's container. Both go through
n8n's own API at ADDON_URL (n8n's port 5678), never its database:

seed     owner, an encrypted credential, an active webhook workflow (JavaScript
         and Python Code nodes), EXECUTIONS executions of it and a public API key.
verify   n8n is ready (its migrations finished), the owner logs in, the
         credential still decrypts, the encryption key is the same, the workflow
         is still active and runs, the executions are kept and the API key works.

What verify needs from seed (ids, the API key) is kept in HOOK_STATE_DIR.
Each check goes to $REPORT_DIR/<hook>.json; the hook exits 1 when one fails.
Standard library only (the hooks run on python:3.12-alpine).
"""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

OWNER = {"email": "upgrade@example.com", "firstName": "Upgrade", "lastName": "Test", "password": "UpgradeTest123!"}
CREDENTIAL = {"name": "Woow upgrade header", "type": "httpHeaderAuth",
              "data": {"name": "X-Woow-Upgrade", "value": "woow-upgrade-credential-secret"}}
WEBHOOK = "woow-upgrade"
EXECUTIONS = 5
READY_TIMEOUT = 420

JS_CODE = "return [{json: {js: [1, 2, 3].reduce((a, b) => a + b, 0), supervisor: $env.SUPERVISOR_TOKEN ?? null}}];"
PY_CODE = 'previous = _items[0]["json"]\nreturn [{"json": {**previous, "py": sum(range(10))}}]'


def workflow() -> dict[str, object]:
    """Webhook -> JavaScript Code node -> native Python Code node (as test/smoke_lib.py smoke_workflow)."""
    return {
        "name": "Woow upgrade", "active": False, "settings": {"executionOrder": "v1"},
        "nodes": [
            {"parameters": {"path": WEBHOOK, "responseMode": "lastNode", "options": {}}, "name": "Webhook",
             "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": str(uuid.uuid4())},
            {"parameters": {"jsCode": JS_CODE}, "name": "JS", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 0]},
            {"parameters": {"language": "pythonNative", "pythonCode": PY_CODE}, "name": "PY",
             "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [440, 0]},
        ],
        "connections": {"Webhook": {"main": [[{"node": "JS", "type": "main", "index": 0}]]},
                        "JS": {"main": [[{"node": "PY", "type": "main", "index": 0}]]}},
    }


class Client:
    """n8n's REST API with the owner's session cookie, and its public API with an API key."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, method: str, path: str, body: object | None = None, headers: dict[str, str] | None = None,
                timeout: float = 60) -> tuple[int, object]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})})
        try:
            with self.opener.open(req, timeout=timeout) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        except (urllib.error.URLError, OSError) as error:
            return 0, str(error)
        try:
            return status, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return status, raw.decode(errors="replace")[:300]

    def ok(self, method: str, path: str, body: object | None = None, **kw: object) -> object:
        status, payload = self.request(method, path, body, **kw)
        if not 200 <= status < 300:
            raise AssertionError(f"{method} {path} -> {status}: {str(payload)[:300]}")
        return payload["data"] if isinstance(payload, dict) and "data" in payload else payload

    def wait_ready(self) -> str:
        """n8n's readiness (database connected and migrated), then its REST routes (they can come later, n8n 2.12)."""
        deadline, last = time.monotonic() + READY_TIMEOUT, ""
        for path in ("/healthz/readiness", "/rest/settings"):
            while True:
                status, payload = self.request("GET", path, timeout=10)
                if status == 200:
                    break
                last = f"{path} -> {status} {str(payload)[:100]}"
                if time.monotonic() > deadline:
                    raise AssertionError(f"n8n not ready within {READY_TIMEOUT} s: {last}")
                time.sleep(2)
        return f"/healthz/readiness and /rest/settings answer 200"

    def login(self) -> None:
        self.ok("POST", "/rest/login", {"emailOrLdapLoginId": OWNER["email"], "password": OWNER["password"]})

    def webhook(self) -> dict[str, object]:
        deadline, last = time.monotonic() + 120, ""
        while time.monotonic() < deadline:
            status, payload = self.request("GET", f"/webhook/{WEBHOOK}")
            if status == 200:
                return payload[0] if isinstance(payload, list) else payload
            last = f"{status} {str(payload)[:200]}"
            time.sleep(2)
        raise AssertionError(f"webhook {WEBHOOK} did not answer: {last}")

    def executions(self, workflow_id: str) -> int:
        query = urllib.request.quote(json.dumps({"workflowId": workflow_id}))
        payload = self.ok("GET", f"/rest/executions?filter={query}&limit=100")
        return int(payload.get("count", len(payload.get("results", []))))


def code_nodes(result: dict[str, object]) -> str:
    assert result.get("js") == 6 and result.get("py") == 45, f"Code node results: {result}"
    assert result.get("supervisor") is None, "a workflow can read SUPERVISOR_TOKEN"
    return "JavaScript and Python Code nodes ran (js=6, py=45)"


def encryption_key_hash() -> str:
    """sha256 of n8n's encryption key in its config (in /config, the addon_config directory); never the key itself."""
    with open(os.path.join(os.environ["DATA_DIR_ADDON_CONFIG"], ".n8n/config"), encoding="utf-8") as f:
        return hashlib.sha256(json.load(f)["encryptionKey"].encode()).hexdigest()


class Checks:
    """Each check runs even when an earlier one failed, unless it needs what that one made."""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def run(self, name: str, check, needs: bool = True) -> object:
        if not needs:
            self.items.append({"name": name, "result": "skip", "detail": "an earlier check it needs failed"})
            return None
        try:
            value = check()
        except Exception as error:  # noqa: BLE001 - every failure is a failed check with its reason
            self.items.append({"name": name, "result": "fail", "detail": f"{type(error).__name__}: {error}"[:500]})
            print(f"FAIL {name}: {error}", flush=True)
            return None
        detail = value if isinstance(value, str) else "ok"
        self.items.append({"name": name, "result": "pass", "detail": detail})
        print(f"pass {name}: {detail}", flush=True)
        return value if value is not None else True

    def finish(self, hook: str) -> int:
        with open(os.path.join(os.environ["REPORT_DIR"], f"{hook}.json"), "w", encoding="utf-8") as f:
            json.dump({"checks": self.items}, f, indent=1)
        return 1 if any(c["result"] != "pass" for c in self.items) else 0


def state_path() -> str:
    return os.path.join(os.environ["HOOK_STATE_DIR"], "n8n-seed.json")


def seed() -> int:
    n8n, checks, state = Client(os.environ["ADDON_URL"]), Checks(), {}
    ready = checks.run("n8n ready", n8n.wait_ready)

    def owner_setup() -> str:
        # Returns the email even when the response data is empty, so a pass never skips what needs the owner.
        n8n.ok("POST", "/rest/owner/setup", OWNER)
        return OWNER["email"]
    owner = checks.run("owner created", owner_setup, ready)
    credential = checks.run("encrypted credential created", lambda: n8n.ok("POST", "/rest/credentials", CREDENTIAL), owner)
    created = checks.run("workflow created", lambda: n8n.ok("POST", "/rest/workflows", workflow()), owner)

    def activate() -> str:
        status, payload = n8n.request("POST", f"/rest/workflows/{created['id']}/activate", {"versionId": created["versionId"]})
        if not 200 <= status < 300:
            # n8n releases before the publish flow activated through PATCH.
            n8n.ok("PATCH", f"/rest/workflows/{created['id']}", {"active": True, "versionId": created["versionId"]})
        assert n8n.ok("GET", f"/rest/workflows/{created['id']}")["active"], "the workflow is not active"
        return "active"
    active = checks.run("workflow active", activate, bool(created))
    ran = checks.run("workflow runs", lambda: code_nodes(n8n.webhook()), bool(active))

    def executions() -> str:
        for _ in range(EXECUTIONS - 1):
            n8n.webhook()
        deadline = time.monotonic() + 30
        while (count := n8n.executions(created["id"])) < EXECUTIONS and time.monotonic() < deadline:
            time.sleep(1)
        assert count >= EXECUTIONS, f"{count} executions saved, {EXECUTIONS} expected"
        state["executions"] = count
        return f"{count} executions saved"
    checks.run("executions written", executions, bool(ran))

    def api_key() -> str:
        _status, scopes = n8n.request("GET", "/rest/api-keys/scopes")
        scope_list = scopes.get("data", []) if isinstance(scopes, dict) else []
        made = n8n.ok("POST", "/rest/api-keys", {"label": "woow-upgrade", "expiresAt": None, "scopes": scope_list})
        key = made.get("rawApiKey") or made.get("apiKey")
        assert key, f"no API key returned: {sorted(made)}"
        n8n.ok("GET", "/api/v1/workflows", headers={"X-N8N-API-KEY": key})
        state["api_key"] = key
        return f"the public API answers with it ({len(scope_list)} scopes)"
    checks.run("API key created", api_key, bool(owner))

    def key_hash() -> str:
        state["encryption_key_sha256"] = encryption_key_hash()
        return "read from /config/.n8n/config"
    checks.run("encryption key recorded", key_hash)
    if credential:
        state["credential_id"] = credential["id"]
    if created:
        state["workflow_id"] = created["id"]
    with open(state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f)
    return checks.finish("seed")


def verify() -> int:
    n8n, checks = Client(os.environ["ADDON_URL"]), Checks()

    def read_state() -> dict[str, object]:
        try:
            with open(state_path(), encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, ValueError) as error:
            raise AssertionError(f"seed state {state_path()} unreadable (did seed run?): {error}") from error
        assert isinstance(loaded, dict), f"seed state is not an object: {type(loaded).__name__}"
        return loaded
    state = checks.run("seed state readable", read_state)
    seeded = state is not None
    ready = checks.run("migrations finished (n8n ready)", n8n.wait_ready)
    owner = checks.run("owner logs in", lambda: n8n.login() or OWNER["email"], ready)

    def credential() -> str:
        # The REST API decrypts the credential and blanks only its secret fields: a wrong key fails to decrypt.
        data = n8n.ok("GET", f"/rest/credentials/{state['credential_id']}?includeData=true")["data"]
        assert data.get("name") == CREDENTIAL["data"]["name"], f"decrypted header name: {data.get('name')!r}"
        assert data.get("value"), "the secret value is gone"
        return f"decrypts (header {data['name']})"
    checks.run("encrypted credential decrypts", credential, bool(owner) and seeded)
    def same_key() -> str:
        assert encryption_key_hash() == state["encryption_key_sha256"], "the encryption key in /config/.n8n/config changed"
        return "same key in /config/.n8n/config"
    checks.run("encryption key unchanged", same_key, seeded)

    def active() -> str:
        assert n8n.ok("GET", f"/rest/workflows/{state['workflow_id']}")["active"], "the upgrade deactivated the workflow"
        return "still active"
    checks.run("workflow active", active, bool(owner) and seeded)

    def executions() -> str:
        count = n8n.executions(state["workflow_id"])
        assert count >= state["executions"], f"{count} executions, {state['executions']} before the upgrade"
        return f"{count} executions ({state['executions']} before the upgrade)"
    checks.run("executions kept", executions, bool(owner) and seeded)
    checks.run("workflow runs", lambda: code_nodes(n8n.webhook()), bool(ready))

    def api_key() -> str:
        listed = n8n.ok("GET", "/api/v1/workflows", headers={"X-N8N-API-KEY": state["api_key"]})
        ids = [w.get("id") for w in listed] if isinstance(listed, list) else []
        assert state["workflow_id"] in ids, f"the public API lists {ids}"
        return "the public API lists the workflow"
    checks.run("API key works", api_key, bool(ready) and seeded)
    return checks.finish("verify")


def main(hook: str) -> None:
    sys.exit({"seed": seed, "verify": verify}[hook]())
