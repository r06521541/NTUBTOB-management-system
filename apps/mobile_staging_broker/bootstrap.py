"""Gunicorn entry point with lazy privileged initialization."""

import threading

from .app import create_app

_runtime = None
_runtime_lock = threading.Lock()


def _runtime_factory():
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            from .runtime import build_runtime

            _runtime = build_runtime()
        return _runtime


app = create_app(_runtime_factory)
