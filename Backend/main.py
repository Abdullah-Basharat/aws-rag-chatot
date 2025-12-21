from fastapi import FastAPI
from dotenv import load_dotenv

from Backend.admin_dashboard import router as admin_router
from Backend.user_dashboard import router as user_router


load_dotenv()

app = FastAPI(title="AWS RAG Chatbot API")

# Admin endpoints
app.include_router(admin_router)

# User endpoints
app.include_router(user_router)



