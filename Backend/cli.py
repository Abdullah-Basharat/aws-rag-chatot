import os
from getpass import getpass
from typing import List

from Backend.services import postgres_db as db
from Backend.services import ingest
from Backend.services import vector_store as vectordb
from Backend.services import s3_storage
from Backend.services.logger import log_event


def _input_non_empty(prompt: str) -> str:
    value = input(prompt).strip()
    while not value:
        value = input(prompt).strip()
    return value


def user_management_menu() -> None:
    print("\n--- User Management ---")
    print("1. List users")
    print("2. Add user")
    print("3. Delete user")
    print("4. Reset user password")
    print("0. Back to main menu")


def chat_management_menu() -> None:
    print("\n--- Chat Management ---")
    print("1. View user chat history")
    print("0. Back to main menu")


def data_management_menu() -> None:
    print("\n--- Data Management ---")
    print("1. Upload PDF(s)")
    print("2. Upload all PDFs from folder")
    print("3. List all PDFs")
    print("4. Delete PDF(s)")
    print("5. Delete all public PDFs")
    print("0. Back to main menu")


def vectordb_management_menu() -> None:
    print("\n--- VectorDB Management ---")
    print("1. Ingest all public PDFs")
    print("2. Ingest PDF by filename (public or specific user)")
    print("3. Remove PDF data by filename")
    print("4. Remove PDF data by user")
    print("5. List available PDF data")
    print("6. Clear all users' memory")
    print("7. Clear user memory by user ID")
    print("0. Back to main menu")


def _upload_files_to_s3(owner: str, file_paths: List[str], is_public: bool) -> None:
    for path in file_paths:
        path = path.strip().strip('"')
        if not path:
            continue
        if not os.path.isfile(path):
            print(f"  ! Skipping missing file: {path}")
            continue
        filename = os.path.basename(path)
        _, ext = os.path.splitext(filename)
        if ext.lower() not in {".pdf", ".docx", ".txt"}:
            print(f"  ! Skipping unsupported file type: {filename}")
            continue
        if is_public:
            s3_key = os.path.join("public", filename)
        else:
            s3_key = os.path.join(owner, filename)
        with open(path, "rb") as f:
            s3_storage.upload_fileobj(f, s3_key)
        db.add_pdf(filename, owner, int(is_public), s3_key)
        print(f"  ✓ Uploaded {filename} (public={is_public})")


