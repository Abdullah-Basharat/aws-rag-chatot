import os
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_community.vectorstores.pgvector import PGVector

from . import postgres_db


load_dotenv()

embedding = OpenAIEmbeddings()

CHAT_HISTORY_LIMIT = 10


def _pg_connection_string() -> str:
    """
    Build a PostgreSQL connection string for pgvector / PGVector.
    """
    return PGVector.connection_string_from_db_params(
        driver="psycopg2",
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


######################################
# User message history embedding
######################################


def _user_history_store(user_id: str) -> PGVector:
    """
    PGVector store for a single user's chat history.
    We keep per-user collections.
    """
    return PGVector(
        collection_name=f"user_{user_id}",
        embedding_function=embedding,
        connection_string=_pg_connection_string(),
        create_extension=True,
    )


def save_user_message(user_id: str, message: str) -> None:
    """
    Save a user message to:
    - pgvector for similarity-based memory retrieval
    - relational history table for ordered history listing
    """
    # Persist ordered history in relational DB
    with postgres_db.get_db_connection() as conn, conn.cursor() as cur:
        # Ensure table and role column exist
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                message TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            ALTER TABLE chat_history
            ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
            """
        )
        cur.execute(
            "INSERT INTO chat_history (user_id, role, message) VALUES (%s, %s, %s);",
            (user_id, "user", message),
        )
        # Enforce history limit per user
        cur.execute(
            """
            DELETE FROM chat_history
            WHERE id IN (
                SELECT id FROM chat_history
                WHERE user_id = %s
                ORDER BY created_at DESC
                OFFSET %s
            );
            """,
            (user_id, CHAT_HISTORY_LIMIT),
        )
        conn.commit()

    # Store in pgvector for semantic memory retrieval
    db = _user_history_store(user_id)
    doc = Document(page_content=message, metadata={"user_id": user_id})
    db.add_documents([doc])


def save_assistant_message(user_id: str, message: str) -> None:
    """
    Save an assistant (AI) message to the ordered history table.

    We do not currently embed assistant messages into pgvector; only user
    messages are used for semantic memory, which is usually sufficient.
    """
    with postgres_db.get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                message TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            ALTER TABLE chat_history
            ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
            """
        )
        cur.execute(
            "INSERT INTO chat_history (user_id, role, message) VALUES (%s, %s, %s);",
            (user_id, "assistant", message),
        )
        conn.commit()


def retrieve_user_memory(user_id: str, query: str, k: int = 3) -> List[Document]:
    """
    Retrieve previous conversation turns for RAG from the relational history only.
    """
    with postgres_db.get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT role, message
            FROM chat_history
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s;
            """,
            (user_id, 3),
        )
        rows = cur.fetchall()

    docs: List[Document] = []
    # We build documents in chronological order (oldest → newest)
    for role, message in reversed(rows):
        content = f"{role or 'user'}: {message}"
        docs.append(
            Document(
                page_content=content,
                metadata={"user_id": user_id, "source": "chat_history", "role": role},
            )
        )
    return docs[:k]


def get_all_history(user_id: str) -> List[Dict[str, Any]]:
    """
    Return ordered history for a user (oldest → newest) including role info.

    Each entry has the shape:
    { "role": "user" | "assistant", "message": "...", "created_at": "<iso8601>" }
    """
    with postgres_db.get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT role, message, created_at
            FROM chat_history
            WHERE user_id = %s
            ORDER BY created_at ASC;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        history: List[Dict[str, Any]] = []
        for role, message, created_at in rows:
            history.append(
                {
                    "role": role or "user",
                    "message": message,
                    "created_at": created_at.isoformat() if created_at else None,
                }
            )
        return history


def clear_history_by_user(user_id: str) -> None:
    with postgres_db.get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chat_history WHERE user_id = %s;", (user_id,))
        conn.commit()

    db = _user_history_store(user_id)
    # Delete all vectors for this user's history collection
    db.delete()


def clear_history_all() -> None:
    with postgres_db.get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS chat_history;")
        conn.commit()

    # Drop all user_* collections by clearing the underlying collections table.
    # This is a coarse reset of all user memory embeddings.
    conn_str = _pg_connection_string()
    PGVector._drop_tables(conn_str)  # type: ignore[attr-defined]


######################################
# PDF embedding
######################################


def _pdf_store() -> PGVector:
    """
    Single shared PGVector collection for all PDF chunks.
    Each chunk is distinguished by its metadata (user_id, filename, source, is_public).
    """
    return PGVector(
        collection_name="pdf_chunks",
        embedding_function=embedding,
        connection_string=_pg_connection_string(),
        create_extension=True,
    )


def insert_new_chunks(chunks: List[Document]) -> bool:
    """
    Insert a batch of PDF chunks into the shared pdf_chunks collection.
    """
    db = _pdf_store()
    db.add_documents(chunks)
    return True


def get_available_user_ids() -> List[str]:
    """
    For compatibility with the previous Chroma version, this returns all user_ids
    seen in the ingest_state table.
    """
    ingested = postgres_db.get_all_ingested_pdfs()
    return sorted({row["ingested_by"] for row in ingested})


def get_pdf_sources() -> List[Dict[str, Any]]:
    """
    Return a list of {source, ingested_by} pairs using the ingest_state table
    as the source of truth, mirroring the prior behaviour based on Chroma metadata.
    """
    ingested = postgres_db.get_all_ingested_pdfs()
    sources = []
    seen = set()
    for row in ingested:
        key = (row["filename"], row["ingested_by"])
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {"source": row["filename"], "ingested_by": row["ingested_by"]}
        )
    return sources


def retrieve_pdf_for_user(user_id: str, query: str, k: int = 3) -> List[Document]:
    """
    Retrieve PDF chunks for a given user, including public PDFs.
    This approximates the original behaviour (own PDFs + public PDFs).
    """
    db = _pdf_store()

    # Search own PDFs
    own_results = db.similarity_search(
        query,
        k=k,
        filter={"user_id": user_id},
    )

    # Search public PDFs
    public_results = db.similarity_search(
        query,
        k=k,
        filter={"is_public": 1},
    )

    combined: List[Document] = []
    seen_ids = set()
    for doc in own_results + public_results:
        doc_id = doc.metadata.get("id") or id(doc)
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        combined.append(doc)

    return combined[:k]


def clear_pdf_by_source(source_name: str, user_id: Optional[str] = None) -> None:
    """
    Delete all vector chunks for a given PDF source.
    If user_id is provided, only delete chunks for that specific user.
    """
    db = _pdf_store()
    filt: Dict[str, Any] = {"filename": source_name}
    if user_id is not None:
        filt["user_id"] = user_id
    db.delete(filter=filt)  # type: ignore[arg-type]


def clear_pdf_by_user(user_id: str) -> None:
    """
    Delete all vector chunks for all PDFs ingested by the specified user.
    """
    db = _pdf_store()
    db.delete(filter={"user_id": user_id})  # type: ignore[arg-type]


def clear_all_pdf() -> None:
    """
    Clear all PDF vectors (drops the underlying pdf_chunks collection).
    """
    db = _pdf_store()
    db.delete()


