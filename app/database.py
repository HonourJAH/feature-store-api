from sqlmodel import create_engine, Session, SQLModel
import os

from app.model import FeatureSnapshot

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./feature_store.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def init_db():
    """Create all tables. Called once at startup, or via Alembic in production."""
    SQLModel.metadata.create_all(engine)


def get_db():
    """FastAPI dependency — yields a session, closes it when the request finishes."""
    with Session(engine) as session:
        yield session
