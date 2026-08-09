import unittest
from pathlib import Path


WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = WEB_PORTAL_DIR / "static"
TEMPLATES_DIR = WEB_PORTAL_DIR / "templates"


class BrandUiContractTest(unittest.TestCase):
    def test_shared_tokens_define_brand_and_semantic_color_roles(self):
        stylesheet = (STATIC_DIR / "brand.css").read_text(encoding="utf-8")
        expected_tokens = (
            "--brand-primary: #29415d",
            "--brand-primary-hover: #20344a",
            "--brand-accent: #c39a55",
            "--color-canvas: #f5f6f8",
            "--color-text: #18212b",
            "--color-danger: #a63d3d",
            "--color-line: #06c755",
        )
        for token in expected_tokens:
            with self.subTest(token=token):
                self.assertIn(token, stylesheet)

    def test_every_portal_entry_loads_shared_tokens_in_safe_order(self):
        entries = {
            "home.html": "auth.css",
            "account.html": "member_portal.css",
            "attendance.html": "member_portal.css",
            "game_roster.html": "member_portal.css",
            "not_authenticated.html": "auth.css",
            "line_login_error.html": "auth.css",
            "redirect_page.html": "auth.css",
        }
        for template_name, component_css in entries.items():
            with self.subTest(template=template_name):
                template = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
                self.assertIn("filename='brand.css'", template)
                self.assertLess(template.index("filename='brand.css'"), template.index(f"filename='{component_css}'"))

        demo_base = (TEMPLATES_DIR / "demo" / "base.html").read_text(encoding="utf-8")
        self.assertGreater(demo_base.index("filename='brand.css'"), demo_base.index("filename='officer_nav.css'"))

    def test_auth_and_member_styles_use_shared_brand_tokens(self):
        auth_css = (STATIC_DIR / "auth.css").read_text(encoding="utf-8")
        member_css = (STATIC_DIR / "member_portal.css").read_text(encoding="utf-8")
        for legacy_brand_color in ("#173f35", "#255e4e", "#f4f2eb"):
            with self.subTest(color=legacy_brand_color):
                self.assertNotIn(legacy_brand_color, auth_css.lower())
                self.assertNotIn(legacy_brand_color, member_css.lower())
        self.assertIn("var(--color-line)", auth_css)
        self.assertIn("var(--brand-primary)", member_css)

    def test_member_navigation_keeps_home_visible_with_core_links(self):
        navigation = (TEMPLATES_DIR / "_member_nav.html").read_text(encoding="utf-8")
        self.assertIn("url_for('home')", navigation)
        self.assertIn("url_for('attendance')", navigation)
        self.assertIn("url_for('account')", navigation)
        member_css = (STATIC_DIR / "member_portal.css").read_text(encoding="utf-8")
        self.assertIn("overflow-x: auto", member_css)

    def test_game_and_account_pages_share_mobile_contract(self):
        shared_pages = (
            "attendance.html",
            "game_roster.html",
            "account.html",
        )
        for template_name in shared_pages:
            with self.subTest(template=template_name):
                template = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
                self.assertIn("filename='brand.css'", template)
                self.assertIn("filename='member_portal.css'", template)
                self.assertIn("_member_nav.html", template)
        for template_name in (
            "dashboard.html",
            "games.html",
            "game_detail.html",
            "game_day.html",
            "profile.html",
        ):
            with self.subTest(template=template_name):
                template = (TEMPLATES_DIR / "demo" / template_name).read_text(
                    encoding="utf-8"
                )
                self.assertIn("extends 'demo/base.html'", template)
        css = (STATIC_DIR / "member_portal.css").read_text(encoding="utf-8")
        for contract in (
            "min-height: 44px",
            "focus-visible",
            ".member-nav",
        ):
            self.assertIn(contract, css)

    def test_theme_color_and_notice_semantics_follow_brand_roles(self):
        demo_base = (TEMPLATES_DIR / "demo" / "base.html").read_text(encoding="utf-8")
        brand_css = (STATIC_DIR / "brand.css").read_text(encoding="utf-8")
        event_detail = (TEMPLATES_DIR / "demo" / "events" / "detail.html").read_text(encoding="utf-8")

        self.assertIn('name="theme-color" content="#29415d"', demo_base)
        self.assertNotIn('name="theme-color" content="#173f35"', demo_base)
        self.assertIn(".metric.warning { background: var(--color-warning-soft)", brand_css)
        self.assertIn(".notice.notice-danger", brand_css)
        self.assertIn('class="notice notice-danger"', event_detail)


if __name__ == "__main__":
    unittest.main()
