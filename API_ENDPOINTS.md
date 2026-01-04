# AWS RAG Chatbot - API Endpoints

Complete list of all API endpoints for AWS API Gateway configuration.

## **Admin Authentication Endpoints**
- `GET /admin/auth/check` → Check admin authentication

## **Admin User Management Endpoints**
- `POST /admin/users` → Add user
- `DELETE /admin/users/{username}` → Delete user
- `POST /admin/users/{username}/reset_password` → Reset user password
- `GET /admin/users` → List all users

## **Admin PDF Management Endpoints**
- `POST /admin/pdf/upload` → Upload PDFs (supports PDF, DOCX, TXT)
- `GET /admin/pdf` → List all PDFs
- `POST /admin/pdf/delete` → Delete specific PDFs (batch delete)
- `POST /admin/pdf/delete_public` → Delete all public PDFs

## **Admin Chat History Endpoints**
- `GET /admin/chat/history/{user_id}` → Get chat history for specific user

## **Admin Vector Database Endpoints**
- `POST /admin/vectordb/ingest/all` → Ingest all public PDFs into vector database
- `POST /admin/vectordb/ingest/one/{filename}` → Ingest one specific PDF
- `POST /admin/vectordb/ingest/public/{filename}` → Ingest PDF as public
- `POST /admin/vectordb/ingest/private/{filename}` → Ingest PDF as private for specific user
- `DELETE /admin/vectordb/pdf/{filename}` → Remove PDF data from vector database by filename
- `DELETE /admin/vectordb/pdf/user/{owner}` → Remove all PDF data for specific user
- `GET /admin/vectordb/pdf` → Get available PDF data sources
- `DELETE /admin/vectordb/memory` → Clear all users' chat memory
- `DELETE /admin/vectordb/memory/{user_id}` → Clear specific user's chat memory

## **User Authentication Endpoints**
- `GET /user/auth/check` → Check user authentication
- `POST /user/register` → Self-service user registration (requires registration code)
- `POST /user/login` → User login

## **User PDF Management Endpoints**
- `POST /user/pdf/upload` → Upload PDFs (supports PDF, DOCX, TXT)
- `GET /user/pdf` → List user's PDFs
- `POST /user/pdf/delete` → Delete specific PDFs (batch delete)
- `GET /user/ingested_pdfs` → List ingested PDFs for user

## **User Vector Database Endpoints**
- `POST /user/vectordb/ingest/all` → Ingest all user's PDFs into vector database
- `POST /user/vectordb/ingest/one/{filename}` → Ingest one specific PDF
- `DELETE /user/vectordb/pdf/one/{filename}` → Remove specific PDF data from vector database
- `DELETE /user/vectordb/pdf/all` → Remove all user's PDF data from vector database
- `GET /user/vectordb/pdf` → Get available PDF data sources for user
- `DELETE /user/vectordb/memory` → Clear user's chat memory

## **User Chat Endpoints**
- `POST /user/chat` → Send chat message and get AI response
- `GET /user/chat/history` → Get user's chat history

---

**Total: 33 endpoints** (17 admin endpoints + 16 user endpoints)

## Notes for AWS API Gateway Configuration

- All admin endpoints require HTTP Basic Authentication with admin credentials
- All user endpoints (except `/user/register` and `/user/login`) require HTTP Basic Authentication with user credentials
- Admin credentials are configured via environment variables: `ADMIN_USERNAME` and `ADMIN_PASSWORD`
- File uploads support PDF, DOCX, and TXT formats
- Files are stored in S3 with keys stored in PostgreSQL database
- Vector database operations use embeddings for RAG functionality
