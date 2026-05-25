from fastapi import APIRouter, HTTPException, Request, status

from src.models.schemas import (
    AuditLogData,
    AuditLogItem,
    AuditLogResponse,
    LlmHealthData,
    LlmHealthResponse,
    LlmRuntimeConfig,
    LlmRuntimeConfigData,
    LlmRuntimeConfigPatchRequest,
    LlmRuntimeConfigResponse,
    LlmTestData,
    LlmTestRequest,
    LlmTestResponse,
)
from src.utils.response import response_meta
from src.utils.security import require_permission, require_role
from src.utils.feature_flags import feature_enabled

router = APIRouter()


@router.get("/llm/config", response_model=LlmRuntimeConfigResponse)
async def get_llm_config(request: Request) -> LlmRuntimeConfigResponse:
    if not feature_enabled(request, "feature_llm_runtime_config"):
        return LlmRuntimeConfigResponse(
            success=False,
            data=None,
            error={"code": "FEATURE_DISABLED", "message": "LLM runtime config feature is disabled", "details": None},
            meta=response_meta(),
        )
    store = request.app.state.services["llm_runtime_store"]
    config = LlmRuntimeConfig(**store.get())
    return LlmRuntimeConfigResponse(
        success=True,
        data=LlmRuntimeConfigData(config=config),
        error=None,
        meta=response_meta(),
    )


@router.patch("/llm/config", response_model=LlmRuntimeConfigResponse)
async def patch_llm_config(
    payload: LlmRuntimeConfigPatchRequest,
    request: Request,
) -> LlmRuntimeConfigResponse:
    if not feature_enabled(request, "feature_llm_runtime_config"):
        return LlmRuntimeConfigResponse(
            success=False,
            data=None,
            error={"code": "FEATURE_DISABLED", "message": "LLM runtime config feature is disabled", "details": None},
            meta=response_meta(),
        )
    actor_user = require_permission(request, "llm:config_manage")
    actor_role = ",".join(actor_user.roles)
    store = request.app.state.services["llm_runtime_store"]
    audit = request.app.state.services["audit_log_store"]
    update_kwargs = {}
    if "base_url" in payload.model_fields_set:
        update_kwargs["base_url"] = payload.base_url
    if "model" in payload.model_fields_set:
        update_kwargs["model"] = payload.model
    if "temperature" in payload.model_fields_set:
        update_kwargs["temperature"] = payload.temperature
    if "max_tokens" in payload.model_fields_set:
        update_kwargs["max_tokens"] = payload.max_tokens
    if "summary_max_tokens" in payload.model_fields_set:
        update_kwargs["summary_max_tokens"] = payload.summary_max_tokens
    if "summary_max_chars" in payload.model_fields_set:
        update_kwargs["summary_max_chars"] = payload.summary_max_chars
    if "summary_system_prompt" in payload.model_fields_set:
        update_kwargs["summary_system_prompt"] = payload.summary_system_prompt
    try:
        updated = store.update(**update_kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    config = LlmRuntimeConfig(**updated)
    audit.append(
        {
            "actor_role": actor_role,
            "action": "llm_runtime_patch",
            "path": str(request.url.path),
            "method": request.method,
            "status": "success",
            "details": {
                "base_url": payload.base_url,
                "model": payload.model,
                "temperature": payload.temperature,
                "max_tokens": payload.max_tokens,
                "summary_max_tokens": payload.summary_max_tokens,
                "summary_max_chars": payload.summary_max_chars,
                "summary_system_prompt": payload.summary_system_prompt,
            },
        }
    )
    return LlmRuntimeConfigResponse(
        success=True,
        data=LlmRuntimeConfigData(config=config),
        error=None,
        meta=response_meta(),
    )


@router.get("/llm/health", response_model=LlmHealthResponse)
async def llm_health(request: Request) -> LlmHealthResponse:
    if not feature_enabled(request, "feature_llm_runtime_config"):
        return LlmHealthResponse(
            success=False,
            data=None,
            error={"code": "FEATURE_DISABLED", "message": "LLM runtime config feature is disabled", "details": None},
            meta=response_meta(),
        )
    store = request.app.state.services["llm_runtime_store"]
    settings = request.app.state.settings
    data = await store.health(timeout_seconds=settings.request_timeout_seconds)
    return LlmHealthResponse(success=True, data=LlmHealthData(**data), error=None, meta=response_meta())


@router.post("/llm/test", response_model=LlmTestResponse)
async def llm_test(payload: LlmTestRequest, request: Request) -> LlmTestResponse:
    if not feature_enabled(request, "feature_llm_runtime_config"):
        return LlmTestResponse(
            success=False,
            data=None,
            error={"code": "FEATURE_DISABLED", "message": "LLM runtime config feature is disabled", "details": None},
            meta=response_meta(),
        )
    actor_user = require_permission(request, "llm:config_manage")
    actor_role = ",".join(actor_user.roles)
    store = request.app.state.services["llm_runtime_store"]
    settings = request.app.state.settings
    audit = request.app.state.services["audit_log_store"]
    data = await store.dry_run(prompt=payload.prompt, timeout_seconds=settings.request_timeout_seconds)
    audit.append(
        {
            "actor_role": actor_role,
            "action": "llm_test",
            "path": str(request.url.path),
            "method": request.method,
            "status": data["status"],
            "details": {"finish_reason": data["finish_reason"], "latency_ms": data["latency_ms"]},
        }
    )
    return LlmTestResponse(success=True, data=LlmTestData(**data), error=None, meta=response_meta())


@router.get("/ops/audit/logs", response_model=AuditLogResponse)
async def list_audit_logs(request: Request, limit: int = 100) -> AuditLogResponse:
    if not feature_enabled(request, "feature_ops_dashboard"):
        return AuditLogResponse(
            success=False,
            data=None,
            error={"code": "FEATURE_DISABLED", "message": "Ops dashboard feature is disabled", "details": None},
            meta=response_meta(),
        )
    require_role(request, "admin")
    store = request.app.state.services["audit_log_store"]
    events = [AuditLogItem(**item) for item in store.list_recent(limit=limit)]
    return AuditLogResponse(
        success=True,
        data=AuditLogData(events=events, total=len(events)),
        error=None,
        meta=response_meta(),
    )
