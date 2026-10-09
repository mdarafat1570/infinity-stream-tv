"""Environment configuration for the website and enquiry service."""

from datetime import timedelta
from pathlib import Path
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def site_origin(value: str) -> str:
    """Accept only a canonical HTTP(S) origin, never credentials or a path."""
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("SITE_URL must be an HTTP(S) origin, for example https://example.com")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def environment_config() -> dict:
    production = os.getenv("APP_ENV", "development").lower() == "production"
    origin = site_origin(os.getenv("SITE_URL", "http://localhost:5000"))
    if production and not origin.startswith("https://"):
        raise ValueError("Production SITE_URL must use HTTPS.")
    configured_hosts = os.getenv("TRUSTED_HOSTS", "").strip()
    hosts = (
        [host.strip() for host in configured_hosts.split(",") if host.strip()]
        if configured_hosts
        else [urlsplit(origin).hostname, "localhost", "127.0.0.1"]
    )
    if production and not configured_hosts:
        hosts = [urlsplit(origin).hostname]
    return {
        "APP_ENV": "production" if production else "development",
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "SITE_URL": origin,
        "DATABASE": os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "instance" / "enquiries.sqlite3")),
        "SITE_DATA_FILE": str(PROJECT_ROOT / "data" / "site.json"),
        "TRUSTED_HOSTS": hosts,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SECURE": production,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=2),
        "WTF_CSRF_TIME_LIMIT": 3600,
        "MAX_CONTENT_LENGTH": 16 * 1024,
        "MAX_FORM_MEMORY_SIZE": 16 * 1024,
        "MAX_FORM_PARTS": 20,
        "ENQUIRY_RATE_LIMIT": int(os.getenv("ENQUIRY_RATE_LIMIT", "5")),
        "ENQUIRY_RATE_WINDOW": int(os.getenv("ENQUIRY_RATE_WINDOW", "600")),
        "TRUST_PROXY_COUNT": int(os.getenv("TRUST_PROXY_COUNT", "0")),
        "PREFERRED_URL_SCHEME": "https" if production else "http",
        "DEBUG": False,
    }
