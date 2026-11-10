from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=None, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(settings.database_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
