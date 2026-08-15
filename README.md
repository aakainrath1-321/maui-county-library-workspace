# Maui County Library Workspace Prototype v2.1

Presentation-safe Flask prototype for an interactive Maui County staff workspace.

## Included
- Countywide Staff Hub and eight branch workspaces
- Original Google Sites structure repeated across every branch
- Branch logos and exterior photos
- Lahaina Sketchfab model and Hana Meshy model integration/fallback
- Atlas embedded workspace intelligence and navigation assistant
- Universal workspace search
- Prototype Edit Mode with browser-local demo changes
- Staff Board with browser-local demo posts
- Named or anonymous feedback saved to SQLite
- Authentication/role-based-access concept page
- Lokelani-inspired favicon
- Responsive design and Render configuration

## Safety model
No real internal HSPLS operational content is included. Public Edit Mode does not modify the shared application; demo edits and Staff Board posts remain in the current browser. Feedback is the only server-side submission in this prototype.

Atlas is intentionally presentation-safe and structure-aware. It can navigate the prototype and initiate UI actions without sending data to an external AI service. A future approved version can connect Atlas to an approved LLM and internal knowledge layer.

## Run locally
`py -m pip install -r requirements.txt`

`py app.py`

Open `http://127.0.0.1:5000`.

## Deployment
The repository includes `render.yaml` and Gunicorn for Render deployment. Keep credentials and real internal content out of the public repository/deployment.

## 3D models
Lahaina uses the Sketchfab UID supplied for the project and is correctly labeled as Lahaina Public Library. Hana uses the supplied Meshy shared model URL; because third-party pages can restrict iframe embedding, an Open Model fallback is included. For the most reliable Hana embed later, export the model as GLB and host it with a web 3D viewer.


## v2.1 fixes

- Fixed branch and section page template errors caused by a Jinja dictionary-method naming collision.
- Upgraded Atlas responses with contextual branch awareness, more natural navigation, hierarchy guidance, capability explanations, and better intent handling.


## Atlas Gemini Upgrade

Atlas is now Gemini-powered and conversational. See `ATLAS_SETUP.md`.


## V5 changes

- Atlas now retries transient Gemini 503/429 errors automatically.
- Atlas falls back from `gemini-3.6-flash` to `gemini-3.5-flash-lite` when needed.
- User-facing Atlas errors are now friendly instead of exposing raw API exceptions.
- The visual theme now changes the actual selectors used by the app: warm white, muted ocean teal, soft sage, restrained Lokelani rose, thinner borders, gentler shadows, and reduced visual noise.
