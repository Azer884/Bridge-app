"""Bridge WhatsApp Cloud call events into LiveKit Cloud."""

import asyncio
import json


async def _handle_with_livekit(event, env):
    from livekit import api
    from livekit.protocol.agent_dispatch import RoomAgentDispatch

    livekit = api.LiveKitAPI(url=env["LIVEKIT_URL"], api_key=env["LIVEKIT_API_KEY"],
                             api_secret=env["LIVEKIT_API_SECRET"])
    try:
        call_id = event["id"]
        if event["event"] == "connect":
            if event.get("sdp_type") != "offer" or not event.get("sdp"):
                raise ValueError("inbound connect event has no SDP offer")
            phone_id = event.get("phone_number_id") or env.get("WHATSAPP_PHONE_NUMBER_ID", "")
            if not phone_id or not env.get("WHATSAPP_TOKEN"):
                raise RuntimeError("WhatsApp phone number ID or access token is not configured")
            agent_name = env.get("WHATSAPP_LIVEKIT_AGENT_NAME", "orbyte-whatsapp")
            # Call ID is a stable, non-phone identifier for the existing chatbot conversation.
            await livekit.connector.accept_whatsapp_call(api.AcceptWhatsAppCallRequest(
                whatsapp_phone_number_id=phone_id,
                whatsapp_api_key=env["WHATSAPP_TOKEN"],
                whatsapp_cloud_api_version=env.get("WHATSAPP_CALL_GRAPH_API_VERSION", "26.0"),
                whatsapp_call_id=call_id,
                sdp={"type": "offer", "sdp": event["sdp"]},
                room_name=f"wa-call-{call_id}",
                agents=[RoomAgentDispatch(agent_name=agent_name,
                                          metadata=json.dumps({"user_id": call_id}))],
            ))
        elif event["event"] == "terminate":
            await livekit.connector.disconnect_whatsapp_call(api.DisconnectWhatsAppCallRequest(
                whatsapp_call_id=call_id,
                disconnect_reason=api.DisconnectWhatsAppCallRequest.USER_INITIATED,
            ))
    finally:
        await livekit.aclose()


def handle_call_event(event, env):
    """Synchronous webhook background-task entry point."""
    required = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise RuntimeError("LiveKit credentials are not configured")
    asyncio.run(_handle_with_livekit(event, env))
