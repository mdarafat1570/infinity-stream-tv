"""Render a portable preview with WhatsApp-only forms and no backend claims."""

import argparse
from pathlib import Path
import shutil
import tempfile

from flask import render_template

from app import PAGES, create_app, page_context, robots_text, sitemap_xml
from config import PROJECT_ROOT, site_origin


SOURCE_ONLY_IMAGES = {"brand-original.jpg", "artwork-provenance.md"}


def _reference_is_used() -> bool:
    source_files = list((PROJECT_ROOT / "templates").rglob("*.html"))
    for pattern in ("*.css", "*.js"):
        source_files.extend((PROJECT_ROOT / "static").rglob(pattern))
    return any("reference.png" in source.read_text(encoding="utf-8") for source in source_files)


def _copy_public_assets(target: Path) -> None:
    """Keep originals/provenance in source, but deploy only the public assets."""
    excluded = SOURCE_ONLY_IMAGES | (set() if _reference_is_used() else {"reference.png"})
    image_source = (PROJECT_ROOT / "static" / "images").resolve()

    def ignore_sources(directory, names):
        return excluded.intersection(names) if Path(directory).resolve() == image_source else set()

    shutil.copytree(PROJECT_ROOT / "static", target / "static", dirs_exist_ok=True, ignore=ignore_sources)
    # Remove only these known source artifacts from a previous export. Their
    # originals are preserved in the project's static/images directory.
    for filename in excluded:
        artifact = target / "static" / "images" / filename
        if artifact.is_file():
            if target not in artifact.resolve().parents:
                raise ValueError("A stale export artifact points outside the export directory.")
            artifact.unlink()


def export_site(output: str | Path = "dist", *, origin: str | None = None) -> Path:
    target = Path(output).resolve()
    if target == PROJECT_ROOT or target in PROJECT_ROOT.parents:
        raise ValueError("The export directory cannot be the project directory or one of its parents.")
    for protected in ("static", "templates", "data", ".venv", "instance", "tests"):
        source_directory = PROJECT_ROOT / protected
        if target == source_directory or source_directory in target.parents:
            raise ValueError("The export directory must not overlap source files or private application data.")
    with tempfile.TemporaryDirectory(prefix="infinity-static-") as temporary:
        overrides = {
            "APP_ENV": "development",
            "TESTING": True,
            "SECRET_KEY": "static-render-only-no-sessions-are-exported",
            "DATABASE": str(Path(temporary) / "unused.sqlite3"),
        }
        if origin:
            overrides["SITE_URL"] = site_origin(origin)
        app = create_app(overrides)
        target.mkdir(parents=True, exist_ok=True)
        with app.test_request_context("/"):
            for slug, (route, _title, _description) in PAGES.items():
                directory = target if route == "/" else target / route.strip("/")
                directory.mkdir(parents=True, exist_ok=True)
                template = "index.html" if slug == "home" else "page.html"
                html = render_template(template, **page_context(slug, is_static=True))
                (directory / "index.html").write_text(html, encoding="utf-8")
            (target / "404.html").write_text(
                render_template(
                    "page.html",
                    **page_context(
                        "error", is_static=True, page_title="Page not found | Infinity Stream TV",
                        error_title="Page not found", error_message="Explore our plans or contact the team to find what you need.",
                    ),
                ),
                encoding="utf-8",
            )
            (target / "sitemap.xml").write_text(sitemap_xml(), encoding="utf-8")
            (target / "robots.txt").write_text(robots_text(), encoding="utf-8")
        _copy_public_assets(target)
        # Applied by hosts supporting Netlify-style headers. Configure equivalent
        # headers on other hosts; static files do not run Flask's response hooks.
        (target / "_headers").write_text(
            "/*\n"
            "  X-Content-Type-Options: nosniff\n"
            "  X-Frame-Options: DENY\n"
            "  Referrer-Policy: strict-origin-when-cross-origin\n"
            "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
            "  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://wa.me\n",
            encoding="utf-8",
        )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dist", help="Directory to write the portable site into.")
    parser.add_argument("--site-url", help="Public canonical origin; otherwise uses SITE_URL from the environment.")
    args = parser.parse_args()
    destination = export_site(args.output, origin=args.site_url)
    print(f"Exported {len(PAGES)} pages and static assets to {destination}")
