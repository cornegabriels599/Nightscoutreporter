import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import engine
from app.models import Base
from app.routers import auth, basal, cockpit, data, me


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nightscout-cockpit")


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Nightscout Cockpit", version="2.0.0")

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(data.router)
app.include_router(basal.router)
app.include_router(cockpit.router)