# Maui County Library Workspace — Master Prototype

Final public-prototype release for a shared Maui County library staff workspace spanning eight branch workspaces.

## Master Prototype features
- One countywide Staff Hub and eight branch workspaces
- Consistent Management, Operations, Services, and Communications hierarchy
- Gemini-powered Atlas with page context, conversation history, navigation actions, search handoff, feedback/Edit Mode/My Workspace actions, and presentation-safe boundaries
- Search 2.0 with branch filtering, typed results, keyboard `/` shortcut, and Atlas fallback
- My Workspace with browser-local favorites and recently viewed locations
- Staff Board 2.0 with categories, branch filtering, reactions, and browser-local demo posts
- Browser-local Edit Mode with add/remove/reset workflows
- Activity Center filters and prototype update feed
- First-visit guided onboarding tour
- Installable PWA manifest, service worker, caching, online/offline feedback, and offline screen
- Custom 404 and 500 experiences
- Responsive/mobile layout, keyboard focus treatment, skip link, reduced-motion support, accessible labels, and improved drawer behavior
- Custom Lokelani-inspired eight-branch workspace emblem and resilient branch-image fallbacks
- Existing anonymous/named feedback endpoint preserved
- Lahaina Sketchfab and Hana Meshy model support

## Intentional boundaries
The Master Prototype does **not** implement production authentication, permanent production storage, real HSPLS internal content, organizational user accounts, or live Microsoft/SharePoint/OneDrive integrations. Those are adoption-phase items requiring organizational approval, governance, and security decisions.

Browser-local features (favorites, recent history, Staff Board demo content, Edit Mode demo content, local usage counters) remain on the current device. Feedback continues to use the existing prototype SQLite endpoint and should not be treated as durable production storage on an ephemeral host.

## Missing branch photo assets
The GitHub ZIP used for this Master build did not include `static/assets/branches/*` or `static/assets/logos/*`, although V9 referenced them. The Master UI is resilient: missing exterior images fall back to designed branch-cover treatments instead of broken image icons.

If you have the original branch exterior images, restore them under:

`static/assets/branches/`

using these filenames:
- `hana.png`
- `kahului.jpg`
- `kihei.jpg`
- `lahaina.jpg`
- `lanai.jpg`
- `makawao.jpg`
- `molokai.jpg`
- `wailuku.jpg`

The Master templates will automatically use them when present.

## Local run
```bash
py -m pip install -r requirements.txt
py app.py
```
Open `http://127.0.0.1:5000`.

Atlas requires the `GEMINI_API_KEY` environment variable. Do not commit API keys or secrets to GitHub.

## Existing Render deployment
Keep the existing Render Web Service connected to the same GitHub repository. Updating that repository triggers a redeploy while preserving the existing Render service URL.

Recommended sequence:
1. Run and inspect the Master build locally.
2. Confirm Atlas works with your local/environment key configuration.
3. Push the Master files to the existing GitHub repository.
4. Let the existing Render service redeploy.
5. Smoke-test `/`, a branch page, a section page, Atlas, search, feedback, and the PWA manifest.

## Adoption-phase roadmap
Only after formal adoption: organizational authentication/SSO, durable managed database/storage, role-based authorization, approved document/content ingestion, Microsoft integration, production logging/backups/retention, and security/governance review.
