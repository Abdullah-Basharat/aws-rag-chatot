import os
import tempfile
from dotenv import load_dotenv
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .postgres_db import get_all_pdfs, get_pdfs_by_user, ingest
from .vector_store import insert_new_chunks
from . import s3_storage


load_dotenv(".env")

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)


def _load_documents(path: str):
    """
    Load documents from a local file path, supporting PDF, DOCX and TXT.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(path)
    elif ext in {".docx"}:
        loader = Docx2txtLoader(path)
    elif ext in {".txt"}:
        loader = TextLoader(path, encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file extension for ingestion: {ext}")
    return loader.load()


####################################
# Admin
####################################


def ingest_all_pdfs():
    """
    Admin: Ingest all public PDFs.
    Now uses S3 as the storage backend and downloads to temp files for processing.
    """
    all_pdfs = get_all_pdfs()
    public_pdfs = [p for p in all_pdfs if p["is_public"] == 1]
    if not public_pdfs:
        print("No public PDFs found.")
        return
    for pdf in public_pdfs:
        key = pdf["filepath"]
        try:
            tmp_path = s3_storage.download_to_temp(key)
            try:
                docs = _load_documents(tmp_path)
                chunks = splitter.split_documents(docs)
                for c in chunks:
                    c.metadata = {
                        "user_id": "public",
                        "filename": pdf["filename"],
                        "source": pdf["filename"],
                        "is_public": 1,
                    }
                insert_new_chunks(chunks)
                ingest(pdf["filename"], "public", 1)
                print(f"Ingested public PDF from S3: {pdf['filename']}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as e:
            print(f"Failed to ingest {pdf['filename']}: {e}")


def ingest_one_pdf_admin(filename: str, user_id: str = None):
    """Admin: Ingest one PDF for any user or for all (public). If user_id is None, treat as public."""
    all_pdfs = get_all_pdfs()
    pdf_info = None
    for pdf in all_pdfs:
        if pdf["filename"] == filename:
            pdf_info = pdf
            break
    if not pdf_info:
        print(f"PDF '{filename}' not found in database.")
        return
    # File is stored in S3 – filepath column holds the S3 key
    file_key = pdf_info["filepath"]
    try:
        tmp_path = s3_storage.download_to_temp(file_key)
        try:
            docs = _load_documents(tmp_path)
            chunks = splitter.split_documents(docs)
            if user_id:
                meta_user = user_id
                is_public = 0
            else:
                meta_user = "public"
                is_public = 1
            for c in chunks:
                c.metadata = {
                    "user_id": meta_user,
                    "filename": pdf_info["filename"],
                    "source": pdf_info["filename"],
                    "is_public": is_public,
                }
            insert_new_chunks(chunks)
            ingest(pdf_info["filename"], meta_user, is_public)
            print(f"Admin ingested PDF: {filename} for user: {meta_user}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        print(f"Failed to ingest {filename}: {e}")


def ingest_one_pdf_public(filename: str):
    """Admin: Ingest one PDF as public (user_id='public', is_public=1)."""
    all_pdfs = get_all_pdfs()
    pdf_info = None
    for pdf in all_pdfs:
        if pdf["filename"] == filename:
            pdf_info = pdf
            break
    if not pdf_info:
        print(f"PDF '{filename}' not found in database.")
        return
    file_key = pdf_info["filepath"]
    try:
        tmp_path = s3_storage.download_to_temp(file_key)
        try:
            docs = _load_documents(tmp_path)
            chunks = splitter.split_documents(docs)
            for c in chunks:
                c.metadata = {
                    "user_id": "public",
                    "filename": pdf_info["filename"],
                    "source": pdf_info["filename"],
                    "is_public": 1,
                }
            insert_new_chunks(chunks)
            ingest(pdf_info["filename"], "public", 1)
            print(f"Admin ingested PDF: {filename} as public from S3.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        print(f"Failed to ingest {filename}: {e}")


def ingest_one_pdf_private(filename: str, user_id: str):
    """Admin: Ingest one PDF for a specific user (user_id, is_public=0)."""
    all_pdfs = get_all_pdfs()
    pdf_info = None
    print("TEST", all_pdfs)
    for pdf in all_pdfs:
        if pdf["filename"] == filename:
            pdf_info = pdf
            break
    if not pdf_info:
        print(f"PDF '{filename}' not found in database.")
        return
    # File is stored in S3 – filepath column holds the S3 key
    file_key = pdf_info["filepath"]
    try:
        tmp_path = s3_storage.download_to_temp(file_key)
        try:
            docs = _load_documents(tmp_path)
            chunks = splitter.split_documents(docs)
            for c in chunks:
                c.metadata = {
                    "user_id": user_id,
                    "filename": pdf_info["filename"],
                    "source": pdf_info["filename"],
                    "is_public": 0,
                }
            insert_new_chunks(chunks)
            ingest(pdf_info["filename"], user_id, 0)
            print(f"Admin ingested PDF: {filename} for user: {user_id} from S3.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        print(f"Failed to ingest {filename}: {e}")


####################################
# User
####################################


def ingest_my_all_pdfs(user_id: str = None, is_public: bool = False):
    """User: Ingest all PDFs uploaded by this user. Only for me."""
    if not user_id:
        print("user_id required")
        return
    pdfs = get_pdfs_by_user(user_id)
    if not pdfs:
        print(f"No PDFs found for user {user_id}")
        return
    for pdf in pdfs:
        if is_public and not pdf["is_public"]:
            continue
        file_key = pdf["filepath"]
        try:
            tmp_path = s3_storage.download_to_temp(file_key)
            try:
                loader = PyPDFLoader(tmp_path)
                docs = loader.load()
                chunks = splitter.split_documents(docs)
                for c in chunks:
                    c.metadata = {
                        "user_id": user_id,
                        "filename": pdf["filename"],
                        "source": pdf["filename"],
                        "is_public": pdf["is_public"],
                    }
                insert_new_chunks(chunks)
                ingest(pdf["filename"], user_id, pdf["is_public"])
                print(f"User {user_id} ingested PDF from S3: {pdf['filename']}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as e:
            print(f"Failed to ingest {pdf['filename']}: {e}")


def ingest_one_pdf_user(filename: str, user_id: str = None):
    """User: Ingest one PDF, but can only ingest PDFs which user uploaded."""
    if not user_id:
        print("user_id required")
        return
    user_pdfs = get_pdfs_by_user(user_id)
    pdf_info = None
    for pdf in user_pdfs:
        if pdf["filename"] == filename:
            pdf_info = pdf
            break
    if not pdf_info:
        print(f"PDF '{filename}' not found or not permitted for user {user_id}.")
        return
    file_key = pdf_info["filepath"]
    try:
        tmp_path = s3_storage.download_to_temp(file_key)
        try:
            loader = PyPDFLoader(tmp_path)
            docs = loader.load()
            chunks = splitter.split_documents(docs)
            for c in chunks:
                c.metadata = {
                    "user_id": user_id,
                    "filename": pdf_info["filename"],
                    "source": pdf_info["filename"],
                    "is_public": pdf_info["is_public"],
                }
            insert_new_chunks(chunks)
            ingest(pdf_info["filename"], user_id, pdf_info["is_public"])
            print(f"User {user_id} ingested PDF from S3: {filename}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        print(f"Failed to ingest {filename}: {e}")


if __name__ == "__main__":
    print("Ingest all public PDFs (admin)")
    ingest_all_pdfs()


