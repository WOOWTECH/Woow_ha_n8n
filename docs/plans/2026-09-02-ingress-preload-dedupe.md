# n8n Ingress Preload De-duplication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop n8n 2.12.3 from appending duplicate preload/CSS links under Home Assistant Ingress so `#n8n-app` fills every viewport naturally.

**Architecture:** On ingress nginx port 5690, rewrite the pinned Vite preload URL builder to use the already-prefixed `window.BASE_PATH`. Remove the misdirected 2.12.13 outer-frame workaround. Preserve direct port 5678 and Cloudflare behavior.

**Tech Stack:** Home Assistant add-on YAML, nginx `sub_filter`, n8n/Vite JavaScript, Python HTTP fixtures, Playwright Chromium, GitHub, Home Assistant Supervisor CLI.

---

### Task 1: Build a red-capable preload/cascade regression

**Files:**
- Create: `n8n/test/test-ingress-preload-dedup.py`
- Reuse: `n8n/rootfs/etc/nginx/nginx.conf`

**Step 1: Gate the version-specific fixture and create a real-nginx fixture**

Before starting nginx or accepting the exact helper fixture, require all supported upstream references to remain at n8n 2.12.3: Dockerfile `BUILD_FROM`, the Dockerfile runner stage, `build.yaml` aarch64 and amd64 images, and `addon_info.yaml` `current_version`. Emit a deliberate seam-review failure if any pin changes; do not derive the expected fixture version from those files.

Start a local backend that serves:

- `/signin`: initial BaseLayout stylesheet, index stylesheet, `window.BASE_PATH = '/'`, the preload helper module, and a Vue-like `#app > #n8n-app` element;
- `/assets/BaseLayout.css`: `.appGrid { height: 100%; }`;
- `/assets/index.css`: `.app { height: 100vh; }` plus full-height `html/body`;
- `/assets/preload.js`: the pinned n8n helper seam `hee=function(e){return\`/\`+e}` and its native duplicate-link test, invoked for `assets/BaseLayout.css`.

Run the repository nginx config on a temporary port with only listener/upstream/log/alias paths adapted for the test. Put a small front proxy before nginx that simulates Supervisor: it accepts the token-prefixed browser URL, strips `/api/hassio_ingress/<token>`, and adds `X-Ingress-Path`.

**Step 2: Assert the user-visible contract**

At a 1440×900 browser viewport require:

- exactly one BaseLayout stylesheet;
- no duplicate stylesheet hrefs;
- `#n8n-app` height approximately 900px;
- the preload helper response contains the prefix-aware builder;
- no failed CSS/JS requests or page errors.

Load the backend directly and require the same one-stylesheet/full-height result, proving root-path behavior remains valid.

**Step 3: Run RED**

```bash
python n8n/test/test-ingress-preload-dedup.py
```

Expected before implementation: FAIL because ingress has two BaseLayout stylesheets and app height resolves to the fixture's natural content height instead of 900px.

### Task 2: Implement the minimal ingress preload rewrite

**Files:**
- Modify: `n8n/rootfs/etc/nginx/nginx.conf`
- Modify: `n8n/test/test-cloudflare-config.sh`
- Delete: `n8n/rootfs/etc/nginx/ingress-frame-height.js`
- Delete: `n8n/test/test-ingress-frame-height.py`
- Modify: `n8n/test/test-ingress-nginx.py`

**Step 1: Add the exact pinned rewrite**

Inside the ingress proxy location add one exact `sub_filter` that rewrites:

```text
hee=function(e){return`/`+e}
```

into:

```text
hee=function(e){return(window.BASE_PATH||`/`)+e}
```

Do not patch generic DOM APIs or remove links after load.

**Step 2: Remove the outer-height workaround**

Remove:

- `/_woow/ingress-frame-height.js` nginx location;
- the injected frame-height script tag;
- its production JavaScript file;
- its dedicated Playwright test.

Keep the existing base-path fetch/XHR/history/WebSocket/lazy-asset adapter unchanged except for the new preload builder rewrite.

**Step 3: Update static and nginx tests**

Require the exact preload rewrite and reject the old height-script location/tag. Update `test-ingress-nginx.py` to confirm:

- normal ingress HTML still gets base/runtime injection;
- JavaScript containing the pinned helper is returned with `window.BASE_PATH` logic;
- no frame-height resource is exposed;
- nginx absence remains a hard test failure.

**Step 4: Run GREEN**

```bash
bash n8n/test/test-cloudflare-config.sh
python n8n/test/test-ingress-nginx.py
python n8n/test/test-ingress-preload-dedup.py
```

Expected: all pass, with one BaseLayout stylesheet and 900px ingress/direct app heights.

### Task 3: Version and document release 2.12.14

**Files:**
- Modify: `n8n/config.yaml`
- Modify: `n8n/CHANGELOG.md`
- Modify: `n8n/README.md`
- Keep: `n8n/Dockerfile`, `n8n/build.yaml`

