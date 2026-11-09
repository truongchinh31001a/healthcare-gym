from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings
class Base(DeclarativeBase):
    pass
def make_engine(url, **kwargs):
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True,
                           connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine
engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
