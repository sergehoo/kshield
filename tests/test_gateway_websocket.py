import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from kshield.asgi import application


@pytest.mark.django_db
def test_gateway_websocket_accepts_agent_bearer_token(kaydan_tenant):
    from devices.models import LocalAgent

    agent = LocalAgent.objects.create(
        tenant=kaydan_tenant,
        label="Gateway WebSocket",
        api_token="gateway-ws-token",
        hmac_secret="gateway-ws-hmac",
    )

    async def scenario():
        communicator = WebsocketCommunicator(
            application,
            f"/ws/agents/{agent.pk}/",
            headers=[(b"authorization", b"Bearer gateway-ws-token")],
        )

        connected, _ = await communicator.connect()

        assert connected is True
        message = await communicator.receive_json_from()
        assert message["type"] == "hello"
        assert message["agent_id"] == str(agent.pk)
        await communicator.disconnect()

    async_to_sync(scenario)()
