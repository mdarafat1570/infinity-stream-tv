"""Behavioral checks for public routes, enquiries and the static preview."""

from html.parser import HTMLParser
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

import pytest

from app import PAGES, create_app
from build_static import export_site
from config import PROJECT_ROOT, site_origin


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and "name" in attrs:
            self.values[attrs["name"]] = attrs.get("value", "")


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-with-at-least-32-characters",
        "DATABASE": str(tmp_path / "enquiries.sqlite3"),
        "SITE_URL": "http://localhost:5000",
        "ENQUIRY_RATE_LIMIT": 5,
        "ENQUIRY_RATE_WINDOW": 600,
        "TRUST_PROXY_COUNT": 0,
    })


@pytest.fixture
def client(app):
    return app.test_client()


def form(client, **changes):
    parser = Inputs()
    response = client.get("/contact")
    assert response.status_code == 200
    parser.feed(response.get_data(as_text=True))
    assert parser.values.get("csrf_token"), "The live enquiry form must contain a CSRF token."
    values = {
        "name": "Test Customer", "country": "Bangladesh", "contact_method": "whatsapp",
        "contact": "+880 1310 993838", "message": "Please share the current Premium Plan details.",
        "plan": "premium", "source_page": "contact", "website": "",
        "csrf_token": parser.values["csrf_token"],
    }
    values.update(changes)
    return values


def stored(app):
    with sqlite3.connect(app.config["DATABASE"]) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM enquiries").fetchall()


@pytest.mark.parametrize("route", [value[0] for value in PAGES.values()])
def test_public_routes_have_metadata(client, route):
    response = client.get(route)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<meta name="description"' in html
    assert 'rel="canonical"' in html
    assert "Infinity Stream TV" in html
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("contact", ["+880 1310 993838", "+880.1310.993838"])
def test_success_saves_minimum_fields_and_opens_reviewable_whatsapp(client, app, contact):
    response = client.post("/enquiry", data=form(client, contact=contact))
    assert response.status_code == 303
    destination = urlsplit(response.location)
    assert destination.scheme == "https"
    assert destination.netloc == "wa.me"
    assert destination.path == "/8801310993838"
    text = parse_qs(destination.query)["text"][0]
    assert "Premium Plan" in text and "Test Customer" in text
    rows = stored(app)
    assert len(rows) == 1
    assert rows[0]["contact"] == "+8801310993838"
    assert rows[0]["status"] == "new"
    assert "ip" not in rows[0].keys()


def test_json_success_reports_saved_enquiry_not_sent_message(client, app):
    response = client.post("/enquiry", data=form(client, contact_method="email", contact="customer@example.com"), headers={"Accept": "application/json"})
    assert response.status_code == 200
    result = response.get_json()
    assert result["saved"] is True
    assert "Review and send" in result["message"]
    assert result["whatsapp_url"].startswith("https://wa.me/8801310993838?")
    assert len(stored(app)) == 1


@pytest.mark.parametrize("changes,field", [
    ({"name": "A"}, "name"),
    ({"country": ""}, "country"),
    ({"contact_method": "sms"}, "contact_method"),
    ({"contact": "not-a-number"}, "contact"),
    ({"contact_method": "email", "contact": "wrong@email"}, "contact"),
    ({"message": "short"}, "message"),
    ({"message": "x" * 2001}, "message"),
    ({"name": "Bad\x00Name"}, "name"),
    ({"plan": "https://attacker.example"}, "plan"),
])
def test_validation_rejects_invalid_input_without_saving(client, app, changes, field):
    response = client.post("/enquiry", data=form(client, **changes), headers={"Accept": "application/json"})
    assert response.status_code == 400
    assert field in response.get_json()["errors"]
    assert not stored(app)


def test_missing_csrf_and_cross_session_csrf_are_rejected(client, app):
    values = form(client)
    other_client = app.test_client()
    assert other_client.post("/enquiry", data=values, headers={"Accept": "application/json"}).status_code == 400
    values.pop("csrf_token")
    response = client.post("/enquiry", data=values, headers={"Accept": "application/json"})
    assert response.status_code == 400
    assert "_form" in response.get_json()["errors"]
    assert not stored(app)


def test_honeypot_does_not_save(client, app):
    response = client.post("/enquiry", data=form(client, website="https://spam.example"), headers={"Accept": "application/json"})
    assert response.status_code == 400
    assert not stored(app)


