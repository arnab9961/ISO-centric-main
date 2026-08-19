import os
from typing import Optional

import chromadb
from chromadb.config import Settings


class VectorDBClient:
    """Singleton ChromaDB client manager."""

    _client: Optional[chromadb.ClientAPI] = None
    _collection: Optional[chromadb.Collection] = None
    _persist_directory: str = "./chroma_db"

    @classmethod
    def get_client(cls) -> chromadb.ClientAPI:
        if cls._client is None:
            cls._client = chromadb.PersistentClient(
                path=cls._persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )
        return cls._client

    @classmethod
    def get_collection(cls, name: str = "iso_documents") -> chromadb.Collection:
        if cls._collection is None:
            client = cls.get_client()
            cls._collection = client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return cls._collection

    @classmethod
    def reset_collection(cls, name: str = "iso_documents") -> None:
        """Delete and recreate the collection."""
        client = cls.get_client()
        try:
            client.delete_collection(name=name)
        except Exception:
            pass
        cls._collection = None
        cls.get_collection(name)

    @classmethod
    def close(cls) -> None:
        cls._client = None
        cls._collection = None
