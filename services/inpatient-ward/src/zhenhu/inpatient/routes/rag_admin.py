"""RAG 知识库管理路由 — 管理端专用。

提供知识库全生命周期管理: 浏览/搜索/增删改查/索引/验证/备份。
建议由临床知识管理员(如科室质控护士或临床药师)定期维护。
"""

import re
import time

from fastapi import APIRouter, Request, HTTPException
from starlette.concurrency import run_in_threadpool

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/admin/rag", tags=["rag-admin"])


@router.get("/dashboard")
async def rag_dashboard():
    """知识库管理仪表盘 — 全景视图。"""
    from ..agent.rag_engine import _c, LAYERS, collection_row_count, expected_document_counts, rag_runtime_status
    import time
    client = _c()

    layers = {}
    issues = []
    total = 0
    try:
        expected = expected_document_counts()
    except Exception as exc:
        expected = {}
        issues.append(f"知识源校验失败: {exc}")

    for layer, coll_name in LAYERS.items():
        try:
            actual = collection_row_count(coll_name) if client.has_collection(coll_name) else 0
            exp = expected.get(layer, 0)
            layers[layer] = {
                "collection": coll_name,
                "expected": exp,
                "actual": actual,
                "health": "ok" if actual >= exp else ("incomplete" if actual > 0 else "missing"),
                "category": _layer_category(layer),
            }
            total += actual
            if actual < exp:
                issues.append(f"{layer}({coll_name}): {actual}/{exp}")
        except Exception as e:
            layers[layer] = {"health": "error", "error": str(e)}
            issues.append(f"{layer}: {e}")

    runtime = rag_runtime_status()
    last_reindex = runtime.get("last_reindex") or {}
    last_indexed = last_reindex.get("indexed_at") if isinstance(last_reindex, dict) else None
    return UnifiedResponse(data={
        "total_documents": total,
        "total_layers": len(LAYERS),
        "layers": layers,
        "issues": issues,
        "needs_attention": len(issues) > 0,
        "last_indexed": time.strftime("%Y-%m-%d %H:%M", time.localtime(last_indexed)) if last_indexed else None,
        "runtime": runtime,
    })


def _layer_category(layer: str) -> str:
    cats = {"L1":"评分","L2":"疾病","L3":"模板","L4":"护理","L5":"用药",
            "L6":"检验","L7":"急症","L8":"操作","L9":"患教",
            "L10":"外科","L11":"剂量","L12":"感控","L13":"营养","L14":"妇产"}
    return cats.get(layer, "其他")


@router.get("/entries")
async def list_entries(layer: str | None = None, search: str = "", page: int = 1, page_size: int = 50):
    """按层或关键词搜索知识条目。"""
    from ..agent.rag_engine import _c, LAYERS, collection_row_count
    client = _c()
    results = {}
    normalized_search = search.strip().casefold()
    search_terms = [
        (quoted or bare).casefold()
        for quoted, bare in re.findall(r'"([^"]+)"|(\S+)', normalized_search)
        if quoted or bare
    ]
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 100))
    page_offset = (safe_page - 1) * safe_page_size

    if layer and layer in LAYERS:
        layers_to_search = {layer: LAYERS[layer]}
    elif layer:
        return UnifiedResponse(data={"error": f"无效层级: {layer}"})
    else:
        layers_to_search = LAYERS

    for lk, coll_name in layers_to_search.items():
        try:
            # Milvus expressions are not a safe place for raw user text. Fetch the
            # bounded layer content and apply the multi-field search in Python.
            collection_size = max(0, collection_row_count(coll_name))
            candidate_limit = max(safe_page * safe_page_size, min(collection_size, 5_000))
            res = client.query(
                coll_name,
                filter='source != ""',
                output_fields=["source","category","topic","disease_id","department","text","indexed_at"],
                limit=candidate_limit,
                offset=0,
            )
            items = []
            for r in res:
                item = {
                    "id": r.get("id", ""),
                    "topic": r.get("topic", ""),
                    "category": _layer_category(lk),
                    "disease_id": r.get("disease_id", ""),
                    "department": r.get("department", ""),
                    "text": (r.get("text", "") or "")[:300],
                    "indexed_at": r.get("indexed_at", ""),
                }
                searchable = " ".join(str(r.get(field, "") or "") for field in (
                    "topic", "text", "source", "category", "disease_id", "department"
                )).casefold()
                if not search_terms or all(term in searchable for term in search_terms):
                    items.append(item)
            paged_items = items[page_offset:page_offset + safe_page_size]
            results[lk] = {
                "collection": coll_name,
                "count": len(items),
                "items": paged_items,
            }
        except Exception as e:
            results[lk] = {"error": str(e)}

    failed_layers = [layer_key for layer_key, value in results.items() if value.get("error")]
    return UnifiedResponse(data={
        "layers": results,
        "search": search.strip(),
        "page": safe_page,
        "page_size": safe_page_size,
        "failed_layers": failed_layers,
    })


