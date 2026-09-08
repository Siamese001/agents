"""Apps RG-owned SQLite adapter.

The app uses only the standard-library DB-API surface. Keeping that surface
local prevents storage helpers from importing an external runtime during
ordinary retrieval, cache, and graph operations.
"""

import sqlite3 as sqlite3_adapter

__all__ = ["sqlite3_adapter"]
