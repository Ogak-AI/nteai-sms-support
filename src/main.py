"""
Main FastAPI Application
SMS-based Customer Support System using Voicebip MCP
"""

import json
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.config import settings
from src.voicebip_client import voicebip_client
from src.sms_handler import sms_handler
from src.logging_config import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("application_starting", environment=settings.environment)
    # Startup logic here
    yield
    # Shutdown logic
    await voicebip_client.close()
    logger.info("application_shutdown")


app = FastAPI(
    title="NteAI SMS Support",
    description="SMS-based Customer Support System using Voicebip MCP",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [settings.webhook_url] if settings.webhook_url else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_webhook_signature(
    request: Request,
    x_voicebip_signature: str = Header(..., alias="X-Voicebip-Signature"),
    x_voicebip_timestamp: str = Header(..., alias="X-Voicebip-Timestamp"),
    x_voicebip_event_id: str = Header(..., alias="X-Voicebip-Event-ID"),
) -> Dict[str, Any]:
    """Verify Voicebip webhook signature."""
    body = await request.body()

    # Verify timestamp (prevent replay attacks)
    if not voicebip_client.is_valid_timestamp(x_voicebip_timestamp):
        logger.warning("invalid_webhook_timestamp", timestamp=x_voicebip_timestamp)
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    # Verify signature
    if not voicebip_client.verify_webhook_signature(x_voicebip_signature, x_voicebip_timestamp, body):
        logger.warning("invalid_webhook_signature", event_id=x_voicebip_event_id)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON body
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error("invalid_json_payload", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")

    return payload


@app.post("/webhook")
async def voicebip_webhook(
    payload: Dict[str, Any] = Depends(verify_webhook_signature),
) -> JSONResponse:
    """
    Voicebip webhook endpoint for incoming SMS messages and delivery receipts.
    """
    logger.info("webhook_received", event_type=payload.get("event_type"), event_id=payload.get("event_id"))

    try:
        result = await sms_handler.process_webhook(payload)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("webhook_processing_error", error=str(e), payload=payload)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "nteai-sms-support"}


@app.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    """Readiness check endpoint."""
    # Could add checks for Voicebip API connectivity, etc.
    return {
        "status": "ready",
        "service": "nteai-sms-support",
        "voicebip_configured": bool(settings.voicebip_api_key),
        "agent_configured": bool(settings.voicebip_agent_id),
    }


@app.post("/test/send-sms")
async def test_send_sms(
    to_number: str,
    body: str,
) -> Dict[str, Any]:
    """Test endpoint to send an SMS (development only)."""
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Not available in production")

    result = await voicebip_client.send_message(
        agent_id=settings.voicebip_agent_id,
        channel="sms",
        from_number=settings.voicebip_provisioned_number,
        to_number=to_number,
        body=body,
    )
    return {"success": True, "result": result}


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint."""
    return {
        "service": "NteAI SMS Support",
        "version": "1.0.0",
        "docs": "/docs",
        "webhook": "/webhook",
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )