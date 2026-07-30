"""Database connection & SQLAlchemy models"""
import os
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import enum

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class EquipmentStatus(str, enum.Enum):
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    OVERDUE = "overdue"


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_id = Column(String(20), unique=True, nullable=False, index=True)
    equipment_type = Column(String(50), nullable=False)
    site_id = Column(String(20), nullable=True)
    operator_id = Column(String(20), nullable=True)
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    engine_hours = Column(Float, default=0.0)
    idle_hours = Column(Float, default=0.0)
    fuel_used = Column(Float, default=0.0)
    status = Column(String(20), default=EquipmentStatus.CHECKED_OUT.value)
    rental_cost = Column(Float, default=0.0)
    daily_rental_rate = Column(Float, default=0.0)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_id = Column(String(20), nullable=False, index=True)
    date = Column(DateTime, nullable=False)
    engine_hours = Column(Float, default=0.0)
    idle_hours = Column(Float, default=0.0)
    fuel_used = Column(Float, default=0.0)
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)


def init_db():
    Base.metadata.create_all(engine)
