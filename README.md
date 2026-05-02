# Reap Holding Online Meet - V4.5 Contacts + WhatsApp Invites

This package includes the requested changes:

- All logged-in users can see the Company Contacts Directory.
- Contacts are loaded from registered users in the shared SQLite database.
- Passwords are never returned in the contacts API.
- Registration now includes WhatsApp number.
- Admin Create User now includes WhatsApp number.
- Live Meeting Room includes WhatsApp invite buttons for every registered user.
- WhatsApp invite sends the full meeting link, not only Meeting ID.
- Existing databases are migrated automatically by adding a phone column if missing.
- Jitsi toolbar includes Screen Share button.
- Service worker cache name updated to avoid old cached app.js/style.css.

## Upload steps

Replace your project files with this package structure:

- server.py
- meetings.db
- static/index.html
- static/app.js
- static/style.css
- static/manifest.json
- static/service-worker.js

Then run:

```bash
git add .
git commit -m "Add contacts directory and WhatsApp invites"
git push
```

Wait for Railway Deployments to show Success.

## Important

If an old browser still shows the old version, open the app in Incognito or clear site data once because the app uses a service worker cache.
