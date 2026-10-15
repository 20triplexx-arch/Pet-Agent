"""SSE sends checked sections and only committed final replies."""
import asyncio
import json
from contextlib import suppress
from typing import Annotated
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import select
from app.api.deps import SessionDep, CurrentUser
from app.schemas import ChatInput
from app.models import IdempotencyRecord, Pet, Conversation
from app.services import owned
from app.chat_requests import begin_chat, run_registered, ChatRequests
from app.model_runtime import section_sink
from app.execution import current_execution

router = APIRouter(prefix='/api/v1')
Key = Annotated[str | None, Header(alias='Idempotency-Key')]


def event(name, data):
    return 'event: ' + name + '\ndata: ' + json.dumps(data, ensure_ascii=False, default=str) + '\n\n'


@router.get('/chat/status')
def chat_status(session: SessionDep, user: CurrentUser, key: Key = None):
    registry = ChatRequests(session, user.id, key)
    row = session.exec(select(IdempotencyRecord).where(IdempotencyRecord.user_id == user.id, IdempotencyRecord.key == key)).first()
    if row:
        return {'state': 'complete', 'response': row.result}
    return registry.status()


@router.post('/chat/stream')
async def chat_stream(data: ChatInput, request: Request, session: SessionDep, user: CurrentUser, key: Key = None):
    if data.pet_id:
        owned(session, Pet, data.pet_id, user.id)
    if data.conversation_id:
        conversation = owned(session, Conversation, data.conversation_id, user.id)
        if conversation.pet_id != data.pet_id:
            raise HTTPException(409, '会话与当前宠物不匹配')
    registry, replay = begin_chat(data, session, user, key)
    trace = current_execution.get()
    if replay is not None and trace:
        trace.replayed = True

    async def body():
        yield event('accepted', {'request_id': trace.request_id if trace else None, 'replayed': replay is not None})
        if replay is not None:
            yield event('final', replay)
            return
        queue = asyncio.Queue(maxsize=8)

        async def section(value):
            await queue.put(('section', value))

        async def generate():
            token = section_sink.set(section)
            try:
                result = await run_registered(data, session, user, key, registry)
                if trace:
                    trace.application_status = 200
                await queue.put(('final', result))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if trace:
                    trace.application_status = getattr(exc, 'status_code', 503)
                await queue.put(('error', {'detail': exc.detail if isinstance(exc, HTTPException) else '回答未完成，请手动重试。', 'status': getattr(exc, 'status_code', 503), 'retract': True}))
            finally:
                section_sink.reset(token)

        task = asyncio.create_task(generate())
        try:
            while True:
                try:
                    name, value = await asyncio.wait_for(queue.get(), timeout=5)
                except TimeoutError:
                    yield ': keep-alive\n\n'
                    continue
                yield event(name, value)
                if name in ('final', 'error'):
                    break
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(body(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
