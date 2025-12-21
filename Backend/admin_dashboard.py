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

import Backend.services.postgres_db as db
import Backend.services.ingest as ingest
import Backend.services.vector_store as vectordb
from Backend.services.logger import log_event
from Backend.services import s3_storage


router = APIRouter()

security = HTTPBasic()


######################################
# Admin authentication
######################################


def verify_admin_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = os.environ.get("ADMIN_USERNAME", "admin")
    correct_password = os.environ.get("ADMIN_PASSWORD", "123123")
    if credentials.username != correct_username or credentials.password != correct_password:
        log_event(credentials.username, "admin_auth_check", "failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    log_event(credentials.username, "admin_auth_check", "success")
    return credentials


@router.get("/admin/auth/check")
def admin_auth_check(credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    return {"detail": "Admin authentication successful."}


######################################
# Admin user management
######################################


class UserCreate(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str


@router.post("/admin/users", response_model=UserOut)
def add_user(user: UserCreate, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    success = db.add_user(user.username, user.password)
    if not success:
        log_event(credentials.username, "admin_add_user", f"username={user.username}, failed")
        raise HTTPException(status_code=400, detail="User already exists.")
    # Fetch the user to get the id
    users = db.get_all_users()
    for u in users:
        if u["userid"] == user.username:
            log_event(credentials.username, "admin_add_user", f"username={user.username}, id={u['id']}")
            return UserOut(id=u["id"], username=u["userid"])
    log_event(credentials.username, "admin_add_user", f"username={user.username}, failed to fetch id")
    raise HTTPException(status_code=500, detail="User creation failed.")


@router.delete("/admin/users/{username}")
def delete_user(username: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    success = db.delete_user(username)
    if not success:
        log_event(credentials.username, "admin_delete_user", f"username={username}, failed")
        raise HTTPException(status_code=404, detail="User not found.")
    log_event(credentials.username, "admin_delete_user", f"username={username}, success")
    return {"detail": "User deleted."}


class ResetPasswordRequest(BaseModel):
    password: str


@router.post("/admin/users/{username}/reset_password")
def reset_password(username: str, req: ResetPasswordRequest, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    success = db.update_user_password(username, req.password)
    if not success:
        log_event(credentials.username, "admin_reset_password", f"username={username}, failed")
        raise HTTPException(status_code=404, detail="User not found.")
    log_event(credentials.username, "admin_reset_password", f"username={username}, success")
    return {"detail": "Password reset successful."}


@router.get("/admin/users", response_model=List[UserOut])
def list_users(credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    users = db.get_all_users()
    log_event(credentials.username, "admin_list_users", f"count={len(users)}")
    return [UserOut(id=u["id"], username=u["userid"]) for u in users]


######################################
# Admin PDF management
######################################


PERSIST_DIR = os.getenv("PERSIST_DIR", "")
DATA_DIR = os.path.join(PERSIST_DIR, "data")


@router.post("/admin/pdf/upload")
def upload_pdf(
    files: List[UploadFile] = File(...),
    is_public: int = Form(0),
    credentials: HTTPBasicCredentials = Depends(verify_admin_credentials),
):
    """
    Upload PDFs to S3 instead of local disk.
    The database stores the S3 key in the `filepath` column.
    """
    uploaded = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            continue
        uploaded_by = "admin"
        if is_public:
            s3_key = os.path.join("public", file.filename)
        else:
            s3_key = os.path.join(uploaded_by, file.filename)
        # Push file content directly to S3
        s3_storage.upload_fileobj(file.file, s3_key)
        # Store S3 key in DB
        db.add_pdf(file.filename, uploaded_by, is_public, s3_key)
        uploaded.append(file.filename)
        log_event(credentials.username, "admin_upload_pdf", f"filename={file.filename}, is_public={is_public}")
    if not uploaded:
        raise HTTPException(status_code=400, detail="No valid PDFs uploaded.")
    return {"uploaded": uploaded}


@router.get("/admin/pdf")
def list_pdfs(credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    pdfs = db.get_all_pdfs()
    log_event(credentials.username, "admin_list_pdfs", f"count={len(pdfs)}")
    return {"pdfs": pdfs}


@router.post("/admin/pdf/delete")
def delete_pdf(
    data: dict = Body(...),
    credentials: HTTPBasicCredentials = Depends(verify_admin_credentials),
):
    filenames = data.get("filenames")
    if not filenames or not isinstance(filenames, list):
        raise HTTPException(status_code=400, detail="Missing or invalid 'filenames' (must be a list).")
    deleted = []
    errors = []
    for filename in filenames:
        pdfs = db.get_all_pdfs()
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
        fileid = pdf_info["id"]
        success = db.delete_pdf_by_id(fileid)
        if not success:
            errors.append({"filename": filename, "error": "Failed to delete from database"})
            continue
        deleted.append(filename)
        log_event(credentials.username, "admin_delete_pdf", f"filename={filename}")
    return {"deleted": deleted, "errors": errors}


@router.post("/admin/pdf/delete_public")
def delete_all_public_pdfs(credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    deleted = []
    errors = []
    pdfs = db.get_all_pdfs()
    for pdf in pdfs:
        if pdf["is_public"] != 1:
            continue
        filename = pdf["filename"]
        s3_key = pdf["filepath"]
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
        log_event(credentials.username, "admin_delete_public_pdf", f"filename={filename}")
    return {"deleted": deleted, "errors": errors}


######################################
# Admin chat history
######################################


@router.get("/admin/chat/history/{user_id}")
def get_chat_history(user_id: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        history = vectordb.get_all_history(user_id)
        log_event(credentials.username, "admin_get_chat_history", f"user_id={user_id}, count={len(history)}")
        return {"user_id": user_id, "history": history}
    except Exception as e:
        log_event(credentials.username, "admin_get_chat_history_failed", f"user_id={user_id}, error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


######################################
# Admin vectordb management
######################################


@router.post("/admin/vectordb/ingest/all")
def ingest_all(credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        ingest.ingest_all_pdfs()
        log_event(credentials.username, "admin_ingest_all_pdfs", "all public PDFs ingested")
        return {"detail": "All public PDFs ingested."}
    except Exception as e:
        log_event(credentials.username, "admin_ingest_all_pdfs_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/vectordb/ingest/one/{filename}")
def ingest_by_filename(filename: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        ingest.ingest_one_pdf_admin(filename)
        log_event(credentials.username, "admin_ingest_pdf", f"filename={filename}")
        return {"detail": f"PDF '{filename}' ingested."}
    except Exception as e:
        log_event(credentials.username, "admin_ingest_pdf_failed", f"filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/vectordb/ingest/public/{filename}")
def ingest_public_pdf(filename: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        ingest.ingest_one_pdf_public(filename)
        log_event(credentials.username, "admin_ingest_public_pdf", f"filename={filename}")
        return {"detail": f"PDF '{filename}' ingested as public."}
    except Exception as e:
        log_event(credentials.username, "admin_ingest_public_pdf_failed", f"filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/vectordb/ingest/private/{filename}")
def ingest_private_pdf(filename: str, user_id: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        ingest.ingest_one_pdf_private(filename, user_id)
        log_event(credentials.username, "admin_ingest_private_pdf", f"filename={filename}, user_id={user_id}")
        return {"detail": f"PDF '{filename}' ingested for user '{user_id}'."}
    except Exception as e:
        log_event(
            credentials.username,
            "admin_ingest_private_pdf_failed",
            f"filename={filename}, user_id={user_id}, error={str(e)}",
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/vectordb/pdf/{filename}")
def remove_pdf_data(filename: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        vectordb.clear_pdf_by_source(filename)
        log_event(credentials.username, "admin_remove_pdf_data", f"filename={filename}")
        return {"detail": f"PDF data for '{filename}' removed from vectordb."}
    except Exception as e:
        log_event(credentials.username, "admin_remove_pdf_data_failed", f"filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/vectordb/pdf/user/{owner}")
def remove_pdf_data_by_user(owner: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        vectordb.clear_pdf_by_user(owner)
        log_event(credentials.username, "admin_remove_pdf_data_by_user", f"owner={owner}")
        return {"detail": f"All PDF data for user '{owner}' removed from vectordb."}
    except Exception as e:
        log_event(
            credentials.username,
            "admin_remove_pdf_data_by_user_failed",
            f"owner={owner}, error={str(e)}",
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/vectordb/pdf")
def get_available_pdf_data(credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        sources = vectordb.get_pdf_sources()
        log_event(credentials.username, "admin_list_vectordb_sources", f"count={len(sources)}")
        return {"sources": sources}
    except Exception as e:
        log_event(credentials.username, "admin_list_vectordb_sources_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/vectordb/memory")
def clear_all_users_memory(credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        vectordb.clear_history_all()
        log_event(
            credentials.username,
            "admin_clear_all_users_memory",
            "all user chat histories cleared from vectordb",
        )
        return {"detail": "All user chat histories cleared from vectordb."}
    except Exception as e:
        log_event(credentials.username, "admin_clear_all_users_memory_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/vectordb/memory/{user_id}")
def clear_user_memory(user_id: str, credentials: HTTPBasicCredentials = Depends(verify_admin_credentials)):
    try:
        vectordb.clear_history_by_user(user_id)
        log_event(credentials.username, "admin_clear_user_memory", f"user_id={user_id}")
        return {"detail": f"Chat history for user '{user_id}' cleared from vectordb."}
    except Exception as e:
        log_event(
            credentials.username,
            "admin_clear_user_memory_failed",
            f"user_id={user_id}, error={str(e)}",
        )
        raise HTTPException(status_code=500, detail=str(e))

