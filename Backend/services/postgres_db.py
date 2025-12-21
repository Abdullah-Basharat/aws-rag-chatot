import os
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor


load_dotenv()


def get_db_connection():
    """
    Return a new PostgreSQL connection using environment configuration.

    Expected environment variables (all loaded from .env if present):
    - POSTGRES_DB
    - POSTGRES_USER
    - POSTGRES_PASSWORD
    - POSTGRES_HOST (default: localhost)
    - POSTGRES_PORT (default: 5432)
    """
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


def init_db() -> None:
    """Initialise core relational tables if they don't already exist."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Users table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    userid TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                );
                """
            )

            # PDFs uploaded (metadata only)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pdfs (
                    id SERIAL PRIMARY KEY,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    uploaded_by TEXT NOT NULL,
                    is_public INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Ingest state for PDFs → vector store
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_state (
                    id SERIAL PRIMARY KEY,
                    filename TEXT NOT NULL,
                    ingested_by TEXT NOT NULL,
                    is_public INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

        conn.commit()


######################################
# users
######################################


def add_user(userid: str, password: str, is_admin: int = 0) -> bool:
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (userid, password) VALUES (%s, %s);",
                (userid, password),
            )
        return True
    except psycopg2.IntegrityError:
        return False


def delete_user(userid: str) -> bool:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE userid = %s;", (userid,))
        deleted = cur.rowcount > 0
    return deleted


def authenticate_user(userid: str, password: str) -> bool:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM users WHERE userid = %s AND password = %s;",
            (userid, password),
        )
        return cur.fetchone() is not None


def update_user_password(userid: str, new_password: str) -> bool:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password = %s WHERE userid = %s;",
            (new_password, userid),
        )
        updated = cur.rowcount > 0
    return updated


def get_all_users() -> List[Dict[str, Any]]:
    with get_db_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, userid, password FROM users;")
        rows = cur.fetchall()
        # Cast to plain dict list for compatibility with old sqlite API
        return [dict(row) for row in rows]


######################################
# pdfs
######################################


def add_pdf(
    filename: str,
    uploaded_by: str,
    is_global: int = 0,
    filepath: Optional[str] = None,
) -> int:
    if filepath is None:
        filepath = filename
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pdfs (filename, filepath, uploaded_by, is_public)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (filename, filepath, uploaded_by, is_global),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id


def get_pdfs_by_user(uploaded_by: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, filename, filepath, uploaded_by, is_public, created_at
            FROM pdfs
            WHERE uploaded_by = %s;
            """,
            (uploaded_by,),
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def get_all_pdfs() -> List[Dict[str, Any]]:
    with get_db_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, filename, filepath, uploaded_by, is_public, created_at
            FROM pdfs;
            """
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def delete_pdf_by_filename(filename: str) -> bool:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM pdfs WHERE filename = %s;", (filename,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def delete_pdf_by_id(id: str) -> bool:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM pdfs WHERE id = %s;", (id,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def get_pdf_filepath_by_filename(filename: str) -> Optional[str]:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT filepath FROM pdfs WHERE filename = %s;", (filename,))
        row = cur.fetchone()
        return row[0] if row else None


######################################
# ingest_state
######################################


def ingest(pdf_filename: str, ingested_by: str, is_public: int) -> int:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_state (filename, ingested_by, is_public)
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (pdf_filename, ingested_by, is_public),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id


def get_ingested_pdfs_by_user(ingested_by: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, filename, ingested_by, is_public, created_at
            FROM ingest_state
            WHERE ingested_by = %s;
            """,
            (ingested_by,),
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def get_all_ingested_pdfs() -> List[Dict[str, Any]]:
    with get_db_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, filename, ingested_by, is_public, created_at
            FROM ingest_state;
            """
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def delete_ingested_pdf_by_filename(pdf_filename: str) -> bool:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ingest_state WHERE filename = %s;", (pdf_filename,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def delete_ingested_pdf_by_id(id: str) -> bool:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ingest_state WHERE id = %s;", (id,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


# Initialise tables on import
init_db()


