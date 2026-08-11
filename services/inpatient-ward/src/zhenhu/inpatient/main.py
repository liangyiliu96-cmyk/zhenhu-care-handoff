"""住院协同 FastAPI 应用入口 —— 合并迁入。

挂载臻护共享中间件: RequestIdMiddleware + setup_error_handlers。
lifespan + async engine + 路由注册。

合并迁入修正A: 删除本地 middleware.py, 改用 zhenhu.contracts.middleware。
合并迁入修正A: 移除 app.config/app.db 依赖, 改用自包含 models。
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.middleware.trustedhost import TrustedHostMiddleware

# 合并迁入修正A: 使用共享 contracts 中间件, 不再引用本地 middleware.py
from zhenhu.contracts.middleware import RequestIdMiddleware, setup_error_handlers
from zhenhu.contracts import get_session as _contracts_get_session  # 阶段J审计修复
from zhenhu.contracts.agent import set_ai_provider
# 合并迁入修正: 路由导入改为相对路径
from .routes.admission import router as admission_router
from .routes.monitoring import router as monitoring_router
from .routes.discharge import router as discharge_router
from .routes.admin import router as admin_router
from .routes.review import router as review_router
from .routes.admission_clinical import router as admission_clinical_router
from .routes.dashboard import router as dashboard_router
from .routes.dashboard import timeline_router  # 方案4
from .routes.clinical_brief import router as clinical_brief_router
from .routes.agent_flow import router as agent_flow_router
from .routes.command import router as command_router
from .routes.discharge_summary import router as discharge_summary_router
from .routes.ward_overview import router as ward_router
from .routes.pending_reviews import router as pending_reviews_router
from .routes.nurse_board import router as nurse_router
from .routes.monitoring_overdue import router as overdue_router
from .routes.patients import router as patients_router
from .routes.rounds import router as rounds_router
from .routes.workflow_briefs import router as workflow_briefs_router
from .routes.doctor_copilot import router as doctor_copilot_router
from .routes.scores import router as scores_router
from .routes.query import router as query_router
from .routes.nursing import router as nursing_router
from .routes.clinical_note import router as clinical_note_router
from .routes.vital_trends import router as vital_trends_router
from .routes.lab_trends import router as lab_trends_router
from .routes.ward_priority import router as ward_priority_router
from .routes.rag_admin import router as rag_admin_router  # v0.3 知识库管理
from .routes.assistant import router as assistant_router  # v0.3 临床助手
from .routes.assistant_action_drafts import router as assistant_action_drafts_router
from .routes.care_management import router as care_management_router
from .routes.evidence import router as evidence_router
from .routes.evidence_graph import router as evidence_graph_router
from .routes.alerts import router as alerts_router
from .routes.follow_up_contact import router as follow_up_contact_router
from .routes.state_store import StateVersionConflictError
from .middleware.idempotency import IdempotencyMiddleware
from .services.api_contract import state_version_conflict_response, validate_unique_routes
from .services.observability import HTTPObservabilityMiddleware, configure_logging, http_metrics
from .services.transactional_state import TransactionalStateConflictError
from .middleware.auth import role_middleware, validate_auth_configuration
from .agent.config import validate_graph_mode_configuration

VERSION = os.environ.get("APP_VERSION", "0.3.0")

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://[::1]:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def cors_allowed_origins() -> list[str]:
    """Return explicit browser origins; wildcards are unsafe with credentials."""
    configured = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if not configured:
        return list(_DEFAULT_CORS_ORIGINS)
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]

# 结构化日志配置
configure_logging()
logger = logging.getLogger(__name__)

# DeepSeek remains the preferred provider. Local Ollama is an optional
# drafting-only fallback; rule nodes continue when neither provider is ready.
from .agent.llm_utils import get_provider_for_node, warm_ollama_fallback

set_ai_provider(get_provider_for_node("default"))
if os.environ.get("DEEPSEEK_API_KEY", ""):
    logger.info("DeepSeek primary provider configured; eligible nodes may fall back to Ollama")
else:
    logger.warning("DeepSeek is not configured; eligible LLM nodes will use Ollama when available, otherwise rules only")

# 合并迁入修正: SQLite 数据库引擎(移除 app.config.settings 依赖)
ASYNC_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./zhenhu_inpatient.db")

# 连接池配置：SQLite 用默认 NullPool，PostgreSQL/MySQL 启用连接池
_engine_kwargs: dict = {"echo": False}
if "sqlite" not in ASYNC_DATABASE_URL:
    _engine_kwargs.update({
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "3600")),
        "pool_pre_ping": True,
        "pool_timeout": 30,
    })

async_engine = create_async_engine(ASYNC_DATABASE_URL, **_engine_kwargs)
async_session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:  # 阶段J审计修复: 委托 contracts 统一实现
    """FastAPI Depends: 注入数据库会话 —— 阶段J审计修复。"""
    async for session in _contracts_get_session(async_session_factory):
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期：启动建表 → 关闭释放连接。"""
    from .services.schema_migrations import run_schema_migrations

    await run_schema_migrations(async_engine)

    # 启动种子: 病种模板/组织架构/科室护理清单表为预留结构, 此处幂等同步 (管理端与护理功能依赖)
    try:
        from .routes.state_store import seed_disease_templates, seed_org_from_json, seed_checklists_from_dict
        seed_disease_templates()
        seed_org_from_json()
        seed_checklists_from_dict()
    except Exception:
        logger.exception("seed failed")

    async def outbox_delivery_worker() -> None:
        from .agent.outbox import deliver_pending_outbox_events

        interval = max(1, int(os.environ.get("OUTBOX_RETRY_INTERVAL_SECONDS", "15")))
        while True:
            try:
                await deliver_pending_outbox_events()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("outbox delivery cycle failed")
            await asyncio.sleep(interval)

    outbox_worker = asyncio.create_task(outbox_delivery_worker(), name="fhir-outbox-delivery")
    ollama_warmup_worker = asyncio.create_task(warm_ollama_fallback(), name="ollama-fallback-warmup")

    async def ensure_rag_index_worker() -> None:
        """Repair a missing or partial Milvus index without delaying service readiness."""
        try:
            from .agent.rag_engine import LAYERS, _c, collection_row_count, expected_document_counts, index_all

            expected = await run_in_threadpool(expected_document_counts)

            def index_is_incomplete() -> bool:
                client = _c()
                return any(
                    not client.has_collection(collection)
                    or collection_row_count(collection) < expected.get(layer, 0)
                    for layer, collection in LAYERS.items()
                )

            if await run_in_threadpool(index_is_incomplete):
                logger.info("RAG index is incomplete; rebuilding in the background")
                result = await run_in_threadpool(index_all)
                logger.info("RAG background rebuild completed: %d documents", sum(result.values()))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("RAG background index initialization skipped: %s", exc)

    rag_index_worker = asyncio.create_task(ensure_rag_index_worker(), name="rag-index-initialization")

    # startup: 输出路由表
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            logger.info("Route: %s %s", route.methods, route.path)

    logger.info("inpatient-ward started")

    yield

    # 优雅关闭：P0-2 state_store 清理线程
    from .routes.state_store import stop_cleanup_thread
    stop_cleanup_thread()
    outbox_worker.cancel()
    if not ollama_warmup_worker.done():
        ollama_warmup_worker.cancel()
    if not rag_index_worker.done():
        rag_index_worker.cancel()
    try:
        await outbox_worker
    except asyncio.CancelledError:
        pass
    try:
        await ollama_warmup_worker
    except asyncio.CancelledError:
        pass
    try:
        await rag_index_worker
    except asyncio.CancelledError:
        pass
    await async_engine.dispose()
    from .services.evidence_graph import close_evidence_graph
    close_evidence_graph()
    logger.info("inpatient-ward stopped")


