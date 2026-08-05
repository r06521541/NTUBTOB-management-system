import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PACKAGE_DIR = Path(__file__).resolve().parents[1]


class PackageImportTests(unittest.TestCase):
    def test_package_import_has_no_line_helper_side_effect(self):
        constructor = Mock(
            side_effect=AssertionError(
                "LineBotAnnouncementHelper must not be constructed on package import"
            )
        )
        announcement = types.ModuleType("shared_module.announcement")
        linebot = types.ModuleType("shared_module.announcement.linebot")
        linebot.LineBotAnnouncementHelper = constructor

        spec = importlib.util.spec_from_file_location(
            "notify_cronjob_package_under_test",
            PACKAGE_DIR / "__init__.py",
            submodule_search_locations=[str(PACKAGE_DIR)],
        )
        package = importlib.util.module_from_spec(spec)

        with patch.dict(
            sys.modules,
            {
                "shared_module.announcement": announcement,
                "shared_module.announcement.linebot": linebot,
            },
        ):
            spec.loader.exec_module(package)

        constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
