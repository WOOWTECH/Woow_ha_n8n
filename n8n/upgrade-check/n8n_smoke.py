"""The regression comparison of Woow n8n (pipeline #139), rewritten from test/smoke-container.py.

The Store's upgrade test (Woow_HA_App_Store .addon-sync/upgrade_runtime.py)
runs `smoke` on the comparison target (after seed) and on the new version
(after verify), from the mock Supervisor's container, and compares the checks
by name: a check that passes on the comparison target must pass on the new
version. So every check keeps its name across versions.

smoke-container.py drives its own container; this hook can only reach the
add-on from the Supervisor's address and read its data directories, so it
keeps the checks that can be seen from there:

  n8n is ready; the watchdog answers healthy to the Supervisor; ingress serves
  the editor under the ingress path (<base>, asset URLs, BASE_PATH, the
  rewritten preload builder); no Content-Security-Policy; the owner signs in;
  a webhook workflow runs a JavaScript and a native Python Code node in the
  task runners, and neither can read the Supervisor or task broker token; the
  task broker and Redis refuse connections from the network; the task broker
  token is a root-only file that is not the default.

What needs `docker exec`, the add-on's log or a restart (processes and their
environments, secrets in the log, system Python, the browser check, the token
across a restart) stays in smoke-container.py, which CI runs on every build.
The workflow it creates is its own per version (webhook woow-smoke-<PHASE>),
so it never touches what seed wrote and verify reads back.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import time
import urllib.error
import urllib.request
import uuid

from n8n_upgrade import OWNER, Checks, Client

INGRESS_PATH = "/api/hassio_ingress/abcdefghijklmnop0123"
# Ports that must listen on loopback only (smoke-container.py check_listeners).
LOOPBACK_ONLY = {"task broker": 5679, "Redis": 6379}

JS_CODE = """return [{json: {
  js: [1, 2, 3].reduce((a, b) => a + b, 0),
  supervisor: $env.SUPERVISOR_TOKEN ?? null,
  hassio: $env.HASSIO_TOKEN ?? null,
  broker: $env.N8N_RUNNERS_AUTH_TOKEN ?? null,
}}];"""
PY_CODE = """import os
previous = _items[0]["json"]
return [{"json": {**previous, "py": sum(range(10)),
                  "pySupervisor": os.environ.get("SUPERVISOR_TOKEN"),
                  "pyHassio": os.environ.get("HASSIO_TOKEN"),
                  "pyBroker": os.environ.get("N8N_RUNNERS_AUTH_TOKEN")}}]"""
# The token fields each Code node returns: all must be None.
TOKEN_FIELDS = ("supervisor", "hassio", "broker", "pySupervisor", "pyHassio", "pyBroker")


def workflow(path: str) -> dict[str, object]:
    """Webhook -> JavaScript Code node -> native Python Code node (test/smoke_lib.py smoke_workflow)."""
    return {
        "name": f"Woow smoke {path}", "active": False, "settings": {"executionOrder": "v1"},
        "nodes": [
            {"parameters": {"path": path, "responseMode": "lastNode", "options": {}}, "name": "Webhook",
             "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": str(uuid.uuid4())},
            {"parameters": {"jsCode": JS_CODE}, "name": "JS", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 0]},
            {"parameters": {"language": "pythonNative", "pythonCode": PY_CODE}, "name": "PY",
             "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [440, 0]},
        ],
        "connections": {"Webhook": {"main": [[{"node": "JS", "type": "main", "index": 0}]]},
                        "JS": {"main": [[{"node": "PY", "type": "main", "index": 0}]]}},
    }


def fetch(url: str, headers: dict[str, str] | None = None) -> tuple[int, str, set[str]]:
    """(status, body, lower-case header names) of a GET; status 0 when nothing answers. Unlike Client.request, the
    body is whole: the editor's HTML and bundles are checked in full."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as response:
            return response.status, response.read().decode(errors="replace"), {k.lower() for k in response.headers.keys()}
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace"), {k.lower() for k in error.headers.keys()}
    except (urllib.error.URLError, OSError) as error:
        return 0, str(error), set()


def ingress_port() -> int:
    """The ingress port the Supervisor reports for this version (/addons/self/info)."""
    supervisor = Client(os.environ["SUPERVISOR_URL"])
    info = supervisor.ok("GET", "/addons/self/info", headers={"Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"]})
    return int(info["ingress_port"])


