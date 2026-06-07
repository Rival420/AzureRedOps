import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from .config import get_settings
from .database import Base, engine, SessionLocal
from .security import hash_password
from . import models
from .routers import auth, assessments, tokens, operations, jobs, reference

settings = get_settings()

app = FastAPI(title="AzureRedOps Console", version="1.0.0",
              description="Self-hosted GUI for the AzureRedOps red-team toolkit. "
                          "For authorized, educational security testing only.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def init_db(retries: int = 10, delay: float = 2.0):
    last_exc = None
    for _ in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError as exc:  # database not ready yet
            last_exc = exc
            time.sleep(delay)
    raise last_exc


def bootstrap_admin():
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(
            models.User.username == settings.admin_username).first()
        if not existing:
            db.add(models.User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password),
                is_admin=True,
            ))
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    init_db()
    bootstrap_admin()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "azureredops-console"}


app.include_router(auth.router)
app.include_router(assessments.router)
app.include_router(tokens.router)
app.include_router(operations.router)
app.include_router(jobs.router)
app.include_router(reference.router)
