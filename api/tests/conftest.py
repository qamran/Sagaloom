import asyncio
import uuid

import chromadb
import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from sagaloom.store.canon import CanonStore


@pytest.fixture
def store():
    client = chromadb.EphemeralClient()
    return CanonStore(
        client,
        DeterministicFakeEmbedding(size=256),
        collection_name=f"entries_{uuid.uuid4().hex}",
    )


@pytest.fixture
def aclose_later():
    """Registers an `httpx.AsyncClient` that a sync fixture or helper opened; each is closed at
    teardown, so no test leaves a client unclosed. (The suite defines no async fixtures.)"""
    clients = []
    yield clients.append
    for c in clients:
        asyncio.run(c.aclose())