def smoke() -> int:
    n8n, checks, state = Client(os.environ["ADDON_URL"]), Checks(), {}
    host = os.environ["ADDON_HOST"]
    ready = checks.run("n8n ready", n8n.wait_ready)
    port = checks.run("ingress port reported", ingress_port)

    def watchdog() -> str:
        status, body, _ = fetch(f"http://{host}:{port}/_woow/watchdog")
        try:
            healthy = json.loads(body) == {"status": "ok"}
        except ValueError:
            healthy = False
        assert status == 200 and healthy, f"watchdog -> {status} {body[:200]}"
        return "200 {\"status\":\"ok\"} to the Supervisor"
    checks.run("watchdog healthy", watchdog, bool(ready) and bool(port))

    def ingress_get(path: str) -> str:
        status, body, _ = fetch(f"http://{host}:{port}{path}", {"X-Ingress-Path": INGRESS_PATH})
        assert status == 200, f"ingress {path} -> {status} {body[:200]}"
        return body

    def signin() -> str:
        html = ingress_get("/signin")
        assert f'<base href="{INGRESS_PATH}/">' in html, "ingress <base> not injected"
        assert f'src="{INGRESS_PATH}/assets/' in html, "asset URLs not prefixed"
        state["html"] = html
        return "<base> and asset URLs carry the ingress path"
    page = checks.run("ingress serves the editor", signin, bool(ready) and bool(port))

    def base_path() -> str:
        script = ingress_get("/static/base-path.js").strip()
        assert script == f"window.BASE_PATH = '{INGRESS_PATH}/';", script[:200]
        return script
    checks.run("ingress sets BASE_PATH", base_path, bool(page))

    def preload_builder() -> str:
        html = str(state["html"])
        app = next((part.split('"')[0] for part in html.split(f'href="{INGRESS_PATH}/assets/')[1:]
                    if part.startswith("app-") and '.js"' in part.split(">")[0]), None)
        assert app, "no app-*.js bundle linked from /signin"
        script = ingress_get(f"/assets/{app}")
        assert script.count("function(e){return(window.BASE_PATH||`/`)+e}") == 1, "preload builder not rewritten in the served app bundle"
        assert "function(e){return`/`+e}" not in script, "the served app bundle still has the root preload builder"
        return f"rewritten once in {app}"
    checks.run("ingress rewrites the preload builder", preload_builder, bool(page))

    def no_csp() -> str:
        status, _, headers = fetch(os.environ["ADDON_URL"] + "/signin")
        assert status == 200, f"/signin -> {status}"
        assert "content-security-policy" not in headers, (
            "n8n now enforces a Content-Security-Policy; the inline ingress shim and <base> would be blocked under Ingress")
        return "none on /signin"
    checks.run("no Content-Security-Policy", no_csp, bool(ready))

    def owner() -> str:
        # seed made the owner before smoke runs on either version; never set one up here, or a new version
        # that lost the owner would still pass.
        status, payload = n8n.request("POST", "/rest/login", {"emailOrLdapLoginId": OWNER["email"], "password": OWNER["password"]})
        assert 200 <= status < 300, f"login -> {status} {str(payload)[:200]}"
        return "logged in"
    signed_in = checks.run("owner signs in", owner, bool(ready))

    def code_nodes() -> dict[str, object]:
        path = f"woow-smoke-{os.environ['PHASE']}"
        made = n8n.ok("POST", "/rest/workflows", workflow(path))
        status, _ = n8n.request("POST", f"/rest/workflows/{made['id']}/activate", {"versionId": made["versionId"]})
        if not 200 <= status < 300:
            # n8n releases before the publish flow activated through PATCH.
            n8n.ok("PATCH", f"/rest/workflows/{made['id']}", {"active": True, "versionId": made["versionId"]})
        deadline, last = time.monotonic() + 120, ""
        while time.monotonic() < deadline:
            status, payload = n8n.request("GET", f"/webhook/{path}")
            if status == 200:
                result = payload[0] if isinstance(payload, list) else payload
                assert result.get("js") == 6 and result.get("py") == 45, f"Code node results: {result}"
                state["result"] = result
                return "JavaScript and Python Code nodes ran (js=6, py=45)"
            last = f"{status} {str(payload)[:200]}"
            time.sleep(2)
        raise AssertionError(f"webhook {path} did not answer: {last}")
    ran = checks.run("Code nodes run", code_nodes, bool(signed_in))

    def hidden_tokens() -> str:
        result = state["result"]
        missing = [k for k in TOKEN_FIELDS if k not in result]
        assert not missing, f"the Code nodes did not report {missing}"
        visible = [k for k in TOKEN_FIELDS if result[k] is not None]
        assert not visible, f"a workflow can read {visible}"
        return "SUPERVISOR_TOKEN, HASSIO_TOKEN and N8N_RUNNERS_AUTH_TOKEN are hidden from both Code nodes"
    checks.run("workflows cannot read tokens", hidden_tokens, bool(ran))

    def loopback_only() -> str:
        # Only a refused connection proves nothing listens there: a timeout or another error proves nothing.
        ports = ", ".join(f"{name} ({number})" for name, number in LOOPBACK_ONLY.items())
        problems = []
        for name, number in LOOPBACK_ONLY.items():
            try:
                socket.create_connection((host, number), timeout=5).close()
                problems.append(f"{name} ({number}) is reachable from the network")
            except ConnectionRefusedError:
                pass
            except OSError as error:
                problems.append(f"{name} ({number}) did not refuse the connection: {error}")
        assert not problems, "; ".join(problems)
        return f"{ports} refuse connections from the Supervisor's address"
    checks.run("task broker and Redis on loopback only", loopback_only, bool(ready))

    def broker_token() -> str:
        path = os.path.join(os.environ["DATA_DIR_DATA"], "n8n-runners-auth-token")
        info = os.stat(path)
        assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == 0, f"{oct(stat.S_IMODE(info.st_mode))} uid {info.st_uid}"
        with open(path, encoding="utf-8") as f:
            token = f.read().strip()
        assert len(token) == 64 and token != "n8n-runner", "the task broker token is the default or not 64 characters"
        return f"{path} is 600 root, 64 characters, not the default"
    checks.run("task broker token is root-only and not the default", broker_token, bool(ready))
    return checks.finish("smoke")
