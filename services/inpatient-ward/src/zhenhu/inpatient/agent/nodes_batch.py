"""批量评分节点 — 并行执行 padua/vte/news2/qsofa。
替代 graph.py 中 5 个串行节点，asyncio.gather 并行。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("zhenhu.batch_scoring")


async def node_batch_scoring(state: dict) -> dict:
    """并行执行全部评分节点。返回合并后的状态更新。"""
    from .nodes_scoring import node_padua_score, node_vte_prophylaxis, node_news2, node_qsofa

    async def safe_run(fn, name):
        try:
            return await fn(state)
        except Exception as e:
            logger.warning("batch_scoring[%s]: %s", name, e)
            return {}

    results = await asyncio.gather(
        safe_run(node_padua_score, "padua"),
        safe_run(node_vte_prophylaxis, "vte"),
        safe_run(node_news2, "news2"),
        safe_run(node_qsofa, "qsofa"),
    )

    merged: dict = {}
    for r in results:
        if r:
            merged.update(r)
    return merged
