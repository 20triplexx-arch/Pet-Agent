"""Connection reuse without sharing request callbacks, metering, or credentials."""
import asyncio
import hashlib
import weakref
from contextvars import ContextVar
from types import SimpleNamespace
from openai import AsyncOpenAI as SDKClient

section_sink: ContextVar[object | None] = ContextVar('chat_section_sink', default=None)
# Only isolated evaluation workers install this observer. Production logs keep metadata only.
request_observer: ContextVar[object | None] = ContextVar('model_request_observer', default=None)
_pools = weakref.WeakKeyDictionary()


def acquire_client(factory, selection, timeout):
    # Mock/capture factories own their transports. Never retain them across tests.
    if factory is not SDKClient:
        return factory(api_key=selection.key, base_url=selection.base_url,
                       max_retries=0, timeout=timeout), False
    loop = asyncio.get_running_loop()
    pool = _pools.setdefault(loop, {})
    key = (selection.provider, selection.base_url,
           hashlib.sha256(selection.key.encode()).digest(), timeout)
    client = pool.get(key)
    if client is None or client.is_closed():
        client = factory(api_key=selection.key, base_url=selection.base_url,
                         max_retries=0, timeout=timeout)
        pool[key] = client
    return client, True


async def close_clients():
    pool = _pools.pop(asyncio.get_running_loop(), {})
    for client in pool.values():
        await client.close()


class RequestClient:
    """The provider sees a private completion hook on a shared HTTP connection."""
    def __init__(self, client, create):
        self._source = client
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    def __getattr__(self, name):
        return getattr(self._source, name)


class MeteredStream:
    def __init__(self, stream, consume):
        self.stream, self.consume = stream, consume

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def __aiter__(self):
        try:
            async for chunk in self.stream:
                self.consume(chunk)
                yield chunk
        finally:
            await self.close()

    async def close(self):
        await self.stream.close()

    def __getattr__(self, name):
        return getattr(self.stream, name)
