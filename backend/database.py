from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import create_engine

Base = declarative_base()


class TransactionRecord(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, unique=True, index=True, nullable=False)
    customer_id = Column(String, index=True, nullable=False)
    customer_type = Column(String, default="Retail")
    transaction_type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    merchant_category = Column(String, default="general")
    country = Column(String, default="US")
    city = Column(String, default="Unknown")
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")
    source = Column(String, default="manual")
    model_result = Column(String, default="legitimate")
    risk_score = Column(Float, default=0.0)
    anomaly_score = Column(Float, default=0.0)
    prediction_probability = Column(Float, default=0.0)
    explanation = Column(Text, default="")
    record_hash = Column(String, unique=True, index=True)
    previous_hash = Column(String, default="")
    blockchain_hash = Column(String, default="")
    block_number = Column(Integer, default=0)
    audit_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    alerts = relationship("AlertRecord", back_populates="transaction")
    audits = relationship("AuditRecord", back_populates="transaction")


class AlertRecord(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), index=True)
    alert_type = Column(String, default="fraud")
    severity = Column(String, default="medium")
    risk_score = Column(Float, default=0.0)
    model_result = Column(String, default="review")
    reason = Column(Text, default="")
    status = Column(String, default="new")
    created_at = Column(DateTime, default=datetime.utcnow)
    transaction = relationship("TransactionRecord", back_populates="alerts")


class AuditRecord(Base):
    __tablename__ = "audit_history"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), index=True)
    previous_hash = Column(String, default="")
    record_hash = Column(String, default="")
    blockchain_hash = Column(String, default="")
    block_number = Column(Integer, default=0)
    verification_passed = Column(Boolean, default=False)
    tampered = Column(Boolean, default=False)
    summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    transaction = relationship("TransactionRecord", back_populates="audits")


DATABASE_URL = "sqlite:///./bank_fraud.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
