from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core import Services
from .emailing import EmailGateway, ResendEmailGateway, TestEmailGateway
from .integrations.http import IntegrationHub
from .jobs import recover_jobs
from .routes import agent, demo, evidence, intel, market, procurement, status
from .settings import Settings, get_settings
from .store import MemoryStore, MongoStore, Store
from .workflows import register_handlers


def create_app(settings: Settings | None = None, http_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    if runtime_settings.storage_mode == "memory":
        store: Store = MemoryStore()
    else:
        if not runtime_settings.mongodb_uri:
            raise RuntimeError("RELIEFMESH_MONGODB_URI is required when storage mode is mongo")
        store = MongoStore(runtime_settings.mongodb_uri, runtime_settings.mongodb_database)
    email: EmailGateway = TestEmailGateway() if runtime_settings.app_env == "test" else ResendEmailGateway(runtime_settings)
    hub = IntegrationHub(store, runtime_settings.http_user_agent, transport=http_transport)
    services = Services(runtime_settings, store, email, hub)
    register_handlers(services)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await services.store.initialize()
        await recover_jobs(services)
        yield
        if services.jobs:
            await asyncio.gather(*services.jobs, return_exceptions=True)
        await services.store.close()

    app = FastAPI(
        title="ReliefMesh Procurement API",
        version="0.2.0",
        description=(
            "Evidence-backed emergency procurement: real supplier quotes, deterministic policy, integer "
            "optimization, autonomous replanning, and human financial approval."
        ),
        lifespan=lifespan,
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-PAYMENT", "PAYMENT-SIGNATURE"],
        expose_headers=["X-PAYMENT-RESPONSE", "PAYMENT-RESPONSE", "PAYMENT-REQUIRED"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "storage": runtime_settings.storage_mode}

    for module in (procurement, intel, evidence, market, demo, agent, status):
        app.include_router(module.router)
    return app


app = create_app()