def test_rate_limit_is_shared_across_clients_and_expires(client, app):
    app.config["ENQUIRY_RATE_LIMIT"] = 2
    values = form(client, message="short")
    for _ in range(2):
        assert client.post("/enquiry", data=values, headers={"Accept": "application/json"}).status_code == 400
    other_client = app.test_client()
    response = other_client.post("/enquiry", data=form(other_client), headers={"Accept": "application/json"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    with sqlite3.connect(app.config["DATABASE"]) as db:
        db.execute("UPDATE enquiry_limits SET attempted_at = 0")
    assert client.post("/enquiry", data=form(client)).status_code == 303


def test_invalid_form_values_are_html_escaped(client):
    payload = '<script>alert("test")</script>'
    response = client.post("/enquiry", data=form(client, name=payload, message="short"))
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert payload not in html
    assert "&lt;script&gt;" in html


def test_sitemap_and_robots_use_configured_origin(client):
    response = client.get("/sitemap.xml")
    root = ET.fromstring(response.data)
    assert len(root) == len(PAGES)
    locations = [element.text for element in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert "http://localhost:5000/pricing" in locations
    assert "Sitemap: http://localhost:5000/sitemap.xml" in client.get("/robots.txt").get_data(as_text=True)


def test_unsupported_route_and_get_enquiry_are_safe(client):
    assert client.get("/unknown").status_code == 404
    assert client.get("/enquiry").location == "/contact#enquiry"
    assert client.get("/admin").status_code == 404
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400


def test_production_requires_strong_secret_and_https(tmp_path):
    configuration = {"APP_ENV": "production", "SITE_URL": "https://example.com", "DATABASE": str(tmp_path / "production.sqlite3")}
    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app({**configuration, "SECRET_KEY": "short"})
    with pytest.raises(ValueError, match="HTTPS"):
        create_app({**configuration, "SECRET_KEY": "a" * 64, "SITE_URL": "http://example.com"})
    production = create_app({**configuration, "SECRET_KEY": "a" * 64, "TRUSTED_HOSTS": ["example.com"]})
    assert production.config["SESSION_COOKIE_SECURE"] is True
    assert production.config["DEBUG"] is False
    response = production.test_client().get("/pricing", base_url="http://example.com")
    assert response.status_code == 308 and response.location == "https://example.com/pricing"
    secure = production.test_client().get("/contact", base_url="https://example.com")
    assert secure.status_code == 200
    assert "max-age=" in secure.headers["Strict-Transport-Security"]
    assert "Secure; HttpOnly" in secure.headers["Set-Cookie"]


@pytest.mark.parametrize("value", ["javascript:alert(1)", "https://user:pass@example.com", "https://example.com/path", "https://example.com?x=1"])
def test_canonical_origin_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        site_origin(value)


def test_static_export_is_portable_and_has_no_live_csrf(tmp_path):
    output = export_site(tmp_path / "preview", origin="https://example.com")
    for route, _title, _description in PAGES.values():
        page = output / route.strip("/") / "index.html"
        assert page.is_file()
    html = (output / "contact" / "index.html").read_text(encoding="utf-8")
    parser = Inputs()
    parser.feed(html)
    assert not parser.values.get("csrf_token")
    assert "https://example.com/contact" in html
    assert (output / "static" / "js" / "main.js").is_file()
    assert "https://example.com/pricing" in (output / "sitemap.xml").read_text(encoding="utf-8")
    assert (output / "404.html").is_file()
    assert not (output / "static" / "images" / "brand-original.jpg").exists()
    assert not (output / "static" / "images" / "artwork-provenance.md").exists()
    assert not (output / "instance").exists()
    assert not (output / ".env").exists()


def test_static_export_removes_old_source_artifacts(tmp_path):
    target = tmp_path / "preview"
    images = target / "static" / "images"
    images.mkdir(parents=True)
    (images / "brand-original.jpg").write_text("old export", encoding="utf-8")
    (images / "artwork-provenance.md").write_text("old export", encoding="utf-8")
    export_site(target, origin="https://example.com")
    assert not (images / "brand-original.jpg").exists()
    assert not (images / "artwork-provenance.md").exists()


def test_static_export_rejects_source_directory_overlap():
    for target in (PROJECT_ROOT, PROJECT_ROOT.parent, PROJECT_ROOT / "static", PROJECT_ROOT / "static" / "preview"):
        with pytest.raises(ValueError):
            export_site(target)