**Step 1: Bump only the add-on version**

Change `2.12.13` to `2.12.14`. Keep n8n and runners at 2.12.3.

**Step 2: Document the real cause**

Record:

- preload helper root-path duplicate detection versus token-prefixed initial links;
- duplicate BaseLayout CSS overriding `100vh` with `100%`;
- removal of the incorrect frame-height workaround;
- direct 5678 non-impact;
- rollback to the pre-update backup.

**Step 3: Run complete source verification**

```bash
bash n8n/test/test-cloudflare-config.sh
python n8n/test/test-ingress-nginx.py
python n8n/test/test-ingress-preload-dedup.py
node --check n8n/rootfs/etc/nginx/nginx.conf 2>/dev/null || true
python -m py_compile n8n/test/test-ingress-nginx.py n8n/test/test-ingress-preload-dedup.py
python - <<'PY'
import pathlib, yaml
root = pathlib.Path('n8n')
config = yaml.safe_load((root / 'config.yaml').read_text())
assert config['version'] == '2.12.14'
dockerfile = (root / 'Dockerfile').read_text()
assert 'ARG BUILD_FROM=docker.io/n8nio/n8n:2.12.3' in dockerfile
assert 'FROM docker.io/n8nio/runners:2.12.3 AS runner' in dockerfile
build = yaml.safe_load((root / 'build.yaml').read_text())['build_from']
assert build == {
    'aarch64': 'docker.io/n8nio/n8n:2.12.3',
    'amd64': 'docker.io/n8nio/n8n:2.12.3',
}
addon_info = yaml.safe_load((root / 'addon_info.yaml').read_text())
assert addon_info['source']['current_version'] == 'n8n@2.12.3'
print('release metadata checks passed')
PY
git diff --check
```

Remove generated `__pycache__` before review.

### Task 4: Independent review and source publication

**Files/Branch:**
- Branch: `fix/ingress-preload-dedupe`
- Design: `docs/plans/2026-09-02-ingress-preload-dedupe-design.md`
- Plan: `docs/plans/2026-09-02-ingress-preload-dedupe.md`

**Step 1: Spec review**

A fresh reviewer checks every plan requirement and confirms no symptom-only CSS override or direct-port change was introduced.

**Step 2: Quality review**

A separate fresh reviewer examines exact-string brittleness, nginx response scope, preload helper semantics, fixture sensitivity, direct-route isolation, and future-upgrade failure behavior.

**Step 3: Fix accepted findings and re-review**

Use one writer. Repeat review until no fixes worth doing now remain.

**Step 4: Commit, push, PR, and merge**

```bash
git add docs/plans/2026-09-02-ingress-preload-dedupe*.md n8n
git commit -m "fix: deduplicate n8n ingress preloads"
git push -u origin fix/ingress-preload-dedupe
```

Open and merge a reviewed PR into `WOOWTECH/Woow_ha_n8n:main`.

### Task 5: Synchronize Woow_HA_App_Store

**Files:**
- Replace: `Woow_HA_App_Store/n8n/`
- Modify: `Woow_HA_App_Store/README.md` version table

Copy the complete merged source directory with deletion semantics, verify exact directory parity, run all three tests in the store checkout, then commit and merge a focused sync PR.

### Task 6: Backup and deploy

**Resources:**
- HA SSH: `woowtech-ssh.woowtech.io`
- Add-on: `1b7b4ce7_woow-n8n`

**Step 1: Record pre-deploy state**

Whitelist version/state/image/checksums only. Redact options, tokens, cookies, and credentials.

**Step 2: Create a partial add-on backup**

Create a named pre-2.12.14 backup and retain its slug privately.

**Step 3: Reload store and update**

Confirm 2.12.14 is offered, update, and wait for `started` plus health 200.

**Step 4: Verify deployed bytes and transport**

Confirm source/runtime nginx checksums match, n8n remains 2.12.3, direct Cloudflare has no ingress injection, ingress assets return 200, and `/rest/push` upgrades with 101.

### Task 7: Live Cloudflare and authenticated RWD validation

Use Cloudflare Browser Rendering MCP for a public edge snapshot and authenticated local Playwright for HA form login without embedding credentials in Cloudflare request scripts.

Test:

- 1920×1080
- 1440×900
- 1280×720
- 1024×768
- 768×1024
- 430×932
- 390×844
- 360×800

At every viewport require:

- `ha-panel-app` host height equals outer viewport;
- HA iframe height follows native HA desktop/mobile header rules;
- child viewport equals iframe content height;
- `#n8n-app` equals child viewport;
- exactly one BaseLayout stylesheet;
- zero duplicate stylesheet hrefs;
- no failed CSS/JS requests;
- preload helper does not append an existing initial BaseLayout link.

Capture screenshots and a token-redacted JSON result under `/tmp/ha-n8n-live-rwd-2.12.14/`.

**Rollback:** Restore the named pre-2.12.14 partial backup, returning to 2.12.13. No n8n database migration or runner version change is involved.
