# Cloudflare Full-UI Design

## Goal

Expose the complete Woow n8n user interface, REST API, webhooks, and editor WebSocket over one Cloudflare Tunnel hostname while retaining the add-on's existing LAN HTTP entry point.

Production hostname: `https://woowtech-n8n.woowtech.io`.

## Architecture

```text
Browser / webhook caller
  -> Cloudflare edge (HTTPS + WebSocket)
  -> existing remotely-managed `woowtech` Tunnel
  -> http://homeassistant:5678
  -> Woow n8n add-on (plain HTTP origin)
```

TLS terminates at Cloudflare. n8n continues to listen on HTTP port 5678 inside Home Assistant. The public hostname is forwarded intact and cloudflared supplies forwarded headers. n8n is configured with its public editor and webhook URLs plus the trusted proxy-hop count, so generated links, OAuth redirects, webhooks, cookies, and the `/rest/push` WebSocket use the public HTTPS origin.

The add-on remains reusable: no WoowTech hostname is hard-coded in defaults. New first-class optional settings expose the n8n reverse-proxy controls in the Home Assistant configuration UI. Legacy `WEBHOOK_URL` and newer `N8N_WEBHOOK_URL` are mirrored at boot so the current bundled n8n and a future n8n upgrade both receive the correct public webhook URL.

## Cloudflare changes

Reuse the existing healthy, remotely managed `woowtech` Tunnel. Insert this rule immediately before the terminal `http_status:404` rule:

```json
{"hostname":"woowtech-n8n.woowtech.io","service":"http://homeassistant:5678","originRequest":{}}
```

Create a proxied CNAME `woowtech-n8n.woowtech.io` pointing to the tunnel UUID under `cfargotunnel.com`. No Cloudflare Access policy is added because the same origin must accept unauthenticated production webhooks. n8n's own authentication protects the editor.

## Runtime configuration

```yaml
N8N_HOST: woowtech-n8n.woowtech.io
N8N_EDITOR_BASE_URL: https://woowtech-n8n.woowtech.io
N8N_WEBHOOK_URL: https://woowtech-n8n.woowtech.io
WEBHOOK_URL: https://woowtech-n8n.woowtech.io
N8N_PROXY_HOPS: 1
N8N_SECURE_COOKIE: true
```

`N8N_PROTOCOL` remains `http` because the origin listener is not changed to TLS.

## Safety and rollback

Before updating the add-on, create a Home Assistant backup. Rollback consists of restoring the prior add-on version/options, removing the DNS CNAME, and removing the tunnel ingress rule. Tunnel configuration updates preserve every existing ingress rule and only insert the n8n hostname before the catch-all.

## Verification

- Parse and validate YAML.
- Shell syntax and focused boot-variable tests.
- Build/start through Home Assistant Supervisor.
- Verify public HTTPS root and health endpoint.
- Verify forwarded URL generation, login cookie security, webhook URL, REST API, and `/rest/push` WebSocket transport.
- Confirm existing `woowtech-ha.woowtech.io` remains healthy after the shared tunnel update.
