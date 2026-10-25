from __future__ import annotations

import asyncio
from collections import defaultdict
from copy import deepcopy
from typing import Any, Protocol

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient


Document = dict[str, Any]


class Store(Protocol):
    async def initialize(self) -> None: ...
    async def insert(self, collection: str, document: Document) -> Document: ...
    async def get(self, collection: str, document_id: str) -> Document | None: ...
    async def find(self, collection: str, **filters: Any) -> list[Document]: ...
    async def replace(self, collection: str, document_id: str, document: Document) -> Document: ...
    async def upsert(self, collection: str, document: Document) -> Document: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


def _matches(document: Document, filters: dict[str, Any]) -> bool:
    return all(document.get(key) == value for key, value in filters.items())


class MemoryStore:
    """Test-only store with the same repository interface as MongoDB."""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Document]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        return None

    async def insert(self, collection: str, document: Document) -> Document:
        async with self._lock:
            if document["id"] in self._documents[collection]:
                raise ValueError(f"duplicate id in {collection}")
            self._documents[collection][document["id"]] = deepcopy(document)
        return deepcopy(document)

    async def get(self, collection: str, document_id: str) -> Document | None:
        document = self._documents[collection].get(document_id)
        return deepcopy(document) if document else None

    async def find(self, collection: str, **filters: Any) -> list[Document]:
        documents = [document for document in self._documents[collection].values() if _matches(document, filters)]
        return deepcopy(documents)

    async def replace(self, collection: str, document_id: str, document: Document) -> Document:
        async with self._lock:
            if document_id not in self._documents[collection]:
                raise KeyError(document_id)
            self._documents[collection][document_id] = deepcopy(document)
        return deepcopy(document)

    async def upsert(self, collection: str, document: Document) -> Document:
        async with self._lock:
            self._documents[collection][document["id"]] = deepcopy(document)
        return deepcopy(document)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class MongoStore:
    """MongoDB persistence using PyMongo's native asynchronous client."""

    def __init__(self, uri: str, database_name: str) -> None:
        self.client = AsyncMongoClient(uri, serverSelectionTimeoutMS=8000)
        self.database = self.client[database_name]

    async def initialize(self) -> None:
        await self.database.users.create_index([("email", ASCENDING)], unique=True)
        await self.database.memberships.create_index(
            [("organization_id", ASCENDING), ("user_id", ASCENDING)], unique=True
        )
        await self.database.invitations.create_index([("token_hash", ASCENDING)], unique=True)
        await self.database.purchase_orders.create_index(
            [("plan_id", ASCENDING), ("idempotency_key", ASCENDING), ("supplier_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"idempotency_key": {"$exists": True}},
        )
        await self.database.jobs.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
        await self.database.audit_events.create_index([("mission_id", ASCENDING), ("created_at", ASCENDING)])
        # A forked audit chain (two events claiming one sequence slot) must fail loudly.
        await self.database.audit_events.create_index(
            [("chain_key", ASCENDING), ("sequence", ASCENDING)],
            unique=True,
            partialFilterExpression={"chain_key": {"$exists": True}},
        )
        await self.database.evidence.create_index(
            [("organization_id", ASCENDING), ("subject_id", ASCENDING), ("retrieved_at", DESCENDING)]
        )
        await self.database.payments.create_index([("transaction", ASCENDING)], unique=True, sparse=True)
        await self.database.agent_tokens.create_index([("token_hash", ASCENDING)], unique=True)
        for collection in (
            "quotes", "plans", "approvals", "notifications", "supplier_leads",
            "supplier_reviews", "disruptions", "payments", "continuity_analyses",
        ):
            await self.database[collection].create_index([("mission_id", ASCENDING)])
        await self.database.continuity_analyses.create_index(
            [("mission_id", ASCENDING), ("plan_id", ASCENDING), ("input_hash", ASCENDING)]
        )
        for collection in ("organizations", "users", "missions", "quotes", "plans", "suppliers", "evidence"):
            await self.database[collection].create_index([("id", ASCENDING)], unique=True)
        # Operations integrations: ids are idempotency hashes, so a duplicate insert is the dedupe signal.
        for collection in ("ops_events", "ops_deliveries", "integration_connections", "oauth_states",
                           "calendar_slots", "drive_files", "drive_folders", "email_outbox"):
            await self.database[collection].create_index([("id", ASCENDING)], unique=True)
        await self.database.ops_deliveries.create_index([("organization_id", ASCENDING), ("created_at", DESCENDING)])
        await self.database.ops_deliveries.create_index([("mission_id", ASCENDING), ("channel", ASCENDING)])
        await self.database.ops_deliveries.create_index([("status", ASCENDING)])
        await self.database.email_dispatches.create_index([("organization_id", ASCENDING), ("provider", ASCENDING)])

    async def insert(self, collection: str, document: Document) -> Document:
        await self.database[collection].insert_one(deepcopy(document))
        return deepcopy(document)

    async def get(self, collection: str, document_id: str) -> Document | None:
        document = await self.database[collection].find_one({"id": document_id}, {"_id": 0})
        return document

    async def find(self, collection: str, **filters: Any) -> list[Document]:
        cursor = self.database[collection].find(filters, {"_id": 0})
        return [document async for document in cursor]

    async def replace(self, collection: str, document_id: str, document: Document) -> Document:
        result = await self.database[collection].replace_one({"id": document_id}, deepcopy(document))
        if not result.matched_count:
            raise KeyError(document_id)
        return deepcopy(document)

    async def upsert(self, collection: str, document: Document) -> Document:
        await self.database[collection].replace_one({"id": document["id"]}, deepcopy(document), upsert=True)
        return deepcopy(document)

    async def ping(self) -> bool:
        await self.client.admin.command("ping")
        return True

    async def close(self) -> None:
        await self.client.close()
