# Woow_ha_n8n — WoowTech n8n Home Assistant Add-on Repository

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWOOWTECH%2FWoow_ha_n8n)

Home Assistant add-on repository for [n8n](https://n8n.io) workflow automation
(HTTP/LAN variant — use a Cloudflare Tunnel for HTTPS).

n8n 工作流程自動化平台的 Home Assistant add-on 倉庫
(HTTP 區網版本,對外請以 Cloudflare Tunnel 建立 HTTPS)。

## Add-ons in this repository | 本倉庫的 add-on

| Add-on | Description |
|---|---|
| [Woow n8n](n8n/) | n8n workflow automation + bundled Redis (amd64/aarch64) |

## Installation | 安裝

1. Click the badge above (or **Settings → Add-ons → Add-on Store → ⋮ →
   Repositories**) and add:
   `https://github.com/WOOWTECH/Woow_ha_n8n`
2. Find **Woow n8n** in the store and click **INSTALL**.
3. Details, options and troubleshooting: [n8n/README.md](n8n/README.md)

> **Migrated from `Woow_n8n_docker_compose_all` (branch `ha`)** — if you added
> the old repository URL, remove it and add this one to keep receiving updates.
> 若你先前加入的是舊倉庫網址,請移除並改加本倉庫,才能繼續收到更新。

## Other deployment platforms | 其他部署平台

- Docker/Podman Compose → [Woow_podman_n8n](https://github.com/WOOWTECH/Woow_podman_n8n)
- K3s/Kubernetes Helm chart → [Woow_k3s_n8n](https://github.com/WOOWTECH/Woow_k3s_n8n)
