import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
	"DATABASE_URL",
	"postgresql+psycopg2://preplace_user:preplace_pass@localhost:5433/preplac",
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # recycle connections after 1 hour to avoid stale connections
    pool_pre_ping=True,  # verify connection health before use
)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()