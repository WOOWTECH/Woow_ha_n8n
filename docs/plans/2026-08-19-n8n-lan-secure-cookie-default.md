# n8n LAN Secure Cookie Default Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Make the Woow n8n Home Assistant add-on usable over its documented LAN HTTP URL by default while retaining an explicit HTTPS-safe override.

**Architecture:** Add `N8N_SECURE_COOKIE` as a first-class boolean add-on option defaulting to `false`. The existing generic option loader will export it into the n8n runtime; HTTPS deployments can set it to `true`. Bump the add-on revision, document the security trade-off, sync the complete add-on directory to `Woow_HA_App_Store`, then update and verify the target host.

**Tech Stack:** Home Assistant add-on YAML, s6-overlay option loader, n8n environment variables, Git/GitHub, Supervisor CLI/API.

---

### Task 1: Update the source add-on

**Files:**
- Modify: `n8n/config.yaml`
- Modify: `n8n/translations/en.yaml`
- Modify: `n8n/translations/zh-Hant.yaml`
- Modify: `n8n/README.md`
- Modify: `n8n/CHANGELOG.md`

1. Add `N8N_SECURE_COOKIE: bool` to the schema and default it to `false`.
2. Bump version from `2.12.3` to `2.12.3-v1`; the Dockerfile already strips the `-v*` add-on revision when selecting the upstream runner image.
3. Document that LAN HTTP defaults to `false`, while HTTPS deployments should set it to `true`.
4. Add translated configuration labels.
5. Validate YAML parsing and assert schema/default/version values.
6. Commit and push `WOOWTECH/Woow_ha_n8n`.

### Task 2: Synchronize Woow_HA_App_Store

**Files:**
- Replace/update: `sources/Woow_HA_App_Store/n8n/` from the verified source `n8n/` directory.

1. Synchronize the source add-on directory without unrelated changes.
2. Re-run YAML assertions and compare source/store directories.
3. Commit and push `WOOWTECH/Woow_HA_App_Store`.

### Task 3: Update and verify the target Home Assistant host

1. Reload the Supervisor Store and confirm version `2.12.3-v1` is offered.
2. Update `1b7b4ce7_woow-n8n` through the Store.
3. Confirm runtime environment contains `N8N_SECURE_COOKIE=false`.
4. Confirm the add-on starts, the editor returns HTTP 200, and logs show version `2.12.3` without startup failure.
5. Reproduce the original browser prerequisite by checking that LAN HTTP is the configured editor URL and secure-cookie enforcement is disabled.
