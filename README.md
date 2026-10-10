# Infinity Stream TV

A responsive entertainment website built with HTML, CSS, vanilla JavaScript and a Python Flask backend. The supplied Infinity Stream TV logo and landing-page reference guide the visual identity. Content, prices, billing options, enquiry copy and the WhatsApp contact are editable in `data/site.json`.

## Run locally on Windows

Python 3.10 or newer is required. This project was tested with Python 3.14.3.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe app.py
```

Open **http://localhost:5000**. Local `.env` configuration is optional. When no local `SECRET_KEY` is supplied, the app generates a persistent development key in the ignored `instance/` directory. Debug mode is disabled.

On macOS/Linux, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.

## Pages and editable content

Public routes are `/`, `/pricing`, `/channels`, `/devices`, `/reseller`, `/faq`, `/contact`, `/privacy`, `/terms`, and `/refund-policy`. The devices page includes the setup overview. Each page has its own title, description and canonical URL; `/sitemap.xml` and `/robots.txt` use `SITE_URL`.

Edit `data/site.json` to update plan names, features and the `monthly`, `quarterly`, and `yearly` options. Each billing period has its own `price`, `currency` and display `label`. A `null` price displays an enquiry prompt. Confirmed prices should be numeric values. Restart Flask and rebuild any static export after changing content.

The initial configuration deliberately leaves prices and trial duration unset. The copy asks visitors to confirm current content, compatibility, connection limits, trial availability, payment options and subscription terms with the business. No customer testimonials, content counts, uptime promises or invented prices are included. Business-specific terms, operator identity and policies should be completed with confirmed information before public launch.

The primary sales contact is **+880 1874 608217**, configured as digits-only `8801874608217`. Every plan CTA creates a WhatsApp message naming that plan and the selected billing period. Opening WhatsApp prepares a message for the visitor to review and send; it does not send anything automatically.

## Enquiry behavior

On Flask, the contact and reseller forms submit to `POST /enquiry`. Required fields are `name`, `country`, `contact_method` (`whatsapp` or `email`), `contact`, and `message`. Optional `plan` defaults to `general`; `source_page` chooses the contact or reseller page for feedback. `csrf_token` is required and `website` is an empty honeypot field.

The server validates and escapes form content, checks a session-bound CSRF token, rejects honeypot entries, and limits submissions to five attempts per client over ten minutes by default. The limiter uses a shared SQLite table, stores an HMAC of the client IP, and does not trust forwarded headers unless explicitly configured.

Valid enquiries are stored in `instance/enquiries.sqlite3` with name, country, preferred contact method, contact details, message, selected plan, source page, timestamp and status. A regular browser form then redirects to the configured WhatsApp contact with a prepared message. Requests with `Accept: application/json` receive `{ok, saved, whatsapp_url, message}` on success or `{ok, saved, errors}` on failure. Saving an enquiry does not contact the business by itself; the customer sends the prepared WhatsApp message. There is no public admin panel or automated email service.

The database is private operational data: keep it outside static hosting and restrict access. The maintenance command below removes enquiries older than 90 days and expired rate-limit records. Schedule it if that retention period matches your confirmed privacy policy, and handle requested deletions through private operational tooling.

```powershell
.\.venv\Scripts\python.exe -m flask --app app prune-enquiries
```

## Static preview or hosting

The same templates can be exported for a host that serves static files:

```powershell
.\.venv\Scripts\python.exe build_static.py --site-url https://your-domain.example
.\.venv\Scripts\python.exe -m http.server 8000 --directory dist
```

Open **http://localhost:8000**. An optional `--output` argument selects another export directory. The export includes all pages, public images, CSS, JavaScript, `404.html`, sitemap, robots and a `_headers` file for compatible hosts. Original source artwork and provenance notes stay in the source project. The full landing-page reference is exported only while the CSS or templates still reference it. Set the real public origin when publishing so canonical URLs and the sitemap are correct. Configure equivalent response headers if the host does not support `_headers`.

**Static hosting does not run Python or store enquiries.** Static forms validate in the browser and prepare a WhatsApp message for the visitor to send. Static pages do not include live CSRF tokens or create Flask session cookies. Deploy the Flask application separately if server-side enquiry storage is required. Upload only `dist/` to static hosting; do not upload `.env`, `.venv`, `instance/`, or source files containing operational configuration.

## Production Flask configuration

Set these values through the deployment environment or a private `.env` file:

```dotenv
APP_ENV=production
SITE_URL=https://your-domain.example
# Fill this with the generated secret before starting the application.
SECRET_KEY=
DATABASE_PATH=/private/persistent/path/enquiries.sqlite3
TRUSTED_HOSTS=your-domain.example,www.your-domain.example
TRUST_PROXY_COUNT=1
```

Generate a strong secret with `python -c "import secrets; print(secrets.token_hex(32))"`. `TRUST_PROXY_COUNT` must match the number of trusted reverse proxies, and the application port must not be reachable by untrusted clients when proxy headers are enabled. Leave it at `0` when there is no trusted reverse proxy. Choose a persistent private database location, arrange backups and schedule enquiry retention.

Use Waitress behind an HTTPS reverse proxy; the Flask development server is for local work:

```powershell
.\.venv\Scripts\waitress-serve.exe --host=127.0.0.1 --port=8080 app:app
```

Production startup rejects a missing/short secret or a non-HTTPS canonical origin. The application disables debug mode, restricts trusted hosts, redirects HTTP to HTTPS, sets Secure/HttpOnly/SameSite session cookies, and supplies security headers including a content security policy. Configure HTTPS termination and trusted forwarding at the reverse proxy. SQLite suits this initial small single-host service; review the database and shared rate-limit architecture before deploying across multiple hosts.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Tests cover public pages and metadata, enquiry validation, CSRF, spam controls, rate-limit expiry, safe WhatsApp destinations, HTML escaping, production configuration, sitemap, and static export. Responsive layout, keyboard controls, image loading and WhatsApp flows are also verified in a browser during development.

Pinned dependency versions were checked against [PyPI](https://pypi.org/) and installed together. Production serving and security choices follow the official [Flask Waitress guide](https://flask.palletsprojects.com/en/stable/deploying/waitress/) and [Flask security documentation](https://flask.palletsprojects.com/en/stable/web-security/). Recheck dependencies and rerun validation before a later deployment or update.
