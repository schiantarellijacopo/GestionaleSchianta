"""Risoluzione chiavi AI con priorità al vault super-admin.

La chiave inserita nel pannello Chiavi API (sincronizzata su GEMINI_API_KEY /
OPENAI_API_KEY) ha SEMPRE priorità; la chiave gestita Emergent
(EMERGENT_LLM_KEY) resta solo come fallback quando il pannello è vuoto.
"""
from __future__ import annotations
import os


def openai_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")


def gemini_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
