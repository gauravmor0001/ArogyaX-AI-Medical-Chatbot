import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bot import router as chat_router

app = FastAPI(title="Arogya Medical AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)

print("Arogya Server is starting up...")
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)