def _admin_user_management() -> None:
    while True:
        user_management_menu()
        choice = input("Select option: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            users = db.get_all_users()
            print("\nUsers:")
            for u in users:
                print(f"  id={u['id']} userid={u['userid']}")
        elif choice == "2":
            username = _input_non_empty("New username: ")
            password = getpass("New password: ")
            if db.add_user(username, password):
                log_event(username, "admin_add_user_cli", "success")
                print("User created.")
            else:
                print("User already exists.")
        elif choice == "3":
            username = _input_non_empty("Username to delete: ")
            if db.delete_user(username):
                log_event(username, "admin_delete_user_cli", "success")
                print("User deleted.")
            else:
                print("User not found.")
        elif choice == "4":
            username = _input_non_empty("Username to reset password: ")
            new_pw = getpass("New password: ")
            if db.update_user_password(username, new_pw):
                log_event(username, "admin_reset_password_cli", "success")
                print("Password updated.")
            else:
                print("User not found.")
        else:
            print("Invalid choice.")


def _admin_chat_management() -> None:
    while True:
        chat_management_menu()
        choice = input("Select option: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            user_id = _input_non_empty("User ID to view history: ")
            history = vectordb.get_all_history(user_id)
            print(f"\nChat history for {user_id}:")
            for msg in history:
                print(f"  - {msg}")
        else:
            print("Invalid choice.")


def _admin_data_management() -> None:
    while True:
        data_management_menu()
        choice = input("Select option: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            owner = "admin"
            paths = input(
                "Enter full paths to PDF/DOCX/TXT files (comma-separated): "
            ).split(",")
            is_public = input("Make public? [y/N]: ").strip().lower() == "y"
            _upload_files_to_s3(owner, paths, is_public)
        elif choice == "2":
            owner = "admin"
            folder = _input_non_empty("Folder containing PDFs/DOCX/TXT: ")
            if not os.path.isdir(folder):
                print("Folder does not exist.")
                continue
            files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith((".pdf", ".docx", ".txt"))
            ]
            is_public = input("Make public? [y/N]: ").strip().lower() == "y"
            _upload_files_to_s3(owner, files, is_public)
        elif choice == "3":
            pdfs = db.get_all_pdfs()
            print("\nStored documents:")
            for p in pdfs:
                print(
                    f"  id={p['id']} filename={p['filename']} uploaded_by={p['uploaded_by']} is_public={p['is_public']}"
                )
        elif choice == "4":
            names = input(
                "Enter filenames to delete from storage (comma-separated): "
            ).split(",")
            names = [n.strip() for n in names if n.strip()]
            for name in names:
                pdfs = db.get_all_pdfs()
                pdf_info = next(
                    (p for p in pdfs if p["filename"] == name),
                    None,
                )
                if not pdf_info:
                    print(f"  ! Not found in DB: {name}")
                    continue
                s3_storage.delete_object(pdf_info["filepath"])
                db.delete_pdf_by_id(pdf_info["id"])
                print(f"  ✓ Deleted {name}")
        elif choice == "5":
            pdfs = db.get_all_pdfs()
            for pdf in pdfs:
                if pdf["is_public"] != 1:
                    continue
                s3_storage.delete_object(pdf["filepath"])
                db.delete_pdf_by_id(pdf["id"])
            print("All public PDFs deleted.")
        else:
            print("Invalid choice.")


def _admin_vectordb_management() -> None:
    while True:
        vectordb_management_menu()
        choice = input("Select option: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            ingest.ingest_all_pdfs()
        elif choice == "2":
            filename = _input_non_empty("Filename to ingest: ")
            mode = input("Ingest as [p]ublic or [u]ser-specific? [p/u]: ").strip().lower()
            if mode == "u":
                user_id = _input_non_empty("User ID: ")
                ingest.ingest_one_pdf_admin(filename, user_id=user_id)
            else:
                ingest.ingest_one_pdf_public(filename)
        elif choice == "3":
            filename = _input_non_empty("Filename to remove from vectordb: ")
            vectordb.clear_pdf_by_source(filename)
            print("Vector data removed.")
        elif choice == "4":
            user_id = _input_non_empty("User ID to remove data for: ")
            vectordb.clear_pdf_by_user(user_id)
            print("All vector data for user removed.")
        elif choice == "5":
            sources = vectordb.get_pdf_sources()
            print("\nAvailable vector sources:")
            for s in sources:
                print(f"  source={s['source']} ingested_by={s['ingested_by']}")
        elif choice == "6":
            vectordb.clear_history_all()
            print("All users' chat memories cleared.")
        elif choice == "7":
            user_id = _input_non_empty("User ID to clear memory for: ")
            vectordb.clear_history_by_user(user_id)
            print("User chat memory cleared.")
        else:
            print("Invalid choice.")


def admin_main_menu() -> None:
    while True:
        print("\n=== Admin Main Menu ===")
        print("1. User Management")
        print("2. Chat Management")
        print("3. Data Management")
        print("4. VectorDB Management")
        print("0. Exit")
        choice = input("Select option: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            _admin_user_management()
        elif choice == "2":
            _admin_chat_management()
        elif choice == "3":
            _admin_data_management()
        elif choice == "4":
            _admin_vectordb_management()
        else:
            print("Invalid choice.")


def user_main_menu(user_id: str) -> None:
    while True:
        print("\n=== User Main Menu ===")
        print("1. Upload PDFs")
        print("2. Upload all PDFs from folder")
        print("3. List my PDFs")
        print("4. Ingest a PDF")
        print("5. Ingest all my PDFs")
        print("6. List my ingested PDFs")
        print("7. Delete a PDF from storage")
        print("8. Delete all my PDFs from storage")
        print("9. Remove a PDF from vectordb")
        print("10. Remove all my PDFs from vectordb")
        print("0. Exit")
        choice = input("Select option: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            paths = input(
                "Enter full paths to your PDF/DOCX/TXT files (comma-separated): "
            ).split(",")
            is_public = input("Make public? [y/N]: ").strip().lower() == "y"
            _upload_files_to_s3(user_id, paths, is_public)
        elif choice == "2":
            folder = _input_non_empty("Folder containing your PDFs/DOCX/TXT: ")
            if not os.path.isdir(folder):
                print("Folder does not exist.")
                continue
            files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith((".pdf", ".docx", ".txt"))
            ]
            is_public = input("Make public? [y/N]: ").strip().lower() == "y"
            _upload_files_to_s3(user_id, files, is_public)
        elif choice == "3":
            pdfs = db.get_pdfs_by_user(user_id)
            print("\nYour stored PDFs:")
            for p in pdfs:
                print(
                    f"  id={p['id']} filename={p['filename']} is_public={p['is_public']}"
                )
        elif choice == "4":
            filename = _input_non_empty("Filename to ingest: ")
            ingest.ingest_one_pdf_user(filename, user_id=user_id)
        elif choice == "5":
            ingest.ingest_my_all_pdfs(user_id=user_id)
        elif choice == "6":
            ingested = db.get_ingested_pdfs_by_user(user_id)
            print("\nYour ingested PDFs:")
            for row in ingested:
                print(
                    f"  id={row['id']} filename={row['filename']} is_public={row['is_public']}"
                )
        elif choice == "7":
            filename = _input_non_empty("Filename to delete from storage: ")
            pdfs = db.get_pdfs_by_user(user_id)
            pdf_info = next(
                (p for p in pdfs if p["filename"] == filename),
                None,
            )
            if not pdf_info:
                print("Not found.")
                continue
            s3_storage.delete_object(pdf_info["filepath"])
            db.delete_pdf_by_id(pdf_info["id"])
            print("Deleted.")
        elif choice == "8":
            pdfs = db.get_pdfs_by_user(user_id)
            for p in pdfs:
                s3_storage.delete_object(p["filepath"])
                db.delete_pdf_by_id(p["id"])
            print("All your PDFs deleted from storage.")
        elif choice == "9":
            filename = _input_non_empty("Filename to remove from vectordb: ")
            vectordb.clear_pdf_by_source(filename, user_id=user_id)
            print("Vector data removed.")
        elif choice == "10":
            vectordb.clear_pdf_by_user(user_id)
            print("All your PDFs removed from vectordb.")
        else:
            print("Invalid choice.")


def main() -> None:
    print("Backend CLI interface for AWS RAG Chatbot")
    while True:
        print("\n1. Admin login")
        print("2. User login")
        print("0. Exit")
        choice = input("Select option: ").strip()
        if choice == "0":
            break
        elif choice == "1":
            admin_username = _input_non_empty("Admin username: ")
            admin_password = getpass("Admin password: ")
            # For CLI we rely on environment-based admin credentials
            expected_user = os.getenv("ADMIN_USERNAME", "admin")
            expected_pw = os.getenv("ADMIN_PASSWORD", "123123")
            if (
                admin_username == expected_user
                and admin_password == expected_pw
            ):
                log_event(admin_username, "admin_login_cli", "success")
                admin_main_menu()
            else:
                log_event(admin_username, "admin_login_cli", "failed")
                print("Invalid admin credentials.")
        elif choice == "2":
            username = _input_non_empty("User ID: ")
            password = getpass("Password: ")
            if db.authenticate_user(username, password):
                log_event(username, "user_login_cli", "success")
                user_main_menu(username)
            else:
                log_event(username, "user_login_cli", "failed")
                print("Invalid username or password.")
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()