@router.post("/reindex")
async def reindex_knowledge(request: Request, layers: str = ""):
    """重新索引指定层或全部知识库。layers=L1,L5 或 empty=全部。"""
    from ..services.management_access import require_management_operation
    require_management_operation(request, "rag_reindex")
    from ..agent.rag_engine import LAYERS, RagIndexError, index_all
    requested_layers = [layer.strip().upper() for layer in layers.split(",") if layer.strip()]
    invalid_layers = sorted(set(requested_layers) - set(LAYERS))
    if invalid_layers:
        raise HTTPException(status_code=422, detail={"message": "包含未知知识层", "invalid_layers": invalid_layers})
    try:
        result = await run_in_threadpool(index_all, requested_layers or None)
    except RagIndexError as exc:
        raise HTTPException(status_code=422, detail={"message": "知识源校验失败", "error": str(exc)}) from exc
    except Exception as exc:
        # Do not turn a Milvus/model failure into an opaque 500 for operators.
        raise HTTPException(status_code=503, detail={"message": "知识索引服务重建失败", "error": str(exc)}) from exc
    from ..agent.audit import write_management_audit_event
    audit_id = await write_management_audit_event(action_type="rag_reindexed", detail={"requested_layers": requested_layers or list(LAYERS), "indexed": result}, request=request)
    return UnifiedResponse(data={"indexed": result, "total": sum(result.values()), "audit_id": audit_id})


@router.get("/diagnostics")
async def rag_diagnostics(request: Request):
    """Manager-only operational diagnostics without exposing source content."""
    from ..services.management_access import require_management_operation

    require_management_operation(request, "rag_reindex", write=False)
    from ..agent.rag_engine import LAYERS, collection_row_count, expected_document_counts, rag_runtime_status

    expected = expected_document_counts()
    rows = {}
    for layer, collection in LAYERS.items():
        try:
            rows[layer] = {"expected": expected.get(layer, 0), "actual": collection_row_count(collection)}
        except Exception as exc:
            rows[layer] = {"expected": expected.get(layer, 0), "actual": 0, "error": str(exc)}
    return UnifiedResponse(data={"runtime": rag_runtime_status(), "layers": rows, "total_expected": sum(expected.values())})


@router.get("/preview")
async def preview_retrieval(request: Request, query: str, layers: str = "", top_k: int = 5):
    """Run the actual semantic retrieval path for knowledge governance QA."""
    from ..services.management_access import require_management_operation

    require_management_operation(request, "rag_reindex", write=False)
    from ..agent.rag_engine import LAYERS, rag_runtime_status, search

    selected_layers = [item.strip().upper() for item in layers.split(",") if item.strip()]
    invalid_layers = sorted(set(selected_layers) - set(LAYERS))
    if invalid_layers:
        raise HTTPException(status_code=422, detail={"message": "包含未知知识层", "invalid_layers": invalid_layers})
    started = time.perf_counter()
    results = await search(query, layer=selected_layers or None, top_k=max(1, min(top_k, 10)))
    return UnifiedResponse(data={
        "query": query,
        "layers": selected_layers or list(LAYERS),
        "results": results,
        "count": len(results),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "index_revision": rag_runtime_status()["index_revision"],
    })


@router.get("/maintenance-log")
async def maintenance_log():
    """维护建议 — 基于知识库状态生成维护任务。"""
    from ..agent.rag_engine import _c, LAYERS
    import os, time

    tasks = []

    # 检查源文件更新时间
    source_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "config", "clinical_knowledge.json"
    )
    source_path = os.path.abspath(source_path)
    if os.path.exists(source_path):
        source_mtime = os.path.getmtime(source_path)
        days_since = (time.time() - source_mtime) / 86400
        if days_since > 30:
            tasks.append({
                "priority": "high",
                "task": "知识源文件超过30天未更新",
                "detail": f"config/clinical_knowledge.json 最后修改于 {days_since:.0f} 天前",
                "action": "检查是否有新指南或证据需要更新",
            })
        else:
            tasks.append({
                "priority": "low",
                "task": "知识源文件状态正常",
                "detail": f"最后更新 {days_since:.0f} 天前",
                "action": "无需操作",
            })

    # 检查索引一致性
    expected = {"L1":6,"L2":18,"L3":18,"L4":12,"L5":16,"L6":15,"L7":8,"L8":8,
                "L9":6,"L10":5,"L11":6,"L12":4,"L13":3,"L14":2}
    client = _c()
    for layer, coll_name in LAYERS.items():
        try:
            actual = collection_row_count(coll_name) if client.has_collection(coll_name) else 0
            exp = expected.get(layer, 0)
            if actual < exp:
                tasks.append({
                    "priority": "high",
                    "task": f"L{layer} ({coll_name}) 索引不完整",
                    "detail": f"期望 {exp} 条, 实际 {actual} 条",
                    "action": f"POST /admin/rag/reindex 重新索引",
                })
        except Exception:
            pass

    # 维护建议
    tasks.append({"priority": "info", "task": "建议维护频率", "detail": "每月检查一次临床知识更新", "action": "由临床知识管理员执行"})
    tasks.append({"priority": "info", "task": "建议维护人员", "detail": "科室质控护士或临床药师", "action": "具备临床背景, 可判断知识准确性"})

    return UnifiedResponse(data={"tasks": tasks, "source_file": source_path})
