import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    client = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    scope_notes = Column(Text, nullable=True)
    status = Column(String(20), default="active", index=True)  # active | archived
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    tokens = relationship("Token", back_populates="assessment",
                          cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="assessment",
                        cascade="all, delete-orphan")


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    name = Column(String(200), nullable=False)
    enc_access_token = Column(Text, nullable=True)
    enc_refresh_token = Column(Text, nullable=True)
    tenant_id = Column(String(100), nullable=True)
    username = Column(String(200), nullable=True)
    scope = Column(Text, nullable=True)
    audience = Column(String(255), nullable=True)
    expires = Column(Integer, nullable=True)  # unix epoch from JWT exp
    created_at = Column(DateTime, default=utcnow)

    assessment = relationship("Assessment", back_populates="tokens")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    activity = Column(String(60), nullable=False, index=True)
    label = Column(String(255), nullable=True)
    status = Column(String(20), default="pending", index=True)
    # pending | running | completed | failed | cancelled | awaiting_input
    params = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    assessment = relationship("Assessment", back_populates="jobs")
    logs = relationship("JobLog", back_populates="job",
                        cascade="all, delete-orphan", order_by="JobLog.id")


class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    ts = Column(DateTime, default=utcnow)
    level = Column(String(20), default="info")
    message = Column(Text, nullable=False)

    job = relationship("Job", back_populates="logs")
