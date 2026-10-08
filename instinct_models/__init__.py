"""instinct_models - the shared model layer for Atlas, Meemee and Sugarcode.

Components: Inkling (local GGUF / self-hosted, or Hugging Face router), Ornith
(local GGUF through llama.cpp/Ollama's OpenAI-compatible API), Needle (on-device
tool-calling model, LoRA fine-tuned per product) and The AI Library
(read-only catalog connector). Free-first: the default routes are free or local. The optional Jev
evaluation client is paid and key-gated, and is off by default; the HF router
is metered past its free tier and is opt-in.
Training pipelines are shared; datasets stay per product.
"""
from .catalog import AILibraryCatalog, CatalogItem, CatalogSource
from .config import ProductConfig, load_config
from .providers import (ChatResult, InklingHFRouter, InklingLocal, HermesLocal, OpenClawOwner, JevEval, JevStatusError, NeedleLocal,
                        OrnithOpenAICompat, Provider, ProviderError, ProviderUnavailable, validate_questions)
from .lexical import LexicalLocal, LexicalToolModel
from .router import Router, Task

__all__ = ["AILibraryCatalog", "CatalogItem", "CatalogSource", "ProductConfig", "load_config", "Provider", "ProviderError", "ProviderUnavailable", "ChatResult",
           "InklingLocal", "InklingHFRouter", "HermesLocal", "OpenClawOwner", "OrnithOpenAICompat", "NeedleLocal", "JevEval", "JevStatusError",
           "validate_questions", "Router", "Task", "LexicalLocal", "LexicalToolModel"]
__version__ = "0.1.0"
