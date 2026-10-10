import asyncio, json
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits
from fastapi import HTTPException
from app.core.config import settings
from app.models import ModelUsage


async def run_model(ctx, text, history, profile, articles):
    from app.agent import agent

    client = AsyncOpenAI(
        api_key=settings.MODEL_API_KEY,
        base_url=settings.MODEL_BASE_URL,
        max_retries=0,
        timeout=settings.MODEL_TIMEOUT_SECONDS,
    )
    model = OpenAIChatModel(
        settings.MODEL_NAME, provider=OpenAIProvider(openai_client=client)
    )
    payload = {
        "current_profile": profile,
        "history": history[-8:],
        "retrieved_data": articles,
        "user_message": text,
    }
    prompt = json.dumps(payload, ensure_ascii=False)
    if len(prompt) > 24000:
        prompt = json.dumps(
            {**payload, "history": history[-2:], "retrieved_data": articles[:2]},
            ensure_ascii=False,
        )
    if len(prompt) > 30000:
        raise HTTPException(422, "上下文过长，请简化档案或问题")
    try:
        result = await asyncio.wait_for(
            agent.run(
                prompt,
                model=model,
                deps=ctx,
                model_settings={
                    "max_tokens": settings.MODEL_MAX_OUTPUT_TOKENS,
                    "temperature": 0.2,
                },
                usage_limits=UsageLimits(
                    request_limit=settings.MODEL_MAX_REQUESTS,
                    tool_calls_limit=8,
                    input_tokens_limit=24000,
                    output_tokens_limit=settings.MODEL_MAX_OUTPUT_TOKENS
                    * settings.MODEL_MAX_REQUESTS,
                ),
            ),
            timeout=settings.MODEL_TIMEOUT_SECONDS,
        )
        usage = result.usage
        ctx.session.add(
            ModelUsage(
                user_id=ctx.user.id,
                model=settings.MODEL_NAME,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                requests=usage.requests,
            )
        )
        answer = result.output
        if any(i not in ctx.retrieved for i in answer.citation_ids):
            raise HTTPException(502, "模型返回了未检索来源，本次回答未保存")
        return answer
    except HTTPException:
        raise
    except Exception as e:
        # No key, endpoint, or provider response is exposed.
        raise HTTPException(
            503, "模型请求失败或超出限制，本次未完成。可重试或在服务端切回演示模式。"
        ) from e
    finally:
        await client.close()
