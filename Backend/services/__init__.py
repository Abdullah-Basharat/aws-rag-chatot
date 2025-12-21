"""
Service layer for database, vector store, and related utilities.

This package is responsible for:
- Relational data (users, PDFs, ingest state) via PostgreSQL
- Vector data (chat history, PDF chunks) via pgvector
- PDF ingestion and indexing
- Basic logging and LLM access helpers

All FastAPI routes in `admin_dashboard.py` and `user_dashboard.py`
should depend on this package instead of talking directly to a specific
database or vector-store implementation.
"""


