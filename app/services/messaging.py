import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as redis

from ..config import settings

_redis: redis.Redis | None = None
_pending: dict[str, dict] = {}
_messages: dict[str, dict] = {}


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.valkey_url, decode_responses=True)
    return _redis


async def close() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def consume_stream() -> None:
    r = await get_redis()
    stream_key = settings.valkey_channel_agent_to_ui
    last_id = "$"
    while True:
        try:
            entries = await r.xread({stream_key: last_id}, block=5000, count=10)
            if not entries:
                continue
            for _stream, messages in entries:
                for entry_id, fields in messages:
                    last_id = entry_id
                    ts_ms = int(entry_id.split("-")[0])
                    ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
                    msg = dict(fields)
                    msg["stream_id"] = entry_id
                    msg["timestamp"] = ts
                    if "content" in msg:
                        msg["content"] = json.loads(msg["content"])
                    msg["needs_response"] = msg.get("needs_response", "False").lower() == "true"
                    _messages[msg["message_id"]] = msg
                    if msg["needs_response"]:
                        _pending[msg["message_id"]] = msg
        except redis.ConnectionError:
            await asyncio.sleep(2)
        except Exception:
            await asyncio.sleep(1)


def list_pending() -> list[dict]:
    return sorted(_pending.values(), key=lambda item: item["timestamp"])


def get_message(message_id: str) -> dict | None:
    return _messages.get(message_id)


def respond(message_id: str, response: str) -> dict | None:
    msg = _pending.pop(message_id, None)
    if msg is None:
        return None
    msg["response"] = response
    msg["needs_response"] = False
    _messages[message_id] = msg
    return msg
