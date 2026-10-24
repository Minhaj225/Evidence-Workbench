from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def create_database(url: str) -> sessionmaker:
    from sqlalchemy.engine import make_url

    path = make_url(url).database
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: Any, record: Any) -> None:
        if str(engine.url).startswith("sqlite"):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return sessionmaker(engine, expire_on_commit=False)
