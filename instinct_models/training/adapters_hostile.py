"""Compatibility alias: the hardened reader IS adapters.JsonlConfirmationLog since integration.

Kept so the prepared tests and the contract's import path keep working.
"""
from .adapters import JsonlConfirmationLog as HardenedJsonlConfirmationLog

__all__ = ["HardenedJsonlConfirmationLog"]
