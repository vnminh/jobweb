"""ORM models. Column names follow the CareerBuilder 2012 TSV files (users.tsv, user_history.tsv, jobs.tsv, apps.tsv)
plus the attributes extracted by the JobUNICORN pipeline (O*NET occupation, skills, job type, seniority, degree, years).

Fields that the dataset does not have (accounts, companies, application status) are demo extensions and are marked so.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import relationship

from .db import Base

ROLES = ("admin", "recruiter", "seeker")
DEGREES = ["None", "High School", "Vocational", "Associate's", "Bachelor's", "Master's", "PhD"]  # users.tsv DegreeType, index = degree_ord
JOB_TYPES = {"full_time": "full-time", "part_time": "part-time", "contract": "contract", "temporary": "temporary", "internship": "internship"}
SENIORITY = ["entry", "mid", "senior", "manager", "executive"]
APP_STATUS = ("submitted", "viewed", "shortlisted", "rejected", "hired")  # demo extension: apps.tsv only records submissions


class Account(Base):  # demo extension (the dataset has no logins)
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(100), nullable=False)
    role = Column(String(16), nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    seeker = relationship("SeekerProfile", back_populates="account", uselist=False, cascade="all, delete-orphan")
    company = relationship("Company", back_populates="account", uselist=False, cascade="all, delete-orphan")


class SeekerProfile(Base):  # users.tsv
    __tablename__ = "seeker_profiles"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), unique=True, nullable=False)
    dataset_user_id = Column(Integer, unique=True, index=True)  # UserID (None for users who registered on the web)
    window_id = Column(Integer, default=7, nullable=False)  # WindowID
    split = Column(String(8))  # Split (Train/Test)
    city = Column(String(80))
    city_key = Column(String(120))  # P2 normalised "city|STATE" (= graph city node key)
    state = Column(String(8), index=True)
    country = Column(String(8), default="US")
    zip5 = Column(String(10))
    degree_type = Column(String(20), default="None")  # DegreeType
    degree_ord = Column(Integer, default=0)
    major = Column(String(120))
    graduation_date = Column(DateTime)
    work_history_count = Column(Integer, default=0)
    total_years_experience = Column(Float)
    currently_employed = Column(Boolean, default=False)
    managed_others = Column(Boolean, default=False)
    managed_how_many = Column(Integer, default=0)
    lat = Column(Float)
    lon = Column(Float)
    # pipeline-derived (P3): last held O*NET occupation and seniority; index of the user in the encoder's embedding table
    last_occ = Column(String(12))
    seniority = Column(String(12))
    world_idx = Column(Integer, index=True)
    account = relationship("Account", back_populates="seeker")
    history = relationship("WorkHistory", back_populates="seeker", order_by="WorkHistory.sequence", cascade="all, delete-orphan")


class WorkHistory(Base):  # user_history.tsv
    __tablename__ = "work_history"
    id = Column(Integer, primary_key=True)
    seeker_id = Column(Integer, ForeignKey("seeker_profiles.id"), index=True, nullable=False)
    sequence = Column(Integer, nullable=False)  # Sequence (1 = most recent)
    job_title = Column(String(200), nullable=False)  # JobTitle
    occupation_code = Column(String(12))  # O*NET code mapped from the title (P3 title map)
    seeker = relationship("SeekerProfile", back_populates="history")


class Company(Base):  # demo extension: jobs.tsv has no employer column
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), unique=True, nullable=False)
    name = Column(String(160), nullable=False)
    state = Column(String(8))
    description = Column(Text)
    account = relationship("Account", back_populates="company")


class Job(Base):  # jobs.tsv (+ P2 cleaning, P3 attributes)
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)  # JobID (canonical after de-duplication); web jobs get ids above the dataset max
    window_id = Column(Integer, default=7, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text)  # Description, HTML removed (P2)
    requirements = Column(Text)  # Requirements, HTML removed (P2)
    city = Column(String(80))
    city_key = Column(String(120))
    state = Column(String(8), index=True)
    country = Column(String(8), default="US")
    zip5 = Column(String(10))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    lat = Column(Float)
    lon = Column(Float)
    # P3 attributes (None = not stated in the posting)
    occupation_code = Column(String(12), index=True)
    occ_group = Column(String(8), index=True)
    job_type = Column(String(16), index=True)
    seniority = Column(String(12))
    degree_req = Column(Integer)  # minimum degree ordinal
    years_req = Column(Float)
    salary_mentioned = Column(Boolean, default=False)
    status = Column(String(10), default="open", index=True)  # open | closed (demo extension)
    source = Column(String(10), default="dataset")  # dataset | web
    world_idx = Column(Integer, index=True)  # row in the encoder's job table (used by the recommender)
    created_at = Column(DateTime, default=datetime.utcnow)
    company = relationship("Company")
    skills = relationship("JobSkill", cascade="all, delete-orphan")


class JobSkill(Base):  # P3 skill extraction (job x skill)
    __tablename__ = "job_skills"
    job_id = Column(Integer, ForeignKey("jobs.id"), primary_key=True)
    skill_key = Column(String(12), ForeignKey("skills.key"), primary_key=True)


class Application(Base):  # apps.tsv
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    seeker_id = Column(Integer, ForeignKey("seeker_profiles.id"), index=True, nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), index=True, nullable=False)
    window_id = Column(Integer, default=7)
    application_date = Column(DateTime, default=datetime.utcnow)  # ApplicationDate
    status = Column(String(12), default="submitted")  # demo extension
    source = Column(String(12), default="dataset")  # dataset | web | assistant
    dataset_role = Column(String(8))  # A_cut5 role of dataset apps: history | target
    __table_args__ = (UniqueConstraint("seeker_id", "job_id"),)
    seeker = relationship("SeekerProfile")
    job = relationship("Job")


class Conversation(Base):  # log of assistant sessions (demo extension)
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    seeker_id = Column(Integer, ForeignKey("seeker_profiles.id"), index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    turns = Column(Integer, default=0)
    n_questions = Column(Integer, default=0)
    success = Column(Boolean, default=False)
    success_turn = Column(Integer)
    accepted_job_id = Column(Integer)
    transcript = Column(Text)  # JSON list of turns
    seeker = relationship("SeekerProfile")


# ---- taxonomies (O*NET 30.1 and the graph's attribute nodes) ----
class OccGroup(Base):
    __tablename__ = "occ_groups"
    key = Column(String(8), primary_key=True)
    name = Column(String(120), nullable=False)


class Occupation(Base):
    __tablename__ = "occupations"
    key = Column(String(12), primary_key=True)  # O*NET-SOC code
    name = Column(String(160), nullable=False)
    group_key = Column(String(8), ForeignKey("occ_groups.key"))


class Skill(Base):
    __tablename__ = "skills"
    key = Column(String(12), primary_key=True)
    name = Column(String(120), nullable=False)


class State(Base):
    __tablename__ = "states"
    key = Column(String(8), primary_key=True)


class City(Base):
    __tablename__ = "cities"
    key = Column(String(120), primary_key=True)  # city_key = "normalised city|STATE"
    name = Column(String(120), nullable=False)
    state = Column(String(8), index=True)
    lat = Column(Float)
    lon = Column(Float)


class TitleMap(Base):  # P3: cleaned job title -> O*NET occupation (exact match or JobBERT nearest label, score >= 0.6)
    __tablename__ = "title_map"
    title_key = Column(String(200), primary_key=True)
    code = Column(String(12), nullable=False)
    score = Column(Float)


Index("ix_jobs_status_state", Job.status, Job.state)
