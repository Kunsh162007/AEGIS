"""Unified model-client layer: one interface over AI/ML API, Featherless,
Ollama, and a deterministic offline mock — selectable per agent tier."""
from .client import ModelClient

__all__ = ["ModelClient"]