app = FastAPI(
    title="臻护住院协同",
    description="通用住院协同模块 —— 病种模板化 + Agent 编排",
    version="0.3.0",
    lifespan=lifespan,
)

validate_auth_configuration()
validate_graph_mode_configuration()
if os.environ.get("APP_ENV", "dev").lower() == "production" and "sqlite" in ASYNC_DATABASE_URL:
    raise RuntimeError("Production requires a durable non-SQLite DATABASE_URL for audit and clinical records.")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip 压缩中间件
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 臻护请求 ID 中间件（透传/注入 X-Request-ID）
app.add_middleware(HTTPObservabilityMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(IdempotencyMiddleware)

# 臻护统一错误处理
setup_error_handlers(app)


@app.exception_handler(StateVersionConflictError)
async def handle_state_version_conflict(request: Request, exc: StateVersionConflictError) -> JSONResponse:
    """Expose database CAS conflicts consistently to every clinical write route."""
    current_version = 0
    try:
        from .routes.state_store import get_state

        current_state = get_state(str(exc.args[0])) if exc.args else None
        current_version = int((current_state or {}).get("state_version", 0))
    except (TypeError, ValueError, IndexError):
        pass
    return state_version_conflict_response(
        current_version=current_version,
        request_id=getattr(request.state, "request_id", None),
    )


@app.exception_handler(TransactionalStateConflictError)
async def handle_transactional_state_conflict(
    request: Request,
    exc: TransactionalStateConflictError,
) -> JSONResponse:
    """Return the same CAS response for the authoritative transactional state."""
    return state_version_conflict_response(
        current_version=exc.current_version,
        request_id=getattr(request.state, "request_id", None),
    )

# v1.3 §十四: 角色中间件（x-role: doctor|nurse）
app.middleware("http")(role_middleware)

# TrustedHost 中间件（生产环境用，开发环境可通过环境变量关闭）
allowed_hosts = os.environ.get("ALLOWED_HOSTS", "*")
if allowed_hosts != "*":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts.split(","),
    )

