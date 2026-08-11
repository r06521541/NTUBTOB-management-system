"""Run the fictional Web Portal preview with localhost live reload."""

import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_PORTAL_ROOT = REPOSITORY_ROOT / "apps" / "web_portal"
SHARED_LIB_ROOT = REPOSITORY_ROOT / "shared_lib"


def main() -> None:
    os.environ.update(
        {
            "WEB_PORTAL_ENV": "development",
            "WEB_PORTAL_LOCAL_PREVIEW_MODE": "true",
            "WEB_PORTAL_FICTIONAL_DEMO_MODE": "true",
            "WEB_PORTAL_DEMO_MODE": "false",
            "WEB_PORTAL_BIND_HOST": "127.0.0.1",
            "PORTAL_DATA_PHASE_C_ENABLED": "true",
            "DSN_HOSTNAME": "127.0.0.1",
            "DSN_PORT": "55432",
            "DSN_DATABASE": "ntubtob_portal_local",
            "DSN_UID": "portal_local",
            "DSN_PASSWORD": "local-only-password",
            "PORTAL_DATA_DATABASE_URL": (
                "postgresql+psycopg2://portal_local:local-only-password@"
                "127.0.0.1:55432/ntubtob_portal_local"
            ),
        }
    )
    sys.path.insert(0, str(SHARED_LIB_ROOT))
    sys.path.insert(0, str(WEB_PORTAL_ROOT))

    from app import app

    app.run(host="127.0.0.1", port=8080, debug=True, use_reloader=True)


if __name__ == "__main__":
    main()
