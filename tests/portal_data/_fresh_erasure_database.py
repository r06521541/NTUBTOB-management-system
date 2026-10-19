"""Small, single-owner disposable PostgreSQL fixture; never a general DB cleaner.

Only generated, confirmed-created databases can be dropped. No force/retry or
base-database DDL. Callers must inspect close() errors separately from test errors.
Initialization callbacks are trusted and must close all connections they open.
"""

from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from shared_lib.shared_module.portal_data.local_database import (
    LOCAL_DATABASE_NAME,
    require_local_database_url,
)

ENGINE_OPTIONS = {
    "connect_args": {
        "connect_timeout": 5,
        "options": "-c statement_timeout=5000 -c lock_timeout=5000",
    },
    "pool_timeout": 5,
}


class FreshDatabaseError(RuntimeError):
    def __init__(self, operation, database_name=None):
        self.operation = operation
        self.database_name = database_name
        super().__init__(f"fresh database fixture failed: {operation}")
        self.__suppress_context__ = True


class FreshErasureDatabases:
    def __init__(self, base_url):
        try:
            self._url = make_url(require_local_database_url(base_url))
            if (
                self._url.query
                or self._url.host not in {"127.0.0.1", "localhost", "::1"}
                or self._url.database != LOCAL_DATABASE_NAME
            ):
                raise ValueError
        except Exception:
            raise FreshDatabaseError("validate_url") from None
        try:
            self._admin = create_engine(
                self._url, isolation_level="AUTOCOMMIT", **ENGINE_OPTIONS
            )
        except Exception:
            raise FreshDatabaseError("admin_engine") from None
        self._owned = {}
        self._attempted = set()
        self._errors = []
        self._template = None
        self._template_started = self._closed = self._uncertain = False

    def _open(self):
        if self._closed or self._uncertain:
            raise FreshDatabaseError("state") from None

    def _create(self, template):
        name = "ntubtob_erasure_" + uuid4().hex
        quote = self._admin.dialect.identifier_preparer.quote
        try:
            with self._admin.connect() as connection:
                connection.exec_driver_sql(
                    f"CREATE DATABASE {quote(name)} TEMPLATE {quote(template)}"
                )
        except Exception:
            self._uncertain = True
            raise FreshDatabaseError("create", name) from None
        self._owned[name] = None  # CREATE acknowledged; engine construction may fail.
        try:
            engine = create_engine(self._url.set(database=name), **ENGINE_OPTIONS)
        except Exception:
            raise FreshDatabaseError("engine", name) from None
        self._owned[name] = engine
        return name, engine

    def create_template(self, initialize):
        self._open()
        if self._template_started or not callable(initialize):
            raise FreshDatabaseError("template_state") from None
        self._template_started = True
        name, engine = self._create("template0")
        failure = None
        try:
            initialize(engine)
        except Exception:
            failure = FreshDatabaseError("initialize", name)
        try:
            engine.dispose()
        except Exception:
            error = FreshDatabaseError("dispose", name)
            self._attempted.add(name)
            self._errors.append(error)
            failure = failure or error
        if failure is not None:
            raise failure from None
        self._template = name

    def clone(self):
        self._open()
        if self._template is None:
            raise FreshDatabaseError("template_unavailable") from None
        return self._create(self._template)[1]

    def release(self, engine):
        self._open()
        name = next(
            (
                name
                for name, owned in self._owned.items()
                if owned is not None and owned is engine
            ),
            None,
        )
        if name is None or name in self._attempted:
            raise FreshDatabaseError("release_unowned") from None
        self._release(name)

    def _release(self, name):
        self._attempted.add(name)  # No automatic resend after any cleanup uncertainty.
        if name == self._template:
            self._template = None
        stage = "dispose"
        try:
            if self._owned[name] is not None:
                self._owned[name].dispose()
            stage = "drop_preflight"
            with self._admin.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT pg_catalog.pg_get_userbyid(d.datdba)=CURRENT_USER, "
                        "(SELECT count(*) FROM pg_catalog.pg_stat_activity a "
                        "WHERE a.datid=d.oid) FROM pg_catalog.pg_database d "
                        "WHERE d.datname=:name"
                    ),
                    {"name": name},
                ).one_or_none()
                if (
                    row is None
                    or len(row) != 2
                    or row[0] is not True
                    or type(row[1]) is not int
                    or row[1] != 0
                ):
                    raise ValueError
                stage = "drop"
                quote = self._admin.dialect.identifier_preparer.quote
                connection.exec_driver_sql(f"DROP DATABASE {quote(name)}")
            del self._owned[name]
        except Exception:
            error = FreshDatabaseError(stage, name)
            self._errors.append(error)
            raise error from None

    def close(self):
        """One cleanup pass; return safe secondary failures without masking primary."""
        if not self._closed:
            self._closed = True
            for name in reversed(tuple(self._owned)):
                if name not in self._attempted:
                    try:
                        self._release(name)
                    except FreshDatabaseError:
                        pass
            try:
                self._admin.dispose()
            except Exception:
                self._errors.append(FreshDatabaseError("admin_dispose"))
        return tuple(self._errors)
