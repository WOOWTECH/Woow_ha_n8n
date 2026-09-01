# Cloudflare Full UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish the complete Woow n8n UI, API, webhooks, and WebSocket at `https://woowtech-n8n.woowtech.io` through the existing WoowTech Cloudflare Tunnel.

**Architecture:** Keep n8n listening on plain HTTP port 5678 inside Home Assistant. Add first-class public URL/proxy settings and compatibility mirroring for old/new webhook environment variables, then route a new Cloudflare hostname to that existing origin.

**Tech Stack:** Home Assistant add-on YAML, s6-overlay/bash, n8n 2.12.3, Cloudflare Tunnel/DNS, Home Assistant Supervisor API, shell/Python validation.

---

### Task 1: Add configuration contract tests

**Files:**
- Create: `n8n/test/test-cloudflare-config.sh`
- Modify: `n8n/rootfs/etc/s6-overlay/s6-rc.d/init-keygen/run`

1. Add a test that asserts the manifest exposes `N8N_EDITOR_BASE_URL`, `N8N_WEBHOOK_URL`, and `N8N_PROXY_HOPS`.
2. Add a test harness that invokes `init-keygen/run` with mocked bashio functions and a temporary s6 environment directory.
3. Assert old-to-new and new-to-old webhook URL mirroring.
4. Run the test before implementation and confirm it fails.

### Task 2: Implement proxy configuration support

**Files:**
- Modify: `n8n/config.yaml`
- Modify: `n8n/rootfs/etc/s6-overlay/s6-rc.d/init-keygen/run`
- Modify: `n8n/translations/en.yaml`
- Modify: `n8n/translations/zh-Hant.yaml`

1. Add optional editor URL, new webhook URL, and proxy-hop settings.
2. Make the s6 environment output directory testable.
3. Mirror `WEBHOOK_URL` and `N8N_WEBHOOK_URL` without overriding explicitly different values.
4. Preserve LAN fallback behavior when neither is configured.
5. Run focused tests and shell/YAML validation.

### Task 3: Document and version the release

**Files:**
- Modify: `n8n/README.md`
- Modify: `n8n/DOCS.md`
- Modify: `n8n/CHANGELOG.md`
- Modify: `n8n/config.yaml`

1. Document full Cloudflare UI/WebSocket configuration and security boundary.
2. Bump add-on version to `2.12.6` without changing the bundled n8n version.
3. Run all repository validation.
4. Commit and push the release to `main`.

### Task 4: Configure Cloudflare

1. Re-read the shared `woowtech` Tunnel configuration and current version.
2. Insert only the new n8n hostname rule before the catch-all.
3. Create the proxied CNAME to the same tunnel.
4. Re-read both resources and verify existing routes are unchanged.

### Task 5: Deploy to Home Assistant

1. Authenticate to `https://woowtech-ha.woowtech.io` without persisting credentials.
2. Inspect the installed add-on slug, version, state, and existing options.
3. Create a backup before mutation.
4. Reload the add-on store, update/install version `2.12.6`, set public URL/proxy options, and start it.
5. Capture logs and Supervisor state.

### Task 6: End-to-end verification

1. Verify the Cloudflare hostname returns the n8n UI over HTTPS.
2. Verify secure cookies and generated public URLs.
3. Verify health, REST authentication behavior, a harmless test webhook, and WebSocket upgrade behavior.
4. Confirm the Home Assistant hostname still responds through the shared tunnel.
5. Record residual risks and rollback instructions.
