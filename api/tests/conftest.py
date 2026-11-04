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
