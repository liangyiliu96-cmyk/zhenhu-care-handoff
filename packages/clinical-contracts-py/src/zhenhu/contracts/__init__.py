"""共享临床契约：病例、知识、入库任务状态机与最小角色访问边界。

该包是正式项目与 PoC 共同引用的唯一状态机事实来源，
不允许在调用方各自硬编码状态转移。
状态定义对照《需求规格说明书 v0.2》§3.4（病例状态机）与 §4.4（知识版本状态）。
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet


# ============================================================================
# 状态枚举
# ============================================================================


class CaseState(str, Enum):
    """病例状态 —— 对照需求 §3.4 病例状态机。"""

    DRAFT = "draft"
    ANALYSING = "analysing"
    REVIEW_PENDING = "review_pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    TASK_DRAFT = "task_draft"
    SIMULATED_PUBLISHED = "simulated_published"
    KNOWLEDGE_CHANGED = "knowledge_changed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class KnowledgeDocumentState(str, Enum):
    """知识版本状态 —— 对照需求 §4.4 知识版本状态。"""

    REVIEW_PENDING = "review_pending"
    PUBLISHED = "published"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    REVIEW_REJECTED = "review_rejected"


class KnowledgeIngestionJobState(str, Enum):
    """知识入库任务状态。"""

    QUEUED = "queued"
    PARSING = "parsing"
    REVIEW_PENDING = "review_pending"
    FAILED = "failed"


class ClinicalRole(str, Enum):
    """临床角色枚举 —— 对照需求 §3.2 角色边界。"""

    DOCTOR = "doctor"
    NURSE = "nurse"
    CASE_MANAGER = "case_manager"
    AUDITOR = "auditor"
    KNOWLEDGE_ADMIN = "knowledge_admin"


class Surface(str, Enum):
    """功能表面枚举 —— 角色-权限映射的键。"""

    CASE_REVIEW = "case_review"
    SIMULATED_TASKS = "simulated_tasks"
    KNOWLEDGE_DOCUMENTS = "knowledge_documents"
    KNOWLEDGE_IMPORT = "knowledge_import"
    KNOWLEDGE_RUNTIME_RESET = "knowledge_runtime_reset"


# ============================================================================
# 状态转移表
# ============================================================================


CASE_TRANSITIONS: dict[CaseState, FrozenSet[CaseState]] = {
    CaseState.DRAFT: frozenset({CaseState.ANALYSING, CaseState.CANCELLED}),
    CaseState.ANALYSING: frozenset({
        CaseState.REVIEW_PENDING,
        CaseState.FAILED,
        CaseState.CANCELLED,
    }),
    CaseState.REVIEW_PENDING: frozenset({
        CaseState.CONFIRMED,
        CaseState.REJECTED,
        CaseState.TASK_DRAFT,
        CaseState.CANCELLED,
        CaseState.KNOWLEDGE_CHANGED,
    }),
    CaseState.CONFIRMED: frozenset({CaseState.TASK_DRAFT, CaseState.CANCELLED}),
    CaseState.REJECTED: frozenset({CaseState.TASK_DRAFT, CaseState.CANCELLED}),
    CaseState.TASK_DRAFT: frozenset({
        CaseState.SIMULATED_PUBLISHED,
        CaseState.REVIEW_PENDING,
        CaseState.CANCELLED,
        CaseState.KNOWLEDGE_CHANGED,
    }),
    CaseState.SIMULATED_PUBLISHED: frozenset({CaseState.CLOSED, CaseState.CANCELLED}),
    CaseState.KNOWLEDGE_CHANGED: frozenset({CaseState.REVIEW_PENDING, CaseState.CANCELLED}),
    CaseState.FAILED: frozenset({CaseState.ANALYSING}),
    CaseState.CANCELLED: frozenset(),
    CaseState.CLOSED: frozenset(),
}


KNOWLEDGE_TRANSITIONS: dict[KnowledgeDocumentState, FrozenSet[KnowledgeDocumentState]] = {
    KnowledgeDocumentState.REVIEW_PENDING: frozenset({
        KnowledgeDocumentState.PUBLISHED,
        KnowledgeDocumentState.WITHDRAWN,
        KnowledgeDocumentState.REVIEW_REJECTED,
    }),
    KnowledgeDocumentState.PUBLISHED: frozenset({
        KnowledgeDocumentState.EXPIRED,
        KnowledgeDocumentState.WITHDRAWN,
        KnowledgeDocumentState.SUPERSEDED,
        KnowledgeDocumentState.ARCHIVED,
    }),
    KnowledgeDocumentState.EXPIRED: frozenset(),
    KnowledgeDocumentState.WITHDRAWN: frozenset(),
    KnowledgeDocumentState.SUPERSEDED: frozenset(),
    KnowledgeDocumentState.ARCHIVED: frozenset(),
    KnowledgeDocumentState.REVIEW_REJECTED: frozenset(),
}


INGESTION_JOB_TRANSITIONS: dict[
    KnowledgeIngestionJobState, FrozenSet[KnowledgeIngestionJobState]
] = {
    KnowledgeIngestionJobState.QUEUED: frozenset({KnowledgeIngestionJobState.PARSING}),
    KnowledgeIngestionJobState.PARSING: frozenset({
        KnowledgeIngestionJobState.REVIEW_PENDING,
        KnowledgeIngestionJobState.FAILED,
    }),
    KnowledgeIngestionJobState.REVIEW_PENDING: frozenset(),
    KnowledgeIngestionJobState.FAILED: frozenset({KnowledgeIngestionJobState.QUEUED}),
}


# ============================================================================
# 衍生常量
# ============================================================================

CASE_STATES: tuple[CaseState, ...] = tuple(CaseState)
KNOWLEDGE_DOCUMENT_STATES: tuple[KnowledgeDocumentState, ...] = tuple(KnowledgeDocumentState)
KNOWLEDGE_INGESTION_JOB_STATES: tuple[KnowledgeIngestionJobState, ...] = (
    tuple(KnowledgeIngestionJobState)
)

# knowledge_changed 仅作为在办病例的阻断态：当其所引用的已发布知识过期/撤回/被替代时进入，
# 须由医生重新检索与人工复核后才能回到 review_pending。见需求 §4.4 末段。
CASE_BLOCKING_STATES: FrozenSet[CaseState] = frozenset({
    CaseState.KNOWLEDGE_CHANGED,
    CaseState.FAILED,
    CaseState.CANCELLED,
    CaseState.CLOSED,
})

# 知识版本终态集合：进入后不可再转移
KNOWLEDGE_TERMINAL_STATES: FrozenSet[KnowledgeDocumentState] = frozenset({
    KnowledgeDocumentState.EXPIRED,
    KnowledgeDocumentState.WITHDRAWN,
    KnowledgeDocumentState.SUPERSEDED,
    KnowledgeDocumentState.ARCHIVED,
    KnowledgeDocumentState.REVIEW_REJECTED,
})

CLINICAL_ROLES: tuple[ClinicalRole, ...] = tuple(ClinicalRole)

# 角色 → 允许访问的表面
SURFACE_PERMISSIONS: dict[Surface, FrozenSet[ClinicalRole]] = {
    Surface.CASE_REVIEW: frozenset({ClinicalRole.DOCTOR, ClinicalRole.AUDITOR}),
    Surface.SIMULATED_TASKS: frozenset({
        ClinicalRole.DOCTOR,
        ClinicalRole.NURSE,
        ClinicalRole.CASE_MANAGER,
    }),
    Surface.KNOWLEDGE_DOCUMENTS: frozenset({
        ClinicalRole.DOCTOR,
        ClinicalRole.AUDITOR,
        ClinicalRole.KNOWLEDGE_ADMIN,
    }),
    Surface.KNOWLEDGE_IMPORT: frozenset({ClinicalRole.KNOWLEDGE_ADMIN}),
    Surface.KNOWLEDGE_RUNTIME_RESET: frozenset({ClinicalRole.KNOWLEDGE_ADMIN}),
}


# ============================================================================
# 断言函数
# ============================================================================


class ContractError(Exception):
    """契约断言失败时抛出的异常。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _is_allowed_transition(
    graph: dict,
    current_state: CaseState | KnowledgeDocumentState | KnowledgeIngestionJobState,
    next_state: CaseState | KnowledgeDocumentState | KnowledgeIngestionJobState,
) -> bool:
    """通用转移判定：检查 next_state 是否在 current_state 的可达集合中。"""
    allowed: FrozenSet | None = graph.get(current_state)
    return allowed is not None and next_state in allowed


