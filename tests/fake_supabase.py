"""Backwards-compatible test import for the local service.

The implementation now lives in ``app/services/local_service.py`` so the same
in-memory service can power both the test-suite and the offline local mode.
"""

from app.services.local_service import LocalSupabaseService as FakeSupabaseService

__all__ = ["FakeSupabaseService"]
