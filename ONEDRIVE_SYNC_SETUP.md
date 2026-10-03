# Wailuku OneDrive sync update

This update adds read-only syncing of the Wailuku master folder. It is disabled by default. Uploading this code alone keeps the current workspace working as before.

## What it does

The source owner connects their own HSPLS OneDrive once. The server checks the master folder about every five minutes while it is running. New files and folders appear; deleted items disappear; renamed and moved items get current names and OneDrive links. New top-level folders become Wailuku workspace areas. Search and Atlas navigation use the current resource list. Empty subfolders remain omitted from resource cards; empty top-level folders can still have an area.

The app never writes to or deletes from OneDrive. It reads only the master folder hierarchy, skips shortcuts outside it, and retrieves Microsoft thumbnails on demand. The Microsoft Files.Read permission itself covers the connected user's files more broadly than this folder: this limitation is enforced by the app, not a folder-specific Microsoft permission. Workspace resource metadata and thumbnails are visible to authenticated workspace staff. Original files still use OneDrive's own access controls.

## Before enabling

1. Keep your deployed workspace backup.
2. Ensure your repository is private if it contains internal staff resources or thumbnails. Website login does not protect files published in a public GitHub repository. This update does not change repository visibility.
3. Arrange persistent private storage. The supplied implementation uses a persistent disk on the same Render web service. Render persistent disks require a paid service. Do not change plans or buy a disk unless you want that cost. A free service's temporary filesystem cannot reliably retain the connection across redeploys and restarts. An external durable database is a possible alternative, but is not part of this disk-based implementation.

## Upload the code

Unzip Wailuku_OneDrive_Sync_Update.zip. Open the resulting folder. From your repository's MAIN page, choose Add file > Upload files and drag its contents into the upload box. Keep templates, static, and tests as folders. Commit changes and deploy the latest commit in Render. Leave ONEDRIVE_SYNC_ENABLED unset until storage and configuration are ready. This package contains fewer than 100 files.

Files changed: app.py, workspace_auth.py, requirements.txt, onedrive_sync.py, templates/branch.html, templates/section.html, templates/onedrive-sync.html, static/js/wailuku-previews.js. Tests and this guide are also included. Existing CSS and saved previews stay in place. No homepage or other branch layout changes.

## Configure Render

After choosing a paid instance and attaching a persistent disk at `/var/data`, set these environment variables. Creating the directory alone is not enough; the disk must actually be attached.

| Variable | Value |
| --- | --- |
| ONEDRIVE_SYNC_ENABLED | 1 |
| ONEDRIVE_SYNC_DATA_DIR | /var/data/wailuku-onedrive |
| ONEDRIVE_SYNC_OWNER_OID | Your Microsoft account object ID |
| ONEDRIVE_SYNC_KEY | A new Fernet encryption key |
| ONEDRIVE_SYNC_INTERVAL_SECONDS | 300 (optional) |

Keep all existing Microsoft sign-in, SECRET_KEY and Gemini settings. This update reuses the existing `/auth/callback` redirect URI. Do not post secrets in chat, commit them, or put them in the backup ZIP.

To find your own object ID after deploying the code, sign in and open:
`https://maui-county-library-workspace.onrender.com/branch/wailuku/onedrive/account`
This displays only the signed-in account's ID. It is an identifier, not a password.

Generate the encryption key in your Mac Terminal (after installing cryptography if needed):
```
python3 -m pip install cryptography
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' | pbcopy
```
Paste the clipboard into ONEDRIVE_SYNC_KEY in Render. Keep this key stable across redeploys; changing it makes existing encrypted state unreadable. Store a secure recovery copy separately from project files.

## Request read access and connect

In Microsoft Entra, open Wailuku Staff Workspace > API permissions > Add a permission > Microsoft Graph > Delegated permissions. Select ONLY Files.Read and add it to the app's configured permissions. This configures the request; it does not by itself grant OneDrive access or enable sync. Do not select Files.Read.All, write permissions, or tenant-wide admin consent.

Deploy with the configured environment and attached disk. Sign in as the source owner and open the Wailuku homepage. Only that owner sees OneDrive connection. Open it and read the permission explanation, then choose Connect OneDrive. Microsoft presents its consent screen. Approve only if you intend to let this workspace app read your files. If Microsoft says administrator approval is required, stop and ask HSPLS IT; do not work around organization policy.

Ordinary staff login still requests only sign-in scopes. Staff do not connect their own drives. Refresh credentials are encrypted on the server and never stored in browser cookies, static files, logs, or this package. Signing out of the workspace does not disconnect the shared background source connection.

## Test before relying on it

Wait for the connection page to report successful syncing. Create a small test folder under an existing Wailuku area with a harmless sample document. Wait for the next check, reload that area, and check the filename, OneDrive original link, and enlarged preview. Rename it, move it between areas, and delete the test item; verify each change after the next check. Also test a new top-level folder and verify it appears on the Wailuku homepage, in search, and as a valid Atlas destination.

Microsoft may not generate a thumbnail for every file type. The app shows a placeholder when a thumbnail is unavailable; the original remains accessible. Thumbnails are cached per item version and replaced after a successful scan notices the edit.

Test a Render restart and confirm the connection survives. Live Microsoft consent, the mounted disk, real thumbnails, and permissions must be checked on the deployment; local automated tests use mocked Microsoft responses.

## Problems and rollback

Failed scans keep the last complete successful list; partial scans never replace it. Changes during a folder scan may settle on the next check. This is periodic eventual updating, not instant synchronization. If a root folder is renamed or moved within the same drive, the saved item ID preserves the connection. Deleting or moving it to another drive requires restoring it or reconnecting; an inaccessible source retains the last successful list and reports an error to the owner.

If Microsoft revokes access, policies change, or a fresh login is required, reconnect from the owner connection page. The configured source starts at the owner's OneDrive root path `Wailuku Public Library Branch Master Folder`. A shared shortcut in another staff member's drive is not the supported source.

Disconnect and use saved resources removes the server's stored connection and synced thumbnails and returns to the packaged catalog. Microsoft consent itself can remain until revoked separately. Setting ONEDRIVE_SYNC_ENABLED=0 and redeploying also returns to the packaged catalog without deleting OneDrive data. Keep the original deployed backup for a full rollback.

The supplied implementation supports a single Render service instance, with a file lock coordinating multiple gunicorn workers. Do not horizontally scale this SQLite/disk setup or use gunicorn preload. A stopped or sleeping service does not poll.

## Validation

Run `python3 -m unittest discover -s tests -v` after installing requirements. Coverage includes paging, additions/renames/removals, encrypted restart-safe state, atomic failure handling, owner-only management, OAuth owner checks with a signed test ID token, CSRF, dynamic search/Atlas routes, and token-free cookies. Homepage and seven other branch pages were compared to the deployed backup and render identically with sync disabled.