def assert_case_transition(
    current_state: CaseState | str,
    next_state: CaseState | str,
) -> bool:
    """断言病例状态转移合法。

    Args:
        current_state: 当前病例状态（枚举值或字符串）。
        next_state: 目标病例状态（枚举值或字符串）。

    Returns:
        True 表示转移合法。

    Raises:
        ContractError: 当状态未知或转移不合法时。
    """
    cur = CaseState(current_state) if isinstance(current_state, str) else current_state
    nxt = CaseState(next_state) if isinstance(next_state, str) else next_state

    if cur not in CASE_TRANSITIONS:
        raise ContractError(f"Unknown case state: {cur.value}")
    if not _is_allowed_transition(CASE_TRANSITIONS, cur, nxt):
        raise ContractError(f"Illegal case transition: {cur.value} -> {nxt.value}")
    return True


def assert_knowledge_transition(
    current_state: KnowledgeDocumentState | str,
    next_state: KnowledgeDocumentState | str,
) -> bool:
    """断言知识版本状态转移合法。

    Args:
        current_state: 当前知识版本状态。
        next_state: 目标知识版本状态。

    Returns:
        True 表示转移合法。

    Raises:
        ContractError: 当状态未知或转移不合法时。
    """
    cur = (
        KnowledgeDocumentState(current_state)
        if isinstance(current_state, str)
        else current_state
    )
    nxt = (
        KnowledgeDocumentState(next_state)
        if isinstance(next_state, str)
        else next_state
    )

    if cur not in KNOWLEDGE_TRANSITIONS:
        raise ContractError(f"Unknown knowledge state: {cur.value}")
    if not _is_allowed_transition(KNOWLEDGE_TRANSITIONS, cur, nxt):
        raise ContractError(f"Illegal knowledge transition: {cur.value} -> {nxt.value}")
    return True


