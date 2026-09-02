# Ingress Transform Cache Coherence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent browsers and Cloudflare from storing transformed HA Ingress HTML/JS/CSS under unchanged n8n asset hashes.

**Architecture:** Map upstream content types to ingress cache policy: no-store for transformed HTML/JavaScript/CSS, preserve upstream caching for unmodified types. Keep direct port 5678 unchanged, deploy 2.12.15, then request approval for one prefix purge.

**Tech Stack:** nginx maps/headers, Python real-nginx tests, Playwright, Home Assistant Supervisor, Cloudflare Cache API.

---

### Task 1: Add a failing cache-policy regression

**Files:**
- Modify: `n8n/test/test-ingress-nginx.py`

Extend the backend fixture so HTML, JavaScript, CSS, and a binary resource all return `Cache-Control: public, max-age=86400`. Through real ingress nginx assert HTML/JS/CSS are `no-store`, while the binary response retains `public, max-age=86400`. Request the backend directly and assert its headers are unchanged.

Run before implementation:

```bash
python n8n/test/test-ingress-nginx.py
```

Expected RED: transformed responses still return public max-age.

### Task 2: Implement conditional ingress cache policy

**Files:**
- Modify: `n8n/rootfs/etc/nginx/nginx.conf`
- Modify: `n8n/test/test-cloudflare-config.sh`

Add an `http`-level map from `$upstream_http_content_type` to an ingress cache value:

- `text/html` → `no-store`
- JavaScript MIME types → `no-store`
- `text/css` → `no-store`
- default → `$upstream_http_cache_control`

In the ingress proxy location hide upstream `Cache-Control` and emit the mapped header with `always`. Do not modify the direct n8n listener, asset URLs, ETags, or body transforms.

Run GREEN:

```bash
bash n8n/test/test-cloudflare-config.sh
python n8n/test/test-ingress-nginx.py
python n8n/test/test-ingress-preload-dedup.py
```

### Task 3: Version and document 2.12.15

**Files:**
- Modify: `n8n/config.yaml`
- Modify: `n8n/CHANGELOG.md`
- Modify: `n8n/README.md`

Document the unchanged-hash/transformed-body cache mismatch, no-store policy for transformed types, preserved caching for other assets, required one-time ingress prefix purge, browser hard refresh, and rollback to 2.12.14. Keep n8n/runners at 2.12.3.

Run all source checks, Python compilation, nginx syntax, release metadata, and `git diff --check`.

### Task 4: Independent review and publication

Run fresh spec and quality reviews. Commit, push, and merge a source PR, then synchronize the complete `n8n/` directory to `Woow_HA_App_Store`, update its version table, rerun tests, and merge a store PR.

### Task 5: Backup and deploy

Create a named partial add-on backup, reload the store, confirm 2.12.15, update, and verify state, health, n8n 2.12.3, nginx checksum, preload rewrite, no old frame script, and WebSocket 101.

### Task 6: Cloudflare purge approval gate

Before mutating Cloudflare, tell the user exactly:

- endpoint: zone cache purge;
- scope: prefix `woowtech-ha.woowtech.io/api/hassio_ingress`;
- effect: remove cached HA ingress objects in all Cloudflare data centers; ordinary HA frontend and direct n8n hostname stay cached;
- consequence: temporary origin refetch for add-on ingress assets;
- rollback: no content change, cache repopulates automatically.

Only after explicit approval, resolve the `woowtech.io` zone ID and execute the prefix purge via Cloudflare MCP.

### Task 7: Live validation

After purge, verify the helper response is prefix-aware and `Cache-Control: no-store` without stale `CF-Cache-Status: HIT`. Run the eight authenticated RWD viewports and Cloudflare Browser Rendering snapshot. Require native host/iframe sizing, child viewport equality, full n8n app height, one BaseLayout stylesheet, no duplicate CSS, no old script, and no failed CSS/JS requests. Store token-redacted artifacts under `/tmp/ha-n8n-live-rwd-2.12.15/`.

**Rollback:** Restore the pre-2.12.15 partial backup to return to 2.12.14. Cache objects repopulate automatically; n8n data remains compatible.
