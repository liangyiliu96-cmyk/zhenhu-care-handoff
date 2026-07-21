"""集中管理所有环境变量配置，其他文件统一 from .config import ..."""
import os


def get_graph_mode() -> str:
    """返回当前 GRAPH_MODE: classic(默认) 或 stateful(Phase-2)。"""
    return os.getenv("GRAPH_MODE", "classic").strip().lower()


def validate_graph_mode_configuration() -> None:
    """Reject graph modes that cannot safely resume a clinical review in production."""
    mode = get_graph_mode()
    if mode not in {"classic", "stateful"}:
        raise RuntimeError(f"Unsupported GRAPH_MODE={mode!r}; expected 'classic' or 'stateful'.")
    if mode == "stateful":
        raise RuntimeError(
            "GRAPH_MODE=stateful is disabled until durable LangGraph interrupt/resume "
            "checkpoints are implemented. Use GRAPH_MODE=classic."
        )


def get_checkpoint_db() -> str:
    """返回 SqliteSaver db 路径; 空=MemorySaver。"""
    return os.getenv("LANGGRAPH_CHECKPOINT_DB", "")


def is_direct_discharge_enabled() -> bool:
    """Legacy direct-discharge execution is permanently disabled."""
    return False


def is_doctor_auto_approve() -> bool:
    """仅 APP_ENV != production 时允许自动批准医生审核。

    生产环境强制不可自动通过。
    """
    if os.getenv("APP_ENV", "") == "production":
        return False  # 生产环境强制不可自动通过
    return os.getenv("DOCTOR_AUTO_APPROVE", "true").lower() == "true"


def get_app_env() -> str:
    """返回部署环境: dev/staging/production。"""
    return os.getenv("APP_ENV", "dev")


def get_state_ttl() -> int:
    """返回 state_store TTL 秒数，默认 1800（30 分钟）。"""
    return int(os.getenv("STATE_TTL_SECONDS", "1800"))


# ============================================================================
# P1-2: 统一 AI provider 缓存 —— 从 5 个节点文件集中至此
# ============================================================================

from typing import Any as _Any


def get_cached_provider() -> _Any:
    """模块级缓存 AI provider 实例（全局唯一）。

    替换原来分散在 nodes_admission/nodes_clinical/nodes_handoff/nodes_monitoring/tools.py
    中各自独立的 _cached_provider() 副本。
    """
    from .llm_utils import get_provider_for_node

    return get_provider_for_node("default")