# 注册路由
# ── 临床核心 ──
app.include_router(admission_router)
app.include_router(monitoring_router)
app.include_router(discharge_router)
app.include_router(admin_router)
# ── 医生面板 ──
app.include_router(review_router)
app.include_router(admission_clinical_router)
app.include_router(dashboard_router)
app.include_router(timeline_router)  # 方案4
app.include_router(clinical_brief_router)
app.include_router(agent_flow_router)
from .routes.cds_hooks import router as cds_hooks_router  # CDS Hooks 标准
app.include_router(cds_hooks_router)
app.include_router(command_router)
app.include_router(discharge_summary_router)
# ── 病区总览 ──
app.include_router(ward_router)
app.include_router(pending_reviews_router)
app.include_router(nurse_router)
app.include_router(overdue_router)
app.include_router(patients_router)
app.include_router(rounds_router)
app.include_router(workflow_briefs_router)
app.include_router(doctor_copilot_router)
# ── 评分与查询 ──
app.include_router(scores_router)
app.include_router(query_router)
# ── 护理与临床文书 ──
app.include_router(nursing_router)
app.include_router(clinical_note_router)
# ── 趋势分析 ──
app.include_router(vital_trends_router)
app.include_router(lab_trends_router)
app.include_router(ward_priority_router)
app.include_router(rag_admin_router)  # v0.3 知识库管理面板
app.include_router(assistant_router)  # v0.3 临床智能助手
app.include_router(assistant_action_drafts_router)
app.include_router(care_management_router)
app.include_router(evidence_router)
app.include_router(evidence_graph_router)
app.include_router(alerts_router)
app.include_router(follow_up_contact_router)

