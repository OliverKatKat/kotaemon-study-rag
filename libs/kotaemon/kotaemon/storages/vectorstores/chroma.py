import logging
from heapq import nsmallest
from itertools import count
from math import exp
from typing import Any, Dict, List, Optional, Type, cast

import numpy as np
from llama_index.vector_stores.chroma import ChromaVectorStore as LIChromaVectorStore
from llama_index.vector_stores.chroma.base import _to_chroma_filter

from .base import LlamaIndexVectorStore

logger = logging.getLogger(__name__)


class ChromaVectorStore(LlamaIndexVectorStore):
    _li_class: Type[LIChromaVectorStore] = LIChromaVectorStore

    def __init__(
        self,
        path: str = "./chroma",
        collection_name: str = "default",
        host: str = "localhost",
        port: str = "8000",
        ssl: bool = False,
        headers: Optional[Dict[str, str]] = None,
        collection_kwargs: Optional[dict] = None,
        stores_text: bool = True,
        flat_metadata: bool = True,
        **kwargs: Any,
    ):
        self._path = path
        self._collection_name = collection_name
        self._host = host
        self._port = port
        self._ssl = ssl
        self._headers = headers
        self._collection_kwargs = collection_kwargs
        self._stores_text = stores_text
        self._flat_metadata = flat_metadata
        self._kwargs = kwargs

        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "ChromaVectorStore requires chromadb. "
                "Please install chromadb first `pip install chromadb`"
            )

        client = chromadb.PersistentClient(path=path)
        collection = client.get_or_create_collection(collection_name)

        # pass through for nice IDE support
        super().__init__(
            chroma_collection=collection,
            host=host,
            port=port,
            ssl=ssl,
            headers=headers or {},
            collection_kwargs=collection_kwargs or {},
            stores_text=stores_text,
            flat_metadata=flat_metadata,
            **kwargs,
        )
        self._client = cast(LIChromaVectorStore, self._client)

    def delete(self, ids: List[str], **kwargs):
        """Delete vector embeddings from vector stores

        Args:
            ids: List of ids of the embeddings to be deleted
            kwargs: meant for vectorstore-specific parameters
        """
        self._client.client.delete(ids=ids)

    def drop(self):
        """Delete entire collection from vector stores"""
        self._client.client._client.delete_collection(self._client.client.name)

    def count(self) -> int:
        return self._collection.count()

    def query(
        self,
        embedding: list[float],
        top_k: int = 1,
        ids: Optional[list[str]] = None,
        **kwargs,
    ) -> tuple[list[list[float]], list[float], list[str]]:
        try:
            return super().query(embedding, top_k, ids, **kwargs)
        except RuntimeError as error:
            if "Cannot return the results in a contig" not in str(error):
                raise

        logger.warning("Chroma HNSW search failed. Scanning matching vectors exactly.")
        filters = kwargs.get("filters")
        where = (
            _to_chroma_filter(filters) if filters is not None else kwargs.get("where")
        )
        collection = self._collection
        space = collection.configuration_json["hnsw_configuration"]["space"]
        query = np.asarray(embedding, dtype=np.float32)
        best = []
        page_size = 512
        for offset in count(step=page_size):
            page = collection.get(
                ids=ids,
                where=where,
                where_document=kwargs.get("where_document"),
                include=["embeddings"],
                limit=page_size,
                offset=offset,
            )
            if not page["ids"]:
                break
            vectors = np.asarray(page["embeddings"], dtype=np.float32)
            if space == "cosine":
                norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
                similarities = np.divide(
                    vectors @ query, norms, out=np.zeros(len(vectors)), where=norms > 0
                )
                distances = 1 - similarities
            elif space == "ip":
                distances = 1 - vectors @ query
            else:
                distances = np.sum(np.square(vectors - query), axis=1)
            best = nsmallest(
                top_k,
                [*best, *zip(distances, page["ids"], vectors)],
                key=lambda match: match[0],
            )
            if len(page["ids"]) < page_size:
                break

        return (
            [vector.tolist() for _, _, vector in best],
            [exp(-distance) for distance, _, _ in best],
            [doc_id for _, doc_id, _ in best],
        )

    def __persist_flow__(self):
        return {
            "path": self._path,
            "collection_name": self._collection_name,
            "host": self._host,
            "port": self._port,
            "ssl": self._ssl,
            "headers": self._headers,
            "collection_kwargs": self._collection_kwargs,
            "stores_text": self._stores_text,
            "flat_metadata": self._flat_metadata,
            **self._kwargs,
        }
