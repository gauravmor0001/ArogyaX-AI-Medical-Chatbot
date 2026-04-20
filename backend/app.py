import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the two separate brains
from bot import router as general_router
from vision import router as report_router

app = FastAPI(title="Arogya Medical AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Plug in both routers!
app.include_router(general_router) # Handles /chat
app.include_router(report_router)  # Handles /report/upload and /report/chat

if __name__ == "__main__":
    print("🚀 Arogya Server is starting up...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)