import asyncio, json
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.usage import UsageLimits
from fastapi import HTTPException
from app.core.config import settings
from app.models import ModelUsage
from app.execution import current_execution
from app.evaluation_budget import current_budget, BudgetExceeded


async def run_model(ctx, text, history, profile, articles):
    from app.agent import agent

    if not settings.model_key:
        raise HTTPException(503, "真实模型密钥未配置，本次未完成。请检查服务端配置。")

    client = AsyncOpenAI(
        api_key=settings.model_key,
        base_url="https://api.deepseek.com" if settings.MODEL_PROVIDER == "deepseek" else settings.MODEL_BASE_URL,
        max_retries=0,
        timeout=settings.MODEL_TIMEOUT_SECONDS,
    )
    provider = DeepSeekProvider(openai_client=client) if settings.MODEL_PROVIDER == "deepseek" else OpenAIProvider(openai_client=client)
    model = OpenAIChatModel(settings.model_name, provider=provider)
    create = client.chat.completions.create

    async def measured_create(**kwargs):
        budget = current_budget.get()
        trace = current_execution.get()
        reservation = budget.reserve(kwargs) if budget else None
        if trace:
            trace.model_requests += 1
        try:
            response = await create(**kwargs)
            if budget:
                budget.settle(reservation, response.usage)
            if trace and response.usage:
                trace.input_tokens += response.usage.prompt_tokens or 0
                trace.output_tokens += response.usage.completion_tokens or 0
            return response
        except Exception as exc:
            if trace:
                trace.error_type = type(exc).__name__
            raise

    client.chat.completions.create = measured_create
    payload = {
        "current_profile": profile,
        "history": history[-8:],
        "retrieved_data": articles,
        "user_message": text,
    }
    if ctx.pet_id:
        from app.nutrition import care_history, current_plans
        payload["recent_care"] = [{**r, "note": r["note"][:300]} for r in care_history(ctx.session, ctx.user, ctx.pet_id)[:10]]
        payload["active_plans"] = [{"title": p["title"], "basis": p["basis"][:300]} for p in current_plans(ctx.session, ctx.user, ctx.pet_id)[:5]]
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
                    **({"extra_body": {"thinking": {"type": "disabled"}}} if settings.MODEL_PROVIDER == "deepseek" else {}),
                },
                usage_limits=UsageLimits(
                    request_limit=settings.MODEL_MAX_REQUESTS,
                    tool_calls_limit=8,
                    input_tokens_limit=settings.MODEL_MAX_INPUT_TOKENS,
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
                model=settings.model_name,
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
    except BudgetExceeded as e:
        raise HTTPException(429, "本阶段模型测试预算不足，本次未完成。") from e
    except Exception as e:
        # No key, endpoint, or provider response is exposed.
        if trace := current_execution.get():
            trace.error_type = trace.error_type or type(e).__name__
        def denied_tool(error):
            if isinstance(error, HTTPException) and error.status_code == 403:
                return True
            return any(denied_tool(child) for child in getattr(error, "exceptions", ()))
        if denied_tool(e):
            raise HTTPException(403, "本次工具写入未获得明确授权，未保存任何修改。") from e
        raise HTTPException(
            503, "模型请求失败或超出限制，本次未完成。可重试或在服务端切回演示模式。"
        ) from e
    finally:
        await client.close()
