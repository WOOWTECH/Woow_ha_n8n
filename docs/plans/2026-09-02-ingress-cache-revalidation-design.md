# Ingress Transform Cache Coherence Design

## Confirmed deployment gap

Add-on 2.12.14 correctly rewrites the n8n 2.12.3 preload helper at the origin. Supervisor-network reads contain the prefix-aware builder, but public authenticated browsers can still receive the pre-2.12.14 helper from Cloudflare. The observed response was `CF-Cache-Status: HIT`, `Age: 5289`, and `Cache-Control: public, max-age=86400`. The browser-executed body retained the root builder, while an explicit cache reload fetched the corrected body.

The n8n asset filename did not change because the wrapped n8n version remains 2.12.3. However, ingress nginx changes the asset body after that hash was generated. Reusing upstream long-lived cache headers for transformed bytes makes the URL an invalid immutable cache key: an add-on-only transform release can change content without changing the URL.

## Chosen behavior

Transformed response types must not be stored by browsers or Cloudflare. Add an nginx `map` based on upstream content type:

- HTML: `Cache-Control: no-store`
- JavaScript: `Cache-Control: no-store`
- CSS: `Cache-Control: no-store`
- all other types: preserve the upstream Cache-Control value

Inside ingress port 5690, hide the upstream Cache-Control header and emit the mapped value. Direct port 5678 is not served by this nginx and remains untouched. Images/fonts/icons that are not body-rewritten retain normal cacheability, avoiding a blanket performance penalty.

`no-store` is selected instead of `no-cache`: revalidation against an unchanged upstream ETag could return 304 even though the nginx transform changed, retaining stale transformed bytes. `no-store` removes that validator ambiguity for responses whose bodies nginx may alter.

## One-time operational purge

The new response headers cannot retroactively remove objects already cached with `max-age=86400`. After deploying 2.12.15, perform one Cloudflare prefix purge for `woowtech-ha.woowtech.io/api/hassio_ingress`. This clears only HA ingress paths, not ordinary HA frontend assets or the direct n8n hostname. Users with an already-populated browser cache still need one hard refresh because edge purge cannot delete local browser storage.

The purge is a Cloudflare mutation and requires explicit user approval immediately before execution.

## Validation

Real-nginx tests make the backend return public max-age for HTML, JS, CSS, and an unchanged binary resource. Ingress must return no-store for the transformed types while preserving the binary resource's upstream cache policy. Direct backend responses must remain public max-age. Existing preload-dedup Playwright regression remains green.

After deployment and approved purge, Cloudflare Browser Rendering plus authenticated local Playwright cover eight viewport sizes. Every run requires one BaseLayout stylesheet, zero duplicate CSS hrefs, full n8n app height, native HA mobile header sizing, no old height script, and no failed CSS/JS requests. Response evidence must show the prefix-aware helper and no-store, without a stale Cloudflare HIT.
