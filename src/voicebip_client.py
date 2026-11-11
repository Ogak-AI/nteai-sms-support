"""
Voicebip API Client
Wrapper for Voicebip REST API calls
"""

import hmac
import hashlib
import time
from typing import Any, Dict, List, Optional
import httpx
from src.config import settings
from src.logging_config import logger


class VoicebipClient:
    """Client for interacting with Voicebip REST API."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            base_url=settings.voicebip_api_url,
            headers={
                "Authorization": f"Bearer {settings.voicebip_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "NteAI-SMS-Support/1.0.0",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request with logging."""
        logger.debug("voicebip_api_request", method=method, path=path)
        try:
            response = await self.client.request(method, path, **kwargs)
            response.raise_for_status()
            logger.debug("voicebip_api_response", status=response.status_code, path=path)
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "voicebip_api_error",
                status=e.response.status_code,
                path=path,
                error=str(e),
                response=e.response.text,
            )
            raise
        except Exception as e:
            logger.error("voicebip_api_exception", path=path, error=str(e))
            raise

    # Agent methods
    async def create_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/agents", json=agent_data)

    async def list_agents(self) -> List[Dict[str, Any]]:
        return await self._request("GET", "/agents")

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/agents/{agent_id}")

    async def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("PATCH", f"/agents/{agent_id}", json=updates)

    async def delete_agent(self, agent_id: str) -> None:
        await self._request("DELETE", f"/agents/{agent_id}")

    # Number methods
    async def list_available_numbers(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return await self._request("GET", "/numbers/available", params=filters or {})

    async def provision_number(self, agent_id: str, number_id: str) -> Dict[str, Any]:
        return await self._request("POST", "/numbers/provision", json={"agent_id": agent_id, "number_id": number_id})

    async def get_number(self, number_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/numbers/{number_id}")

    async def release_number(self, number_id: str) -> None:
        await self._request("DELETE", f"/numbers/{number_id}")

    # Messaging methods
    async def send_message(
        self,
        agent_id: str,
        channel: str,
        from_number: str,
        to_number: str,
        body: str,
    ) -> Dict[str, Any]:
        """Send an SMS or WhatsApp message."""
        message_data = {
            "agent_id": agent_id,
            "channel": channel,
            "from_number": from_number,
            "to_number": to_number,
            "body": body,
        }
        return await self._request("POST", "/messages", json=message_data)

    async def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/conversations/{conversation_id}")

    async def list_conversations(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return await self._request("GET", "/conversations", params=filters or {})

    async def update_conversation_mode(self, conversation_id: str, mode: str) -> Dict[str, Any]:
        return await self._request("PATCH", f"/conversations/{conversation_id}/mode", json={"mode": mode})

    async def send_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/messages/template", json=template_data)

    # Routing rules
    async def create_routing_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/routing-rules", json=rule_data)

    async def list_routing_rules(self) -> List[Dict[str, Any]]:
        return await self._request("GET", "/routing-rules")

    async def update_routing_rule(self, rule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("PATCH", f"/routing-rules/{rule_id}", json=updates)

    async def delete_routing_rule(self, rule_id: str) -> None:
        await self._request("DELETE", f"/routing-rules/{rule_id}")

    # Webhook verification
    def verify_webhook_signature(self, signature: str, timestamp: str, body: bytes) -> bool:
        """Verify HMAC-SHA256 webhook signature."""
        if not settings.voicebip_webhook_secret:
            logger.warning("webhook_secret_not_configured")
            return True  # Allow in development

        expected_signature = hmac.new(
            settings.voicebip_webhook_secret.encode(),
            f"{timestamp}.{body.decode()}".encode(),
            hashlib.sha256,
        ).hexdigest()

        provided_signature = signature.replace("sha256=", "")

        return hmac.compare_digest(expected_signature, provided_signature)

    def is_valid_timestamp(self, timestamp: str) -> bool:
        """Check if webhook timestamp is within 5 minutes."""
        try:
            webhook_time = int(timestamp) * 1000  # Convert to milliseconds
            now = int(time.time() * 1000)
            five_minutes = 5 * 60 * 1000
            return abs(now - webhook_time) <= five_minutes
        except ValueError:
            return False

    async def test_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Test webhook delivery to the agent."""
        return await self._request("POST", "/webhooks/test", json=payload)


# Global client instance
voicebip_client = VoicebipClient()