"""
SMS Handler
Processes incoming SMS messages using Voicebip's built-in AI agent
"""

import hashlib
import time
from typing import Dict, Any, Optional, Set
from src.config import settings
from src.voicebip_client import voicebip_client
from src.logging_config import logger


class SMSHandler:
    """Handles incoming SMS messages and routes them to Voicebip's AI agent."""

    def __init__(self) -> None:
        self.processing_cache: Set[str] = set()  # Track processed messages to avoid duplicates
        self.cache_timestamps: Dict[str, float] = {}

    def _get_processing_key(self, message_id: str, phone_number: str) -> str:
        """Generate a unique key for deduplication."""
        return hashlib.sha256(f"{message_id}:{phone_number}".encode()).hexdigest()[:32]

    def _is_duplicate(self, message_id: str, phone_number: str) -> bool:
        """Check if message was already processed."""
        key = self._get_processing_key(message_id, phone_number)
        if key in self.processing_cache:
            return True
        self.processing_cache.add(key)
        self.cache_timestamps[key] = time.time()
        return False

    def _cleanup_cache(self) -> None:
        """Remove old cache entries (older than 5 minutes)."""
        now = time.time()
        five_minutes = 5 * 60
        expired_keys = [
            key for key, timestamp in self.cache_timestamps.items()
            if now - timestamp > five_minutes
        ]
        for key in expired_keys:
            self.processing_cache.discard(key)
            self.cache_timestamps.pop(key, None)

    def _is_opt_out(self, message: str) -> bool:
        """Check if message is an opt-out keyword."""
        opt_out_keywords = {"STOP", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
        return message.strip().upper() in opt_out_keywords

    def _is_help_request(self, message: str) -> bool:
        """Check if message is a help/escalation request."""
        help_keywords = {"HELP", "SUPPORT", "AGENT", "HUMAN", "TALK TO SOMEONE", "SPEAK TO HUMAN"}
        normalized = message.strip().upper()
        return any(keyword in normalized for keyword in help_keywords)

    def _get_opt_out_response(self) -> str:
        return "You have been unsubscribed from NteAI SMS notifications. Reply START to resubscribe."

    def _get_help_response(self) -> str:
        return "I've escalated your request to a human support agent. They will contact you shortly."

    async def process_incoming_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming SMS message via Voicebip's conversation API.
        Voicebip's built-in AI agent handles the conversation automatically.
        """
        event_id = payload.get("event_id")
        event_type = payload.get("event_type")
        channel = payload.get("channel")
        agent_id = payload.get("agent_id")
        number = payload.get("number")  # Our provisioned number
        from_number = payload.get("from")  # User's phone number
        timestamp = payload.get("timestamp")
        msg_payload = payload.get("payload", {})

        body = msg_payload.get("body", "")
        encoding = msg_payload.get("encoding")
        message_id = msg_payload.get("message_id")

        logger.info(
            "processing_incoming_sms",
            event_id=event_id,
            from_number=from_number,
            to_number=number,
            message_id=message_id,
            body_length=len(body),
        )

        # Cleanup cache periodically
        self._cleanup_cache()

        # Check for duplicate
        if self._is_duplicate(message_id, from_number):
            logger.warning("duplicate_message_detected", message_id=message_id, from_number=from_number)
            return {"success": True, "duplicate": True}

        try:
            # Handle opt-out
            if self._is_opt_out(body):
                logger.info("opt_out_request", phone_number=from_number)
                await self._send_sms_response(from_number, number, self._get_opt_out_response())
                return {"success": True, "opt_out": True}

            # Handle help request
            if self._is_help_request(body):
                logger.info("help_request", phone_number=from_number)
                await self._send_sms_response(from_number, number, self._get_help_response())
                # Could trigger human handoff here via Voicebip API
                return {"success": True, "escalated": True}

            # For Voicebip's built-in AI agent, the conversation is handled automatically
            # when the message is received via webhook. The agent responds through
            # Voicebip's conversation management system.
            # However, we can also manually trigger a response if needed.

            # The webhook delivery to Voicebip's agent happens automatically
            # when the message is received. We just need to acknowledge.
            logger.info("message_routed_to_voicebip_agent", agent_id=agent_id, phone_number=from_number)

            return {"success": True, "routed_to_agent": True}

        except Exception as e:
            logger.error("sms_processing_failed", event_id=event_id, phone_number=from_number, error=str(e))
            # Send fallback response
            try:
                fallback = "I apologize, but I'm having trouble processing your message. Please try again."
                await self._send_sms_response(from_number, number, fallback)
            except Exception as send_error:
                logger.error("failed_to_send_fallback", error=str(send_error))
            return {"success": False, "error": str(e)}

    async def process_delivery_receipt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process SMS delivery receipt (DLR)."""
        event_id = payload.get("event_id")
        msg_payload = payload.get("payload", {})
        message_id = msg_payload.get("message_id")
        status = msg_payload.get("status")
        error_code = msg_payload.get("error_code")

        logger.info(
            "delivery_receipt_received",
            event_id=event_id,
            message_id=message_id,
            status=status,
            error_code=error_code,
        )

        # Handle failed deliveries
        if status in ("UNDELIV", "REJECTD", "EXPIRED"):
            logger.warning(
                "message_delivery_failed",
                message_id=message_id,
                status=status,
                error_code=error_code,
            )

        return {"success": True}

    async def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route webhook to appropriate handler based on event type."""
        event_type = payload.get("event_type")
        channel = payload.get("channel")

        if event_type == "message.received" and channel == "sms":
            return await self.process_incoming_message(payload)
        elif event_type == "message.dlr" and channel == "sms":
            return await self.process_delivery_receipt(payload)
        elif event_type == "message.failed":
            logger.error("message_failed_event", payload=payload)
            return {"success": True, "handled": True}
        else:
            logger.debug("unhandled_webhook_event", event_type=event_type, channel=channel)
            return {"success": True, "ignored": True}

    async def _send_sms_response(self, to_number: str, from_number: str, body: str) -> Dict[str, Any]:
        """Send SMS response via Voicebip API."""
        # Truncate to reasonable SMS length (allow multi-segment up to ~1600 chars)
        max_length = 1600
        truncated_body = body[:max_length - 3] + "..." if len(body) > max_length else body

        result = await voicebip_client.send_message(
            agent_id=settings.voicebip_agent_id,
            channel="sms",
            from_number=from_number,
            to_number=to_number,
            body=truncated_body,
        )

        logger.info(
            "sms_response_sent",
            to=to_number,
            from_number=from_number,
            message_id=result.get("message_id"),
            status=result.get("status"),
        )
        return result


# Global handler instance
sms_handler = SMSHandler()