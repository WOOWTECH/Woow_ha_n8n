# HA Ingress Full-Height Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Woow n8n editor fill the complete Home Assistant `/app/<addon>` panel height without changing the direct Cloudflare editor.

**Architecture:** Keep n8n rooted at `/` on port 5678. Add one ingress-only JavaScript resource served by nginx on port 5690 and inject it into proxied HTML. The script runs only when its frame is hosted by Home Assistant's `ha-panel-app`, sets that host to the dynamic viewport height, keeps the iframe at 100%, and emits one resize after an actual correction.

**Tech Stack:** Home Assistant add-on YAML, nginx, browser JavaScript, Bash/Python tests, Playwright Chromium, GitHub, Home Assistant Supervisor CLI.

---

### Task 1: Add a red browser regression test

**Files:**
- Create: `n8n/test/test-ingress-frame-height.py`

**Step 1: Write the failing test**

Create a Playwright test harness that reproduces a `ha-panel-app` host at 40% of an 857px viewport, loads the production JavaScript file into the child iframe, and requires all of the following:

- baseline child viewport is approximately 343px;
- corrected host, iframe, and child viewport are 857px;
- executing the script as a top-level direct page is a no-op;
- no browser page errors occur.

**Step 2: Run it to verify RED**

Run:

```bash
python n8n/test/test-ingress-frame-height.py
```

Expected: FAIL because `n8n/rootfs/etc/nginx/ingress-frame-height.js` does not exist.

### Task 2: Implement the ingress-only frame-height adapter

**Files:**
- Create: `n8n/rootfs/etc/nginx/ingress-frame-height.js`
- Modify: `n8n/rootfs/etc/nginx/nginx.conf`
- Modify: `n8n/test/test-cloudflare-config.sh`

**Step 1: Add the minimal browser adapter**

Implement a plain IIFE that:

1. returns immediately when `window.frameElement` is absent;
2. obtains the iframe shadow-root host;
3. returns unless the host is `ha-panel-app`;
4. sets the host height to `100dvh` when supported, otherwise `100vh`;
5. sets the frame height to `100%`;
6. emits a child `resize` only when styles changed;
7. re-applies on `pageshow`, child resize, and parent resize;
8. observes iframe size changes with `ResizeObserver` when available.

**Step 2: Serve and inject it only through port 5690**

Add an exact nginx location for `/_woow/ingress-frame-height.js`, served from `/etc/nginx/ingress-frame-height.js` with JavaScript content type and `Cache-Control: no-store`. Add a second script tag to the existing ingress `</head>` substitution using the validated `$safe_ingress_path`. Do not modify port 5678 or n8n's public root path.

**Step 3: Extend static configuration checks**

Assert that the JavaScript source exists and contains the `ha-panel-app`, `100dvh`, direct-page guard, and resize logic. Assert that nginx exposes the exact ingress-only location and injects the token-prefixed script URL.

**Step 4: Run RED→GREEN verification**

Run:

```bash
bash n8n/test/test-cloudflare-config.sh
python n8n/test/test-ingress-frame-height.py
```

Expected: both pass; browser report shows baseline near 343px and corrected dimensions at 857px.

### Task 3: Version and document the release

**Files:**
- Modify: `n8n/config.yaml`
- Modify: `n8n/CHANGELOG.md`
- Modify: `n8n/README.md`

**Step 1: Bump add-on version**

Change the add-on version from `2.12.12` to `2.12.13`. Keep bundled n8n and runners pinned to `2.12.3`.

**Step 2: Document behavior and rollback**

Add a changelog entry describing the confirmed Home Assistant App-panel height collapse, the ingress-only frame correction, the direct-port non-impact, and Playwright evidence. Briefly document that the direct Cloudflare UI remains unchanged.

**Step 3: Run complete source verification**

Run:

```bash
bash n8n/test/test-cloudflare-config.sh
python n8n/test/test-ingress-frame-height.py
python n8n/test/test-ingress-nginx.py
python - <<'PY'
import pathlib, yaml
root = pathlib.Path('n8n')
config = yaml.safe_load((root / 'config.yaml').read_text())
assert config['version'] == '2.12.13'
assert 'n8nio/n8n:2.12.3' in (root / 'Dockerfile').read_text()
assert 'n8nio/runners:2.12.3' in (root / 'Dockerfile').read_text()
print('release metadata checks passed')
PY
```

Expected: all pass.

### Task 4: Review and publish the source release

**Files:**
- Source repository branch: `fix/ingress-full-height`

**Step 1: Inspect the complete diff**

Verify there are no unrelated changes and no secrets or generated browser artifacts.

**Step 2: Commit and push**

```bash
git add docs/plans/2026-09-02-ingress-full-height.md n8n
git commit -m "fix: fill Home Assistant ingress viewport"
git push -u origin fix/ingress-full-height
```

**Step 3: Open, independently review, and merge a PR**

Require a fresh-context correctness review focused on recursion, iframe isolation, direct-route non-impact, nginx routing, and regression tests. Apply any accepted fixes with one writer, re-run verification, then merge the PR.

### Task 5: Synchronize the meta app store

**Files:**
- Replace: `Woow_HA_App_Store/n8n/` from the merged `Woow_ha_n8n/n8n/`
- Modify if needed: `Woow_HA_App_Store/README.md`

**Step 1: Copy the complete verified add-on directory**

Use deletion-aware synchronization so stale files cannot remain.

**Step 2: Verify source/store parity**

```bash
diff -ru --exclude test Woow_ha_n8n/n8n Woow_HA_App_Store/n8n
```

Expected: no differences, except any explicitly documented store-only metadata.

**Step 3: Commit, push, and merge the store PR**

Use a focused sync commit and verify the store YAML parses before merge.

### Task 6: Back up, deploy, and verify Home Assistant

**Files/Resources:**
- HA host: `woowtech-ssh.woowtech.io`
- Add-on: `1b7b4ce7_woow-n8n`

**Step 1: Capture pre-deploy state**

Record HAOS/Core/Supervisor versions, installed add-on version/state/options whitelist, container image, and current nginx checksum. Do not expose tokens, cookies, credentials, or full options.

**Step 2: Create a Home Assistant backup**

Create a named pre-`2.12.13` backup and record its slug privately for rollback.

**Step 3: Reload the store and update the add-on**

Reload Supervisor store metadata, confirm `2.12.13` is offered, update the n8n add-on, and wait for `started` plus healthy watchdog status.

**Step 4: Verify the deployed artifact**

Confirm:

- add-on version is `2.12.13`;
- n8n remains `2.12.3`;
- nginx serves `/_woow/ingress-frame-height.js` through the Supervisor source path;
- ingress HTML injects the token-prefixed script;
- direct Cloudflare HTML does not contain the script;
- `/healthz` is 200;
- `/rest/push` can still upgrade;
- no new nginx errors, 404 asset failures, or 5xx responses appear.

**Step 5: User-visible validation**

Reload the HA App panel with cache bypass. The n8n sidebar and application grid must extend to the bottom of the available panel. If it does not, collect the live parent host/iframe/child viewport dimensions before attempting another fix.

**Rollback:** Restore add-on `2.12.12` from the pre-deploy backup or prior source version, retaining the unchanged n8n 2.12.3 data directory.
