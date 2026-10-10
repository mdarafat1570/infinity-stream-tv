"""Infinity Stream TV public pages and a protected, minimal enquiry service."""

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlsplit
from xml.sax.saxutils import escape

from flask import Flask, Response, current_app, g, has_request_context, jsonify, redirect, render_template, request
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import i18n
from config import PROJECT_ROOT, environment_config, site_origin

PAGES = {
    "home": ("/", "Infinity Stream TV | Live TV, Movies & Series", "Explore Infinity Stream TV plans, entertainment categories, device setup guidance and subscription enquiries."),
    "pricing": ("/pricing", "Subscription Plans | Infinity Stream TV", "Explore Basic, Standard, Premium and Reseller plans. Ask for current pricing, billing options and confirmed package details."),
    "channels": ("/channels", "Entertainment Categories | Infinity Stream TV", "Explore live TV, movies, series, sports and international entertainment categories. Confirm the latest availability before subscribing."),
    "devices": ("/devices", "Devices & Setup | Infinity Stream TV", "Check your device compatibility and get personal setup guidance for televisions, phones, tablets and computers."),
    "reseller": ("/reseller", "Reseller Enquiries | Infinity Stream TV", "Discuss partnership eligibility, packages, onboarding and commercial terms with the Infinity Stream TV team."),
    "faq": ("/faq", "Frequently Asked Questions | Infinity Stream TV", "Find answers about subscription enquiries, trials, devices, connection limits, payment options and support."),
    "contact": ("/contact", "Contact & Support | Infinity Stream TV", "Contact Infinity Stream TV on WhatsApp or send a subscription, device setup or support enquiry."),
    "privacy": ("/privacy", "Privacy Information | Infinity Stream TV", "Learn how this website handles enquiry information, essential cookies and WhatsApp links."),
    "terms": ("/terms", "Website Terms | Infinity Stream TV", "Read the website enquiry terms and learn which subscription details to confirm before purchasing."),
    "refund-policy": ("/refund-policy", "Cancellation & Refund Information | Infinity Stream TV", "Find out how to confirm cancellation and refund terms before agreeing to an Infinity Stream TV subscription."),
}

csrf = CSRFProtect()


