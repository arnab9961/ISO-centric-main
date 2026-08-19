import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.vector_db import VectorDBClient


def chunk_document(
    text: str,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> List[str]:
    """Split text into overlapping chunks for better retrieval."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


async def ingest_document(
    filename: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Chunk, embed, and store a document in ChromaDB."""
    if not text or not text.strip():
        return {
            "success": False,
            "error": "Empty document text",
            "chunks_created": 0,
        }

    chunks = chunk_document(text)
    if not chunks:
        return {
            "success": False,
            "error": "Failed to chunk document",
            "chunks_created": 0,
        }

    document_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()

    collection = VectorDBClient.get_collection()

    chunk_metadata = []
    chunk_ids = []
    for idx, chunk in enumerate(chunks):
        chunk_id = f"{document_id}_chunk_{idx}"
        chunk_ids.append(chunk_id)
        chunk_meta = {
            "filename": filename,
            "document_id": document_id,
            "chunk_index": idx,
            "total_chunks": len(chunks),
            "timestamp": timestamp,
        }
        if metadata:
            chunk_meta.update(metadata)
        chunk_metadata.append(chunk_meta)

    collection.add(
        ids=chunk_ids,
        documents=chunks,
        metadatas=chunk_metadata,
    )

    return {
        "success": True,
        "document_id": document_id,
        "chunks_created": len(chunks),
        "filename": filename,
    }


async def search_similar(
    query: str,
    top_k: int = 3,
    min_similarity: float = 0.3,
) -> List[Dict[str, Any]]:
    """Retrieve most similar chunks from ChromaDB."""
    if not query or not query.strip():
        return []

    collection = VectorDBClient.get_collection()

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    retrieved = []
    for idx, doc in enumerate(results["documents"][0]):
        metadata = results["metadatas"][0][idx] if results["metadatas"] else {}
        distance = results["distances"][0][idx] if results["distances"] else 1.0
        similarity = 1.0 - distance

        if similarity >= min_similarity:
            retrieved.append({
                "text": doc,
                "metadata": metadata,
                "similarity_score": round(similarity, 3),
            })

    return retrieved
