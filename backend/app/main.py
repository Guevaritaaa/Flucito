from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.chat import router as chat_router

app = FastAPI(title="Flucito API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://flucito-1.onrender.com"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"mensaje": "Flucito API corriendo"}