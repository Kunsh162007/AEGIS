"""KnowledgeBase — retrieval over typologies + adverse media + reviewed precedent.

Default backend is a dependency-free keyword/overlap scorer so the system runs
offline. Set use_chroma=True (and install chromadb + sentence-transformers) for
real vector search — the interface is identical.
"""
from __future__ import annotations

import re

from .typologies import TYPOLOGIES

_WORD = re.compile(r"[a-z0-9]+")
# Generic terms that appear across many typologies and so carry no discriminating
# signal — ignored when scoring overlap (keeps "funds"/"account" from misleading).
_GENERIC = {"a", "an", "the", "to", "of", "and", "is", "on", "in", "or", "its",
            "own", "from", "with", "funds", "account", "accounts", "large",
            "credit", "transfer", "transfers", "money", "usually", "not",
            "suspicious", "pattern", "indicators", "consistent", "single"}


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if t not in _GENERIC}


class KnowledgeBase:
    def __init__(self, use_chroma: bool = False):
        self.docs: list[dict] = list(TYPOLOGIES)
        self.use_chroma = use_chroma
        self._collection = None
        if use_chroma:
            self._init_chroma()

    def _init_chroma(self) -> None:  # pragma: no cover (optional path)
        import chromadb
        client = chromadb.Client()
        self._collection = client.get_or_create_collection("aegis_kb")
        self._collection.add(documents=[d["text"] for d in self.docs],
                             ids=[d["id"] for d in self.docs])

    def add_precedent(self, doc_id: str, text: str) -> None:
        """Reviewed human decisions become retrievable precedent (§8 feedback loop)."""
        self.docs.append({"id": doc_id, "text": text})
        if self._collection is not None:  # pragma: no cover
            self._collection.add(documents=[text], ids=[doc_id])

    def retrieve(self, query: str, k: int = 3) -> list[dict]:
        if self._collection is not None:  # pragma: no cover
            res = self._collection.query(query_texts=[query], n_results=k)
            ids, docs = res["ids"][0], res["documents"][0]
            return [{"id": i, "text": t} for i, t in zip(ids, docs)]
        q = _tokens(query)
        scored = sorted(((len(q & _tokens(d["text"])), d) for d in self.docs),
                        key=lambda s: s[0], reverse=True)
        # Only return docs with real token overlap. Returning a zero-overlap
        # "best" doc would inject a phantom typology match into every case
        # (badly skews real-data scoring); an empty list is the honest answer.
        return [d for score, d in scored[:k] if score > 0]
