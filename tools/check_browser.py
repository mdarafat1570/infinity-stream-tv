"""Browser smoke checks and responsive screenshots using an existing local browser.

Run: python tools/check_browser.py --base-url http://127.0.0.1:5050
No WhatsApp navigation or real form submission is performed.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


ROUTES = ["/", "/pricing", "/channels", "/devices", "/reseller", "/faq", "/contact", "/privacy", "/terms", "/refund-policy"]
WIDTHS = [360, 390, 768, 1024, 1440, 1920]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5050")
    parser.add_argument("--output", default="output/qa")
    parser.add_argument("--browser", help="Optional existing Chromium executable")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    report = {"base_url": args.base_url, "checks": [], "page_errors": [], "console_errors": [], "network_errors": [], "responses": []}

    def check(name, callback):
        try:
            result = callback()
            report["checks"].append({"name": name, "passed": True, "details": result})
        except Exception as exc:
            report["checks"].append({"name": name, "passed": False, "details": str(exc)})

    with sync_playwright() as p:
        candidates = [args.browser, r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe", p.chromium.executable_path]
        executable = next((str(path) for path in candidates if path and Path(path).is_file()), None)
        if not executable:
            raise SystemExit("No installed Chromium, Edge, or Chrome executable found.")
        browser = p.chromium.launch(executable_path=executable, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.route("https://wa.me/**", lambda route: route.abort())
        page = context.new_page()
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.on("console", lambda msg: report["console_errors"].append({"page": page.url, "text": msg.text}) if msg.type == "error" else None)
        page.on("requestfailed", lambda req: report["network_errors"].append({"url": req.url, "error": req.failure}) if "wa.me/" not in req.url else None)
        page.on("response", lambda response: report["responses"].append({"url": response.url, "status": response.status}) if response.status >= 400 else None)
        page.set_default_timeout(10000)

        def visit(route, width=1440, capture=True):
            page.set_viewport_size({"width": width, "height": 1000})
            response = page.goto(args.base_url.rstrip("/") + route, wait_until="networkidle")
            assert response and response.status == 200, f"HTTP {response.status if response else 'missing'}"
            page.evaluate("async () => { document.querySelectorAll('img').forEach(img => img.loading = 'eager'); await document.fonts.ready; await Promise.all([...document.images].map(img => img.complete ? Promise.resolve() : new Promise(resolve => { img.onload = resolve; img.onerror = resolve; setTimeout(resolve, 3000); }))); }")
            page.wait_for_timeout(100)
            dimensions = page.evaluate("() => ({width: innerWidth, html: document.documentElement.scrollWidth, body: document.body.scrollWidth, fonts: document.fonts.status, brokenImages: [...document.images].filter(img => !img.complete || !img.naturalWidth).map(img => img.src)})")
            name = route.split("?")[0].strip("/").replace("/", "-") or "home"
            if capture:
                page.screenshot(path=str(out / f"{name}-{width}.png"), full_page=True)
                if name == "home" and width in [390, 1440]:
                    page.screenshot(path=str(out / f"home-{width}-top.png"), full_page=False)
            assert max(dimensions["html"], dimensions["body"]) <= width + 1, dimensions
            assert not dimensions["brokenImages"], dimensions
            assert page.title(), "Missing page title"
            assert page.locator("h1").count() == 1, "Expected one primary heading"
            return dimensions

        for width in WIDTHS:
            check(f"home responsive {width}px", lambda width=width: visit("/", width))
        for route in ROUTES[1:]:
            for width in [360, 1440]:
                check(f"{route} responsive {width}px", lambda route=route, width=width: visit(route, width))

        def mobile_menu():
            visit("/", 390, False)
            toggle = page.locator(".menu-toggle")
            toggle.focus()
            page.keyboard.press("Enter")
            assert toggle.get_attribute("aria-expanded") == "true"
            assert page.locator("#mobile-nav").is_visible()
            page.keyboard.press("Escape")
            assert toggle.get_attribute("aria-expanded") == "false"
            assert page.locator("#mobile-nav").is_hidden()
            assert toggle.evaluate("el => el === document.activeElement")
            return "Keyboard Enter opens; Escape closes and returns focus"

        check("mobile menu keyboard and Escape", mobile_menu)

        def billing():
            visit("/pricing", 1440, False)
            config = page.locator("#site-config").evaluate("el => JSON.parse(el.textContent)")
            for period in ["quarterly", "yearly", "monthly"]:
                page.locator(f'[data-period="{period}"]').click()
                assert page.locator('[data-period][aria-pressed="true"]').count() == 1
                assert page.locator(f'[data-period="{period}"]').get_attribute("aria-pressed") == "true"
                for plan in config["plans"]:
                    href = page.locator(f'[data-whatsapp="plan"][data-plan="{plan["slug"]}"]').get_attribute("href")
                    parsed = urlparse(href)
                    message = parse_qs(parsed.query)["text"][0]
                    assert parsed.netloc == "wa.me" and parsed.path == "/8801874608217", href
                    assert plan["name"] in message and f"{period} billing" in message, message
            visit("/pricing?period=yearly", 1440, False)
            assert page.locator('[data-period="yearly"]').get_attribute("aria-pressed") == "true"
            return "All plan links use the correct phone, selected plan and billing period; query works"

        check("billing tabs and WhatsApp URLs", billing)

        def categories():
            visit("/channels?category=movies", 1440, False)
            assert page.locator('[data-category]:visible').count() == 1
            assert page.locator('[data-category="movies"]').is_visible()
            assert page.locator('[data-category-filter="movies"]').get_attribute("aria-pressed") == "true"
            page.locator('[data-category-filter="sports"]').click()
            assert parse_qs(urlparse(page.url).query)["category"] == ["sports"]
            assert page.locator('[data-category="sports"]').is_visible()
            page.locator('[data-category-filter="all"]').click()
            assert page.locator('[data-category]:visible').count() == 8
            assert "category" not in parse_qs(urlparse(page.url).query)
            return "Direct category query and interactive filtering work"

        check("category filtering and links", categories)

        def faq():
            visit("/faq", 390, False)
            first = page.locator("details.faq-item").first
            first.locator("summary").focus()
            page.keyboard.press("Enter")
            assert first.get_attribute("open") is not None
            assert first.locator(".faq-answer").is_visible()
            return "FAQ expands with keyboard"

        check("FAQ keyboard expansion", faq)

        def form_draft():
            visit("/contact?country=Bangladesh&plan=basic", 390, False)
            assert page.locator('[name="country"]').input_value() == "Bangladesh"
            page.evaluate("() => { document.body.dataset.static = 'true'; window.__drafts = []; window.open = url => { window.__drafts.push(url); return null; }; }")
            form = page.locator("[data-enquiry-form]")
            form.locator('[type="submit"]').click()
            assert page.evaluate("window.__drafts.length") == 0, "Empty form opened a draft"
            page.locator('[name="name"]').fill("Browser QA")
            page.locator('[name="contact"]').fill("invalid contact")
            page.locator('[name="message"]').fill("Please confirm device compatibility for this draft enquiry.")
            form.locator('[type="submit"]').click()
            assert page.evaluate("window.__drafts.length") == 0, "Invalid phone opened a draft"
            page.locator('[name="contact_method"]').select_option("email")
            assert page.locator('[name="contact"]').get_attribute("type") == "email"
            page.locator('[name="contact"]').fill("qa@example.com")
            form.locator('[type="submit"]').click()
            drafts = page.evaluate("window.__drafts")
            assert len(drafts) == 1, drafts
            message = parse_qs(urlparse(drafts[0]).query)["text"][0]
            assert "Browser QA" in message and "Bangladesh" in message and "qa@example.com" in message
            assert "draft is ready" in form.locator(".form-feedback").inner_text()
            assert page.url.startswith(args.base_url), "Unexpected external navigation"
            return "Required fields and invalid phone blocked; valid email created intercepted WhatsApp draft"

        check("static form validation and intercepted draft", form_draft)
        check("favicon loads", lambda: context.request.get(args.base_url + "/static/images/favicon.svg").status == 200 or (_ for _ in ()).throw(AssertionError("Favicon failed")))
        browser.close()

    report["passed"] = all(item["passed"] for item in report["checks"]) and not any(report[key] for key in ["page_errors", "network_errors", "responses", "console_errors"])
    (out / "browser-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    failed = [item for item in report["checks"] if not item["passed"]]
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"]), "failures": failed, "page_errors": report["page_errors"], "console_errors": report["console_errors"], "network_errors": report["network_errors"], "responses": report["responses"], "output": str(out.resolve())}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
