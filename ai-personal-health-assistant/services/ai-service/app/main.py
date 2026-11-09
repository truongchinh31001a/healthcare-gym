from typing import Literal
from fastapi import FastAPI
from pydantic import BaseModel
class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["ai-service"] = "ai-service"
app = FastAPI(title="Personal Health Assistant AI Service", version="0.1.0")
@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return HealthResponse()
