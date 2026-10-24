from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core import Services
from .emailing import EmailGateway
from .integrations.connections import TokenVault
from .integrations.http import IntegrationHub
from .jobs import recover_jobs
from .operations.notifications import OperationsService
from .payments import x402_exchange
from .routes import agent, demo, evidence, integrations, intel, market, payments, procurement, status
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
    hub = IntegrationHub(store, runtime_settings.http_user_agent, transport=http_transport)
    vault = TokenVault(runtime_settings)
    email = EmailGateway(runtime_settings, store, vault, hub.client)
    services = Services(runtime_settings, store, email, hub)
    services.vault = vault
    services.ops = OperationsService(services)
    register_handlers(services)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await services.store.initialize()
        await recover_jobs(services)
        await services.ops.recover()
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
        allow_origin_regex=runtime_settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-PAYMENT", "PAYMENT-SIGNATURE"],
        expose_headers=["X-PAYMENT-RESPONSE", "PAYMENT-RESPONSE", "PAYMENT-REQUIRED"],
    )

    if runtime_settings.x402_pay_to:
        x402_gate = x402_exchange.build_payment_middleware(services)

        @app.middleware("http")
        async def x402_payment_gate(request, call_next):  # official Coinbase x402 middleware
            return await x402_gate(request, call_next)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "storage": runtime_settings.storage_mode}

    for module in (procurement, intel, evidence, market, demo, agent, payments, x402_exchange, integrations, status):
        app.include_router(module.router)
    return app


app = create_app()
