import os
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Body,
    Form,
)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import asyncio

import Backend.services.postgres_db as db
import Backend.services.ingest as ingest
import Backend.services.vector_store as vectordb
from Backend.services.llm import LLM as chatmodel
from Backend.services.logger import log_event
from Backend.services import s3_storage


router = APIRouter()

security = HTTPBasic()


######################################
# User authentication
######################################


def verify_user_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if not db.authenticate_user(credentials.username, credentials.password):
        log_event(credentials.username, "user_auth_check", "failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    log_event(credentials.username, "user_auth_check", "success")
    return credentials


@router.get("/user/auth/check")
def user_auth_check(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    return {"success": True, "detail": "User authentication successful."}


######################################
# User registration & login
######################################


class UserRegister(BaseModel):
    username: str
    password: str
    registration_code: str


class UserLogin(BaseModel):
    username: str
    password: str


@router.post("/user/register")
def user_register(user: UserRegister):
    """
    Self-service user registration using a pre-shared registration code.

    Example: admin shares a one-time code like 'abc123' with a new user.
    The user calls this endpoint with that code and their desired password.
    """
    expected_code = os.getenv("REGISTRATION_CODE", "")
    if not expected_code:
        # Registration disabled until a code is configured
        raise HTTPException(
            status_code=503,
            detail="User self-registration is disabled. Please contact an administrator.",
        )
    if user.registration_code != expected_code:
        log_event(user.username, "user_register", "invalid_registration_code")
        raise HTTPException(status_code=400, detail="Invalid registration code.")

    created = db.add_user(user.username, user.password)
    if not created:
        log_event(user.username, "user_register", "user_already_exists")
        raise HTTPException(status_code=400, detail="User already exists.")

    log_event(user.username, "user_register", "success")
    return {"success": True, "user_id": user.username}


@router.post("/user/login")
def user_login(user: UserLogin):
    if db.authenticate_user(user.username, user.password):
        log_event(user.username, "user_login", "success")
        return {"success": True, "user_id": user.username}
    else:
        log_event(user.username, "user_login", "failed")
        raise HTTPException(status_code=401, detail="Invalid username or password.")


######################################
# User PDF management
######################################


PERSIST_DIR = os.getenv("PERSIST_DIR", "")
DATA_DIR = os.path.join(PERSIST_DIR, "data")


@router.post("/user/pdf/upload")
def upload_pdf(
    files: List[UploadFile] = File(...),
    credentials: HTTPBasicCredentials = Depends(verify_user_credentials),
    is_public: int = Form(0),
):
    """
    Upload documents to S3 instead of local disk.

    Supported types: PDF, DOCX, TXT.
    The database stores the S3 key in the `filepath` column.
    """
    allowed_ext = {".pdf", ".docx", ".txt"}
    uploaded = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_ext:
            continue
        if is_public:
            s3_key = os.path.join("public", file.filename)
        else:
            s3_key = os.path.join(credentials.username, file.filename)
        # Push file content directly to S3
        s3_storage.upload_fileobj(file.file, s3_key)
        # Store S3 key in DB
        db.add_pdf(file.filename, credentials.username, is_public, s3_key)
        uploaded.append(file.filename)
        log_event(
            credentials.username,
            "upload_pdf",
            f"filename={file.filename}, is_public={is_public}",
        )
    if not uploaded:
        raise HTTPException(
            status_code=400,
            detail="No valid documents uploaded. Allowed types: PDF, DOCX, TXT.",
        )
    return {"uploaded": uploaded}


@router.get("/user/pdf")
def list_pdfs(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    pdfs = db.get_pdfs_by_user(credentials.username)
    log_event(credentials.username, "list_pdfs", f"count={len(pdfs)}")
    return {"pdfs": pdfs}


@router.post("/user/pdf/delete")
def delete_pdf(
    data: dict = Body(...),
    credentials: HTTPBasicCredentials = Depends(verify_user_credentials),
):
    filenames = data.get("filenames")
    if not filenames or not isinstance(filenames, list):
        raise HTTPException(status_code=400, detail="Missing or invalid 'filenames' (must be a list).")
    deleted = []
    errors = []
    for filename in filenames:
        pdfs = db.get_pdfs_by_user(credentials.username)
        pdf_info = next((pdf for pdf in pdfs if pdf["filename"] == filename), None)
        if not pdf_info:
            errors.append({"filename": filename, "error": "Not found in database"})
            continue
        # S3 key is stored in filepath
        s3_key = pdf_info["filepath"]
        try:
            s3_storage.delete_object(s3_key)
        except Exception as e:
            errors.append({"filename": filename, "error": f"S3 delete failed: {e}"})
            continue
        success = db.delete_pdf_by_filename(filename)
        if not success:
            errors.append({"filename": filename, "error": "Failed to delete from database"})
            continue
        deleted.append(filename)
        log_event(credentials.username, "delete_pdf", f"filename={filename}")
    return {"deleted": deleted, "errors": errors}


@router.get("/user/ingested_pdfs")
def list_ingested_pdfs(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    from Backend.services.postgres_db import get_ingested_pdfs_by_user

    pdfs = get_ingested_pdfs_by_user(credentials.username)
    log_event(credentials.username, "list_ingested_pdfs", f"count={len(pdfs)}")
    return {"ingested_pdfs": pdfs}


######################################
# User vectordb ingestion and management
######################################


@router.post("/user/vectordb/ingest/all")
def ingest_all(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    try:
        ingest.ingest_my_all_pdfs(user_id=credentials.username)
        log_event(credentials.username, "user_ingest_all_pdfs", "all user PDFs ingested")
        return {"detail": "All your PDFs ingested."}
    except Exception as e:
        log_event(credentials.username, "user_ingest_all_pdfs_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/vectordb/ingest/one/{filename}")
def ingest_by_filename(filename: str, credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    try:
        ingest.ingest_one_pdf_user(filename, user_id=credentials.username)
        log_event(credentials.username, "user_ingest_pdf", f"filename={filename}")
        return {"detail": f"PDF '{filename}' ingested."}
    except Exception as e:
        log_event(credentials.username, "user_ingest_pdf_failed", f"filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/user/vectordb/pdf/one/{filename}")
def remove_pdf_data(filename: str, credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    try:
        vectordb.clear_pdf_by_source(filename, credentials.username)
        log_event(credentials.username, "user_remove_pdf_data", f"filename={filename}")
        return {"detail": f"PDF data for '{filename}' removed from vectordb."}
    except Exception as e:
        log_event(
            credentials.username,
            "user_remove_pdf_data_failed",
            f"filename={filename}, error={str(e)}",
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/user/vectordb/pdf/all")
def remove_all_pdf_data(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    try:
        vectordb.clear_pdf_by_user(credentials.username)
        from Backend.services.postgres_db import get_ingested_pdfs_by_user, delete_ingested_pdf_by_id

        ingested = get_ingested_pdfs_by_user(credentials.username)
        for pdf in ingested:
            delete_ingested_pdf_by_id(pdf["id"])
        log_event(credentials.username, "user_remove_all_pdf_data", "all user PDF data removed from vectordb")
        return {"detail": "All your PDF data removed from vectordb."}
    except Exception as e:
        log_event(credentials.username, "user_remove_all_pdf_data_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/vectordb/pdf")
def get_available_pdf_data(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    try:
        sources = vectordb.get_pdf_sources()
        filtered = [
            s for s in sources if s["ingested_by"] == credentials.username or s["ingested_by"] == "public"
        ]
        log_event(credentials.username, "user_list_vectordb_sources", f"count={len(filtered)}")
        return {"sources": filtered}
    except Exception as e:
        log_event(credentials.username, "user_list_vectordb_sources_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/user/vectordb/memory")
def clear_my_memory(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    try:
        vectordb.clear_history_by_user(credentials.username)
        log_event(credentials.username, "user_clear_memory", "chat history cleared from vectordb")
        return {"detail": "Your chat history cleared from vectordb."}
    except Exception as e:
        log_event(credentials.username, "user_clear_memory_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))


######################################
# User chat
######################################


class ChatRequest(BaseModel):
    user_id: str
    message: str


@router.post("/user/chat")
async def chat(req: ChatRequest, credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    user_id = credentials.username
    mem_docs = await asyncio.to_thread(vectordb.retrieve_user_memory, user_id, req.message, 3)
    pdf_docs = await asyncio.to_thread(vectordb.retrieve_pdf_for_user, user_id, req.message, 3)

    mem_text = "\n".join([d.page_content for d in mem_docs]) if mem_docs else "No previous conversation found."
    pdf_text = "\n".join([d.page_content for d in pdf_docs]) if pdf_docs else "No relevant documents found."

    await asyncio.to_thread(vectordb.save_user_message, user_id, req.message)

    prompt = f"""
    Previous conversation:
    {mem_text}

    Relevant documents:
    {pdf_text}

    User: {req.message}
    Answer:
    """

    response = await asyncio.to_thread(chatmodel.predict, prompt)
    # Save assistant response in history as well
    await asyncio.to_thread(vectordb.save_assistant_message, user_id, response)

    log_event(user_id, "user_chat", f"message={req.message}")
    return {"response": response, "prompt": prompt}


@router.get("/user/chat/history")
async def get_my_history(credentials: HTTPBasicCredentials = Depends(verify_user_credentials)):
    history = vectordb.get_all_history(credentials.username)
    log_event(credentials.username, "user_get_chat_history", f"count={len(history)}")
    return {"user_id": credentials.username, "history": history}

