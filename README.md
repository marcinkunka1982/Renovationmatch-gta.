# RenovationMatch GTA — local working prototype (stage 2)

Requires Python 3.10+; no external packages.

1. Unzip this project and open a terminal inside its folder.
2. Set a strong secret token:
   - macOS/Linux: `export RM_ADMIN_TOKEN='replace-with-a-long-random-secret'`
   - Windows PowerShell: `$env:RM_ADMIN_TOKEN='replace-with-a-long-random-secret'`
3. Start: `python server.py`
4. Visit `http://127.0.0.1:8000/` for homeowner submissions, `/contractors.html` for contractor registration, `/admin.html` for the private admin page.
5. Enter your secret in admin to view leads and contractors and assign each lead once.

Data is saved in `renovationmatch.sqlite3` locally. Do not open HTML by double-clicking the file: the API needs the server.

**Not ready for public launch:** No HTTPS, spam/rate limiting, verification, email delivery, user authentication, payment processing, backups, privacy policy, retention/deletion workflow, consent audit, or production hosting. The admin token is a development-only control. Use fictional test information until those are added. No real payments or notifications occur.

## Stage 3 additions (2026-10-10)
- Added basic in-memory per-IP rate limiting for public submissions, restrictive response headers, blocked downloads of server source and SQLite files, and event audit entries.
- Optional administrator notification via SMTP SSL. Set `RM_SMTP_HOST`, `RM_SMTP_PORT`, `RM_SMTP_USER`, `RM_SMTP_PASSWORD`, `RM_SMTP_FROM`, and `RM_NOTIFY_EMAIL` in your server environment. Email notifications include IDs only, not homeowner details. Notifications are best effort, not guaranteed.
- Added `/privacy.html` as a **draft placeholder**, not a final legal policy.
- `.env.example` is a reference only: the standard-library server does not automatically load `.env` files.

**Still NOT ready for public use:** Must deploy behind HTTPS and managed reverse proxy, use proper user authentication instead of a shared admin token, CSRF protection if switching to cookie sessions, durable rate limiting and spam protection, backups and restore testing, a documented privacy/retention/deletion process, verified consent, monitoring, transactional email delivery and privacy/legal review. No domain or hosting has been connected. Do not collect real customer information yet.
