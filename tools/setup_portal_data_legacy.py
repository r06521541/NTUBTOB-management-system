from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)

LEGACY_FIXTURE_SQL = """
CREATE SCHEMA IF NOT EXISTS ntubtob;
CREATE TABLE IF NOT EXISTS ntubtob.members (
  id integer PRIMARY KEY,
  name varchar NOT NULL
);
CREATE TABLE IF NOT EXISTS ntubtob.games (
  id integer PRIMARY KEY,
  year integer NOT NULL,
  season integer NOT NULL,
  start_datetime timestamp NOT NULL,
  duration integer NOT NULL,
  location varchar NOT NULL,
  home_team varchar NOT NULL,
  away_team varchar NOT NULL,
  invitation_time timestamp NULL,
  cancellation_time timestamp NULL,
  cancellation_announcement_time timestamp NULL
);
INSERT INTO ntubtob.members (id, name) VALUES
  (7001, '虛構校友甲'),
  (7002, '虛構校友乙')
ON CONFLICT (id) DO NOTHING;
"""


def main() -> None:
    database_url = require_local_database_url(
        os.environ.get("PORTAL_DATA_DATABASE_URL")
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(LEGACY_FIXTURE_SQL))
    engine.dispose()
    print("local legacy fixture ready")


if __name__ == "__main__":
    main()