# Versioned aliases are additive: existing frontend clients keep their original paths.
app.include_router(admission_router, prefix="/v1")
app.include_router(monitoring_router, prefix="/v1")
app.include_router(discharge_router, prefix="/v1")
app.include_router(review_router, prefix="/v1")
app.include_router(admission_clinical_router, prefix="/v1")
app.include_router(command_router, prefix="/v1")
app.include_router(clinical_brief_router, prefix="/v1")
app.include_router(agent_flow_router, prefix="/v1")
app.include_router(patients_router, prefix="/v1")
app.include_router(rounds_router, prefix="/v1")
app.include_router(workflow_briefs_router, prefix="/v1")
app.include_router(doctor_copilot_router, prefix="/v1")
app.include_router(scores_router, prefix="/v1")
app.include_router(care_management_router, prefix="/v1")
app.include_router(assistant_action_drafts_router, prefix="/v1")
app.include_router(evidence_router, prefix="/v1")
app.include_router(alerts_router, prefix="/v1")
validate_unique_routes(app)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Liveness probe that does not depend on external services."""
    return {
        "status": "ok",
        "service": "inpatient-ward",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["system"])
async def readiness_check() -> JSONResponse:
    """Readiness probe for the transactional database and state-store backend."""
    from .routes.state_store import get_backend_health

    checks: dict[str, object] = {}
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["transactional_database"] = "ok"
    except Exception:
        logger.exception("readiness transactional database check failed")
        checks["transactional_database"] = "unavailable"

    try:
        checks["state_store"] = {"status": "ok", **get_backend_health()}
    except Exception:
        logger.exception("readiness state-store check failed")
        checks["state_store"] = {"status": "unavailable"}

    ready = checks["transactional_database"] == "ok" and checks["state_store"].get("status") == "ok"
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "unavailable", "checks": checks},
    )


# ── Prometheus metrics 端点 ──
from zhenhu.inpatient.agent.metrics import get_metrics
from .routes.state_store import get_backend_health, get_store_size
from .agent.llm_utils import get_llm_metrics  # P2-1


@app.get("/metrics", tags=["system"])
async def metrics():
    from fastapi.responses import PlainTextResponse
    base = get_metrics()
    base += http_metrics.render_prometheus()
    base += f"\n# P0-2 state_store\nzhenhu_state_store_entries {get_store_size()}\n"
    try:
        state_health = get_backend_health()
        backend = state_health["backend"]
        base += (
            "# HELP zhenhu_state_store_up Durable state-store backend availability.\n"
            "# TYPE zhenhu_state_store_up gauge\n"
            f'zhenhu_state_store_up{{backend="{backend}"}} 1\n'
            "# HELP zhenhu_state_store_file_bytes SQLite state-store file size; zero for MySQL.\n"
            "# TYPE zhenhu_state_store_file_bytes gauge\n"
            f'zhenhu_state_store_file_bytes{{backend="{backend}"}} {state_health["file_size_bytes"]}\n'
        )
    except Exception:
        logger.exception("state-store metrics probe failed")
        base += "# HELP zhenhu_state_store_up Durable state-store backend availability.\n"
        base += "# TYPE zhenhu_state_store_up gauge\n"
        base += "zhenhu_state_store_up 0\n"
    # P2-1: LLM 成本追踪
    llm = get_llm_metrics()
    if llm["total_calls"] > 0:
        avg_lat = llm["total_latency_ms"] / max(llm["total_calls"], 1)
        tok_est = (llm["total_prompt_chars"] + llm["total_response_chars"]) // 4
        base += (
            f"\n# P2-1 LLM cost tracking\n"
            f"zhenhu_llm_calls_total {llm['total_calls']}\n"
            f"zhenhu_llm_calls_success {llm['success']}\n"
            f"zhenhu_llm_calls_cache_hits {llm['cache_hits']}\n"
            f"zhenhu_llm_calls_timeouts {llm['timeouts']}\n"
            f"zhenhu_llm_calls_errors {llm['errors']}\n"
            f"zhenhu_llm_avg_latency_ms {avg_lat:.1f}\n"
            f"zhenhu_llm_total_prompt_chars {llm['total_prompt_chars']}\n"
            f"zhenhu_llm_total_response_chars {llm['total_response_chars']}\n"
            f"zhenhu_llm_estimated_tokens {tok_est}\n"
        )
    return PlainTextResponse(base)
#
