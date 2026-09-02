# n8n Ingress Preload De-duplication Design

## Problem and confirmed cause

The Home Assistant App panel, its iframe, and the iframe viewport are already full-height after loading add-on 2.12.13. Across eight viewports from 360×800 to 1920×1080, all three outer layers exactly matched the viewport. Only n8n's `#n8n-app` remained at 489.67px.

n8n 2.12.3 applies two same-specificity CSS-module classes to `#n8n-app`: BaseLayout supplies `height: 100%`; App supplies `height: 100vh`. Direct access loads BaseLayout CSS before the main index CSS, so `100vh` wins. Under HA Ingress, the Vite preload helper searches for root-relative links such as `/assets/BaseLayout-CVWlZK-m.css`, while nginx has already rewritten the initial DOM links to `/api/hassio_ingress/<session>/assets/...`. The helper fails to recognize existing links and appends BaseLayout CSS again after the index stylesheet. The later duplicate `height:100%` wins, but Vue's mount parent has auto height, so the app collapses to its 489.67px natural content height.

Causal browser evidence: disabling only the second BaseLayout stylesheet changes desktop height 489.67→900px and mobile height 489.67→844px; re-enabling it restores 489.67px. Direct n8n has one BaseLayout stylesheet and fills the viewport.

## Chosen architecture

Patch the pinned n8n 2.12.3 preload URL builder only in the ingress nginx response. Rewrite its exact minified root builder from:

```js
hee=function(e){return`/`+e}
```

to:

```js
hee=function(e){return(window.BASE_PATH||`/`)+e}
```

The existing ingress adapter already rewrites `window.BASE_PATH` to the validated Supervisor prefix with a trailing slash. Preload dependencies therefore enter the helper in the same URL namespace as the initial HTML links. Its native duplicate query now succeeds, so it does not append duplicate modulepreload or stylesheet links. Assets that are genuinely new still receive a valid prefixed URL.

The rewrite lives only in nginx port 5690. Direct n8n port 5678 and the Cloudflare hostname never pass through it and remain unchanged. Because the add-on is pinned to n8n 2.12.3, an exact version-specific rewrite is preferable to global DOM monkeypatching. Before exercising the exact helper fixture, the behavioral regression gates it against every supported upstream pin: Dockerfile `BUILD_FROM`, the Dockerfile runner stage, both `build.yaml` architectures, and `addon_info.yaml` `current_version` must all independently identify n8n 2.12.3. Any pin bump therefore fails with an explicit seam-review message instead of silently validating the old fixture against a new release.

## Removal of the previous workaround

Release 2.12.13's `ingress-frame-height.js` is removed together with its nginx location and injection. It repaired an outer layer that live measurement proved was not the failure. On narrow Home Assistant layouts it also overrides HA's `.header + iframe` height calculation, potentially extending the iframe 40px beyond the visible panel. The new fix restores native HA iframe sizing and addresses the actual duplicate-cascade cause.

## Validation and safety

A retained Playwright regression will first enforce the 2.12.3 pin gate, then exercise a real temporary nginx process plus a Supervisor-prefix proxy. The backend fixture uses the pinned n8n helper signature and the same CSS cascade: one BaseLayout stylesheet before an index stylesheet. Before the fix, the helper appends BaseLayout again and collapses the app. After the rewrite, exactly one stylesheet remains and the app equals the viewport. The test also loads the direct backend to prove unchanged root-path behavior.

Deployment validation covers eight desktop/tablet/mobile viewports through the real Cloudflare HA URL after authenticating to HA. Required invariants are: `ha-panel-app` host equals the outer viewport, the iframe follows native HA desktop/mobile header sizing, the child viewport equals the iframe content height, n8n app equals the child viewport, one BaseLayout stylesheet, no duplicate stylesheets, no failed assets, WebSocket 101, and direct Cloudflare n8n unchanged. A partial add-on backup is created before update. Rollback restores 2.12.13; no n8n database migration occurs because n8n and runners stay at 2.12.3.
