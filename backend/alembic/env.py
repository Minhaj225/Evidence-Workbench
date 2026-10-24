from alembic import context

from backend.app.models import Base

connection = context.config.attributes.get("connection")
if connection is None:
    from sqlalchemy import create_engine

    from backend.app.config import Settings

    engine = create_engine(Settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
else:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
