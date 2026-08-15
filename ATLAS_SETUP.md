# Atlas Gemini Setup

Atlas now uses Gemini for real multi-turn conversation inside the workspace.

## Windows local setup

Open Command Prompt in this project folder.

Set the Gemini key for that Command Prompt session:

    set GEMINI_API_KEY=YOUR_KEY_HERE

Optional:

    set GEMINI_MODEL=gemini-2.5-flash

Install/update dependencies:

    py -m pip install -r requirements.txt

Run:

    py app.py

Open:

    http://127.0.0.1:5000

## Check Atlas

Configuration health:

    http://127.0.0.1:5000/api/atlas/health

Live Gemini check:

    http://127.0.0.1:5000/api/atlas/health?live=1

## Render later

Create a secret environment variable named GEMINI_API_KEY in Render.
Never place the real key in app.py, JavaScript, GitHub, or a public file.

## What Atlas can now do

- hold a normal conversation
- remember recent turns during the browser session
- understand the Maui County prototype hierarchy
- understand which branch/section is currently open
- recommend and trigger safe navigation
- open the feedback panel
- enable prototype Edit Mode
- brainstorm, explain, and help organize ideas

Atlas still has no access to private HSPLS systems or real internal content.


## Resilience settings

Default primary model:

    gemini-3.6-flash

Default fallback:

    gemini-3.5-flash-lite

Optional overrides:

    set GEMINI_MODEL=gemini-3.6-flash
    set GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
    set ATLAS_RETRY_ATTEMPTS=2