def assert_ingestion_job_transition(
    current_state: KnowledgeIngestionJobState | str,
    next_state: KnowledgeIngestionJobState | str,
) -> bool:
    """断言知识入库任务状态转移合法。

    Args:
        current_state: 当前入库任务状态。
        next_state: 目标入库任务状态。

    Returns:
        True 表示转移合法。

    Raises:
        ContractError: 当状态未知或转移不合法时。
    """
    cur = (
        KnowledgeIngestionJobState(current_state)
        if isinstance(current_state, str)
        else current_state
    )
    nxt = (
        KnowledgeIngestionJobState(next_state)
        if isinstance(next_state, str)
        else next_state
    )

    if cur not in INGESTION_JOB_TRANSITIONS:
        raise ContractError(f"Unknown ingestion job state: {cur.value}")
    if not _is_allowed_transition(INGESTION_JOB_TRANSITIONS, cur, nxt):
        raise ContractError(
            f"Illegal ingestion job transition: {cur.value} -> {nxt.value}"
        )
    return True


def can_role_access_surface(role: ClinicalRole | str, surface: Surface | str) -> bool:
    """检查角色是否有权访问指定功能表面。

    Args:
        role: 临床角色。
        surface: 功能表面。

    Returns:
        True 表示有权访问。
    """
    r = ClinicalRole(role) if isinstance(role, str) else role
    s = Surface(surface) if isinstance(surface, str) else surface
    return r in SURFACE_PERMISSIONS.get(s, frozenset())


def assert_role_access(role: ClinicalRole | str, surface: Surface | str) -> bool:
    """断言角色有权访问指定功能表面。

    Args:
        role: 临床角色。
        surface: 功能表面。

    Returns:
        True 表示有权访问。

    Raises:
        ContractError: 当角色未知或无权访问时。
    """
    r = ClinicalRole(role) if isinstance(role, str) else role
    s = Surface(surface) if isinstance(surface, str) else surface

    if not can_role_access_surface(r, s):
        raise ContractError(f"Role {r.value} cannot access {s.value}")
    return True


# ============================================================================
# 快照导出
# ============================================================================


def build_contract_snapshot() -> dict:
    """导出可序列化的契约快照，用于运行时校验与调试。

    Returns:
        dict: 包含所有状态列表、阻断态集合和功能表面列表。
    """
    return {
        "case_states": [s.value for s in CASE_STATES],
        "knowledge_states": [s.value for s in KNOWLEDGE_DOCUMENT_STATES],
        "ingestion_job_states": [s.value for s in KNOWLEDGE_INGESTION_JOB_STATES],
        "blocking_case_states": [s.value for s in CASE_BLOCKING_STATES],
        "knowledge_terminal_states": [s.value for s in KNOWLEDGE_TERMINAL_STATES],
        "surfaces": [s.value for s in Surface],
        "version": "0.2.0",
    }


# ============================================================================
# 公开 API
# ============================================================================

__all__ = [
    # 枚举
    "CaseState",
    "KnowledgeDocumentState",
    "KnowledgeIngestionJobState",
    "ClinicalRole",
    "Surface",
    # 转移表
    "CASE_TRANSITIONS",
    "KNOWLEDGE_TRANSITIONS",
    "INGESTION_JOB_TRANSITIONS",
    # 状态集合
    "CASE_STATES",
    "KNOWLEDGE_DOCUMENT_STATES",
    "KNOWLEDGE_INGESTION_JOB_STATES",
    "CASE_BLOCKING_STATES",
    "KNOWLEDGE_TERMINAL_STATES",
    "CLINICAL_ROLES",
    # 权限映射
    "SURFACE_PERMISSIONS",
    # 断言函数
    "ContractError",
    "assert_case_transition",
    "assert_knowledge_transition",
    "assert_ingestion_job_transition",
    "can_role_access_surface",
    "assert_role_access",
    # 快照
    "build_contract_snapshot",
]
