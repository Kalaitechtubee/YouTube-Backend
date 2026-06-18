import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./media_downloader.db")

# SQLite special arguments for thread safety
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