def load_site(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as source:
        site = json.load(source)
    phone = site.get("settings", {}).get("whatsapp_phone", "")
    if not re.fullmatch(r"[1-9][0-9]{6,14}", phone):
        raise ValueError("site.settings.whatsapp_phone must be an international number containing digits only.")
    return site


def _development_secret(instance_path: Path) -> str:
    """Persist one local secret across reloads without checking it into source."""
    instance_path.mkdir(parents=True, exist_ok=True)
    secret_path = instance_path / ".development-secret"
    try:
        with secret_path.open("x", encoding="ascii") as output:
            secret_path.chmod(0o600)
            output.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    return secret_path.read_text(encoding="ascii").strip()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        g.db = db
    return g.db


def initialize_database(app: Flask) -> None:
    database = Path(app.config["DATABASE"])
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=10)) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS enquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                country TEXT NOT NULL,
                contact_method TEXT NOT NULL CHECK(contact_method IN ('whatsapp', 'email')),
                contact TEXT NOT NULL,
                message TEXT NOT NULL,
                plan TEXT NOT NULL,
                source_page TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new'
            );
            CREATE TABLE IF NOT EXISTS enquiry_limits (
                client_hash TEXT NOT NULL,
                attempted_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS enquiry_limits_client_time
                ON enquiry_limits(client_hash, attempted_at);
            """
        )
        db.commit()


def whatsapp_url(plan_name: str | None = None, message: str | None = None, period: str | None = None) -> str:
    """Always build the destination from the validated configured phone number."""
    site = current_app.extensions["site"]
    if message is None:
        if plan_name and str(plan_name).lower() == "trial":
            message = "Hello Infinity Stream TV, is a free trial currently available? Please confirm eligibility, duration, available content and device setup."
        elif plan_name:
            term = f" ({period} billing)" if period else ""
            message = f"Hello Infinity Stream TV, I would like to know more about the {plan_name}{term}. Please share the current price, available content, supported devices and activation details."
        else:
            message = "Hello Infinity Stream TV, I would like to ask about your available plans, device compatibility and setup."
    return f"https://wa.me/{site['settings']['whatsapp_phone']}?{urlencode({'text': message})}"


def resolve_request_locale() -> str:
    """Resolve the active locale from the current request, defaulting to English outside one."""
    if not has_request_context():
        return i18n.DEFAULT_LOCALE
    return i18n.resolve_locale(query_lang=request.args.get("lang"), cookie_lang=request.cookies.get("lang"))


def current_translator():
    """A `t(key, **kwargs)` bound to the active request's locale, for use outside page_context()."""
    return i18n.make_translator(resolve_request_locale())


def alternate_url(path: str, locale: str) -> str | None:
    """The equivalent URL for `path` in `locale`, for hreflang alternate links."""
    origin = current_app.config.get("SITE_URL")
    if not origin:
        return None
    suffix = path.strip("/")
    if locale == "ar":
        return f"{origin}/ar/{suffix}" if suffix else f"{origin}/ar/"
    return origin + path


def _lang_switch_url(current_path: str, target_locale: str, *, is_static: bool) -> str:
    """The current page's URL with `lang` swapped to `target_locale`, preserving other query params."""
    params = []
    if has_request_context() and not is_static:
        params = [(key, value) for key, value in request.args.items(multi=True) if key != "lang"]
    params.append(("lang", target_locale))
    return f"{current_path}?{urlencode(params)}"


def page_context(slug: str, *, is_static: bool = False, locale: str | None = None, **overrides) -> dict:
    path, title, description = PAGES.get(slug, ("/", "Infinity Stream TV", "Entertainment and subscription enquiries."))
    resolved_locale = locale if locale in i18n.SUPPORTED_LOCALES else resolve_request_locale()
    current_path = request.path if (has_request_context() and not is_static) else path
    context = {
        "site": current_app.extensions["site"],
        "page_slug": slug,
        "page_title": title,
        "page_description": description,
        "canonical_url": current_app.config["SITE_URL"] + path,
        "alternate_en_url": alternate_url(path, "en"),
        "alternate_ar_url": alternate_url(path, "ar"),
        "current_year": datetime.now(timezone.utc).year,
        "csrf_token": "" if is_static else generate_csrf(),
        "is_static": is_static,
        "whatsapp_url": whatsapp_url,
        "form_errors": {},
        "form_data": {},
        "enquiry_saved": False,
        "locale": resolved_locale,
        "text_dir": i18n.text_direction(resolved_locale),
        "t": i18n.make_translator(resolved_locale),
        "loc": i18n.localize,
        "lang_url_en": _lang_switch_url(current_path, "en", is_static=is_static),
        "lang_url_ar": _lang_switch_url(current_path, "ar", is_static=is_static),
    }
    context.update(overrides)
    return context


def render_page(slug: str, *, status: int = 200, **overrides):
    template = "index.html" if slug == "home" else "page.html"
    return render_template(template, **page_context(slug, **overrides)), status


def _form_source() -> str:
    return "reseller" if request.form.get("source_page") == "reseller" else "contact"


def _wants_json() -> bool:
    return request.accept_mimetypes.best == "application/json"


def enquiry_error(errors: dict, status: int = 400, data: dict | None = None):
    if _wants_json():
        response = jsonify(ok=False, saved=False, errors=errors)
        response.status_code = status
        return response
    return render_page(_form_source(), status=status, form_errors=errors, form_data=data or {})


def validate_enquiry(form, t=None) -> tuple[dict, dict]:
    t = t or current_translator()
    fields = ("name", "country", "contact_method", "contact", "message", "plan")
    data = {key: str(form.get(key, "")).strip() for key in fields}
    data["plan"] = data["plan"] or "general"
    errors = {}
    for field, minimum, maximum, label_key in (
        ("name", 2, 80, "forms.labels.name"),
        ("country", 2, 80, "forms.labels.country"),
        ("message", 10, 2000, "forms.labels.message"),
    ):
        if not minimum <= len(data[field]) <= maximum:
            errors[field] = t("forms.errors.name_length", label=t(label_key), minimum=minimum, maximum=maximum)
    for field, value in data.items():
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
            errors[field] = t("forms.errors.control_chars")
    if data["contact_method"] not in {"whatsapp", "email"}:
        errors["contact_method"] = t("forms.errors.contact_method")
    elif data["contact_method"] == "whatsapp":
        number = re.sub(r"[\s().\-]", "", data["contact"])
        if not re.fullmatch(r"\+?[1-9][0-9]{6,14}", number):
            errors["contact"] = t("forms.errors.contact_phone")
        else:
            data["contact"] = number
    elif len(data["contact"]) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", data["contact"]):
        errors["contact"] = t("forms.errors.contact_email")
    allowed_plans = {plan["slug"] for plan in current_app.extensions["site"]["plans"]} | {"general", "trial"}
    if data["plan"] not in allowed_plans:
        errors["plan"] = t("forms.errors.plan")
    return data, errors


def _consume_rate_limit() -> tuple[bool, int]:
    """An atomic shared limiter; never retain the original IP address."""
    now = time.time()
    window = current_app.config["ENQUIRY_RATE_WINDOW"]
    client_hash = hmac.new(
        current_app.secret_key.encode("utf-8"),
        (request.remote_addr or "unknown").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM enquiry_limits WHERE attempted_at <= ?", (now - window,))
        row = db.execute(
            "SELECT COUNT(*) AS total, MIN(attempted_at) AS earliest FROM enquiry_limits WHERE client_hash = ?",
            (client_hash,),
        ).fetchone()
        if row["total"] >= current_app.config["ENQUIRY_RATE_LIMIT"]:
            db.commit()
            return False, max(1, int(row["earliest"] + window - now) + 1)
        db.execute("INSERT INTO enquiry_limits(client_hash, attempted_at) VALUES (?, ?)", (client_hash, now))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True, 0


def sitemap_xml() -> str:
    origin = current_app.config["SITE_URL"]
    urls = "".join(f"<url><loc>{escape(origin + value[0])}</loc></url>" for value in PAGES.values())
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


def robots_text() -> str:
    return f"User-agent: *\nAllow: /\nDisallow: /enquiry\nSitemap: {current_app.config['SITE_URL']}/sitemap.xml\n"


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_path=str(PROJECT_ROOT / "instance"))
    app.config.from_mapping(environment_config())
    if test_config:
        app.config.update(test_config)
    app.config["SITE_URL"] = site_origin(app.config["SITE_URL"])
    if app.config["APP_ENV"] == "production":
        if not app.config["SITE_URL"].startswith("https://"):
            raise ValueError("Production SITE_URL must use HTTPS.")
        if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
            raise ValueError("Production requires a SECRET_KEY of at least 32 characters.")
        app.config.update(DEBUG=False, SESSION_COOKIE_SECURE=True)
    elif not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _development_secret(Path(app.instance_path))
    if app.config["ENQUIRY_RATE_LIMIT"] < 1 or app.config["ENQUIRY_RATE_WINDOW"] < 1:
        raise ValueError("Enquiry rate limits must be positive integers.")
    app.extensions["site"] = load_site(app.config["SITE_DATA_FILE"])
    proxy_count = app.config["TRUST_PROXY_COUNT"]
    if proxy_count < 0:
        raise ValueError("TRUST_PROXY_COUNT must not be negative.")
    if proxy_count:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_count, x_proto=proxy_count, x_host=0, x_port=0, x_prefix=0)
    initialize_database(app)

    @app.teardown_appcontext
    def close_database(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.before_request
    def enforce_transport_and_rate_limit():
        if app.config["APP_ENV"] == "production" and not request.is_secure:
            # Build the origin from configuration, never a user-controlled Host header.
            query = ("?" + request.query_string.decode("ascii", errors="ignore")) if request.query_string else ""
            return redirect(app.config["SITE_URL"] + request.path + query, code=308)
        if request.endpoint == "enquiry" and request.method == "POST":
            allowed, retry_after = _consume_rate_limit()
            if not allowed:
                response = app.make_response(enquiry_error({"_form": current_translator()("forms.errors.rate_limited")}, 429))
                response.headers["Retry-After"] = str(retry_after)
                return response

    csrf.init_app(app)

    for slug, (path, _title, _description) in PAGES.items():
        def view(page_slug=slug):
            return render_page(page_slug)
        app.add_url_rule(path, endpoint=slug.replace("-", "_"), view_func=view)

    @app.get("/enquiry")
    def enquiry_start():
        return redirect("/contact#enquiry", code=302)

    @app.post("/enquiry")
    def enquiry():
        t = current_translator()
        if request.form.get("website", "").strip():
            return enquiry_error({"_form": t("forms.errors.spam")})
        data, errors = validate_enquiry(request.form, t)
        if errors:
            return enquiry_error(errors, data=data)
        db = get_db()
        db.execute(
            "INSERT INTO enquiries(name,country,contact_method,contact,message,plan,source_page,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                data["name"], data["country"], data["contact_method"], data["contact"],
                data["message"], data["plan"], _form_source(), datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        db.commit()
        plan_names = {item["slug"]: item["name"] for item in app.extensions["site"]["plans"]}
        plan = plan_names.get(data["plan"], "a trial enquiry" if data["plan"] == "trial" else "a general enquiry")
        message = (
            f"Hello Infinity Stream TV, I am {data['name']} from {data['country']}.\n"
            f"I would like to ask about {plan}.\n"
            f"Preferred contact: {data['contact_method']} ({data['contact']}).\n\n{data['message']}"
        )
        destination = whatsapp_url(message=message)
        if _wants_json():
            return jsonify(ok=True, saved=True, whatsapp_url=destination, message=t("forms.success_message"))
        return redirect(destination, code=303)

    @app.get("/sitemap.xml")
    def sitemap():
        return Response(sitemap_xml(), mimetype="application/xml")

    @app.get("/robots.txt")
    def robots():
        return Response(robots_text(), mimetype="text/plain")

    @app.errorhandler(CSRFError)
    def csrf_failure(error):
        data = {key: request.form.get(key, "") for key in ("name", "country", "contact_method", "contact", "message", "plan")}
        return enquiry_error({"_form": current_translator()("forms.errors.csrf")}, 400, data)

    @app.errorhandler(HTTPException)
    def public_error(error):
        t = current_translator()
        titles = {404: t("error.titles.404"), 413: t("error.titles.413"), 500: t("error.titles.500")}
        messages = {404: t("error.messages.404"), 413: t("error.messages.413"), 500: t("error.messages.500")}
        title = titles.get(error.code, error.name)
        message = messages.get(error.code, t("error.messages.generic"))
        return render_page("error", status=error.code, page_title=f"{title} | Infinity Stream TV", error_title=title, error_message=message)

    @app.after_request
    def secure_response(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://wa.me"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.endpoint not in {"static", "sitemap", "robots"}:
            response.headers["Cache-Control"] = "no-store"
        query_lang = request.args.get("lang")
        if query_lang in i18n.SUPPORTED_LOCALES:
            response.set_cookie(
                "lang", query_lang, max_age=31536000, samesite="Lax",
                secure=app.config["SESSION_COOKIE_SECURE"], httponly=True,
            )
        return response

    @app.cli.command("prune-enquiries")
    def prune_enquiries():
        """Delete enquiries older than 90 days; run regularly for data minimization."""
        cutoff = datetime.fromtimestamp(time.time() - 90 * 86400, timezone.utc).isoformat(timespec="seconds")
        db = get_db()
        result = db.execute("DELETE FROM enquiries WHERE created_at < ?", (cutoff,))
        db.execute("DELETE FROM enquiry_limits WHERE attempted_at <= ?", (time.time() - app.config["ENQUIRY_RATE_WINDOW"],))
        db.commit()
        print(f"Removed {result.rowcount} enquiries older than 90 days.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
