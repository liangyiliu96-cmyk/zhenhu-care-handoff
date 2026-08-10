"""管理路由 —— 阶段D: 病种模板管理、系统状态等管理功能。合并迁入。

提供 GET /inpatient/templates 列出所有可用病种模板(JSON 配置化)。
提供 POST /inpatient/fixtures/load/{patient_key} 一键加载预置患者并执行完整入院→出院流程。
"""
import json
import logging
import os
import time as _time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..schemas import UnifiedResponse
from .demo_patient_pack import DEMO_DEPARTMENTS, DEMO_PACK_VERSION, LEGACY_DEMO_PATIENT_IDS, build_demo_patient_states
from .patient_fixtures import DASHBOARD_CARE_FIXTURE_ID, PATIENTS, build_dashboard_care_fixture

logger = logging.getLogger("zhenhu.admin")

# 合并迁入: 直接引用 disease_templates 目录, 不依赖 app.domain.templates
_TEMPLATE_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "disease_templates")).resolve()

router = APIRouter(prefix="/inpatient", tags=["admin"])


@router.get("/whoami")
async def get_whoami(request: Request):
    """当前登录用户身份 — 读取 request.state.user_info (由 auth middleware 注入)。"""
    user = getattr(request.state, "user_info", {"role": "doctor", "title": "医生"})
    return UnifiedResponse(data=user)


@router.get("/admin-capabilities")
async def get_admin_capabilities(request: Request):
    from ..services.management_access import management_capabilities

    return UnifiedResponse(data=management_capabilities(request))


# ── v0.4: 工号+密码登录 ──

class LoginRequest(BaseModel):
    job_number: str = Field(..., min_length=1, max_length=32, description="工号, 如 D-XN-001")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class DemoPatientResetRequest(BaseModel):
    confirmed: bool = Field(..., description="Explicit confirmation for replacing fictional demo patients")
    purge_runtime: bool = Field(default=False, description="Development-only removal of all historical patient runtime states")


_DEV_SHORTCUTS = {
    "cardiology-director": "D-XN-001",
    "cardiology-attending-1": "D-XN-002",
    "cardiology-attending-2": "D-XN-003",
    "cardiology-head-nurse": "N-XN-001",
    "cardiology-charge-nurse": "N-XN-002",
    "respiratory-director": "D-HX-001",
    "respiratory-attending": "D-HX-002",
    "respiratory-resident": "D-HX-003",
    "respiratory-head-nurse": "N-HX-001",
    "respiratory-charge-nurse": "N-HX-002",
}


def _dev_shortcut_login_enabled() -> bool:
    return (
        os.environ.get("APP_ENV", "dev").strip().lower() == "dev"
        and os.environ.get("AUTH_MODE", "header").strip().lower() == "jwt"
        and os.environ.get("ENABLE_DEV_SHORTCUT_LOGIN", "false").strip().lower() == "true"
    )


@router.post("/login")
async def staff_login(body: LoginRequest):
    """工号 + 密码登录。验证 org_staff 表。

    成功返回 JWT token + 身份信息。
    JWT 可用作后续请求的 Bearer token (当 AUTH_MODE=jwt 时)。
    当前 dev 模式 (AUTH_MODE=header): 前端拿到身份后设 x-role/x-title/x-department headers。
    """
    from .state_store import verify_staff_credentials

    identity = verify_staff_credentials(body.job_number, body.password)
    if identity is None:
        logger.warning("Login failed: job_number=%s", body.job_number)
        return UnifiedResponse(
            error={"code": "INVALID_CREDENTIALS", "message": "工号或密码错误"},
            data=None,
        )

    logger.info("Login success: %s (%s, %s)", identity["name"], identity["title"], identity["department"])
    token = _issue_login_jwt(identity)

    return UnifiedResponse(data={
        **identity,
        "token": token,
        "default_route": (
            "/admin" if identity["is_manager"] and identity["role"] == "doctor"
            else "/admin" if identity["is_manager"] and identity["role"] == "nurse"
            else "/workbench" if identity["role"] == "doctor"
            else "/nurse"
        ),
    })


@router.post("/login/dev-shortcut/{shortcut_id}")
async def dev_shortcut_login(shortcut_id: str):
    """Issue a JWT for one of five explicitly enabled local development identities."""
    if not _dev_shortcut_login_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    job_number = _DEV_SHORTCUTS.get(shortcut_id)
    if not job_number:
        raise HTTPException(status_code=404, detail="Not found")

    from .state_store import get_org_all

    identity = next((staff for staff in get_org_all() if staff.get("job_number") == job_number), None)
    if identity is None:
        raise HTTPException(status_code=503, detail="Development identity is not seeded")

    logger.warning("Development shortcut login: %s", shortcut_id)
    token = _issue_login_jwt(identity)
    return UnifiedResponse(data={
        **identity,
        "token": token,
        "default_route": (
            "/admin" if identity.get("is_manager")
            else "/workbench" if identity.get("role") == "doctor"
            else "/nurse"
        ),
    })


def _issue_login_jwt(identity: dict) -> str:
    """签发登录 JWT token。key=H256, 有效期 12h。"""
    import jwt

    secret = os.environ.get("AUTH_JWT_SECRET", "zhenhu-dev-secret-change-in-production")
    issuer = os.environ.get("AUTH_ISSUER", "zhenhu")
    audience = os.environ.get("AUTH_AUDIENCE", "zhenhu-inpatient")
    now = int(_time.time())

    claims = {
        "sub": identity["job_number"],
        "role": identity["role"],
        "title": identity["title"],
        "department": identity["department"],
        "name": identity["name"],
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + 43200,  # 12 小时
    }
    algorithms = ["HS256"]
    return jwt.encode(claims, secret, algorithm=algorithms[0])


# ═══════════════════════════════════════════════════════════
# 组织架构 — SQLite 驱动
# ═══════════════════════════════════════════════════════════


@router.get("/org")
async def get_org_structure(request: Request):
    """组织架构 — 按角色返回不同层级。数据来源: org_staff 表。"""
    from .state_store import get_org_all, get_org_summary

    user = getattr(request.state, "user_info", {})
    role = user.get("role", "doctor")
    title = user.get("title", "")
    dept = user.get("department")

    is_manager = any(k in title for k in ("主任", "护士长"))

    def leadership_for(staff_members: list[dict], department: str | None) -> dict:
        department_staff = [member for member in staff_members if member.get("department") == department]
        medical_director = next(
            (member for member in department_staff if member.get("role") == "doctor" and "主任" in str(member.get("title") or "")),
            None,
        )
        head_nurse = next(
            (member for member in department_staff if member.get("role") == "nurse" and "护士长" in str(member.get("title") or "")),
            None,
        )
        return {
            "department": department,
            "medical_director": medical_director,
            "head_nurse": head_nurse,
        }

    if is_manager:
        staff = get_org_all()
        departments: dict[str, dict] = {}
        for s in staff:
            d = s["department"]
            if d not in departments:
                departments[d] = {"doctors": [], "nurses": [], "total": 0}
            key = "doctors" if s["role"] == "doctor" else "nurses"
            departments[d][key].append(s)
            departments[d]["total"] += 1

        return UnifiedResponse(data={
            "scope": "全院管理",
            "your_department": dept,
            "your_title": title,
            "leadership": leadership_for(staff, dept),
            "departments": sorted(
                [{"department": k, **v} for k, v in departments.items()],
                key=lambda d: d["total"], reverse=True
            ),
            "summary": get_org_summary(),
        })

    # 普通用户: 本科室
    all_staff = get_org_all()
    dept = dept or (all_staff[0]["department"] if all_staff else None)
    if not dept:
        return UnifiedResponse(data={"scope": "本科室", "error": "无科室数据"})
    from .state_store import get_org_by_department
    dept_data = get_org_by_department(dept)
    all_staff = get_org_all()
    siblings = sorted(set(s["department"] for s in all_staff))

    return UnifiedResponse(data={
        "scope": "本科室",
        "department": dept,
        "your_title": title,
        "leadership": leadership_for(all_staff, dept),
        "department_chain": {
            "department": dept,
            "team": dept_data.get("doctors" if role == "doctor" else "nurses", []),
        },
        "sibling_departments": [{"name": d, "staff_count": sum(1 for s in all_staff if s["department"] == d)}
                                 for d in siblings],
    })


@router.post("/org/seed")
async def seed_org_staff(request: Request):
    """从 config/org_structure.json 导入人员到数据库。"""
    from ..services.management_access import require_management_operation
    require_management_operation(request, "organization_seed")
    from .state_store import seed_org_from_json, get_org_summary
    count = seed_org_from_json()
    from ..agent.audit import write_management_audit_event
    audit_id = await write_management_audit_event(action_type="organization_seeded", detail={"imported": count}, request=request)
    return UnifiedResponse(data={"imported": count, "summary": get_org_summary(), "audit_id": audit_id})


@router.post("/seed-all")
async def seed_all(request: Request):
    """一键导入全部种子数据: 人员 + 病种模板 + 护理清单。"""
    from ..services.management_access import require_management_operation
    require_management_operation(request, "seed_all")
    from .state_store import (seed_org_from_json, seed_templates_from_dir,
                               seed_checklists_from_dict, get_org_summary)
    staff = seed_org_from_json()
    templates = seed_templates_from_dir()
    checklists = seed_checklists_from_dict()
    from ..agent.audit import write_management_audit_event
    audit_id = await write_management_audit_event(action_type="system_seeded", detail={"staff": staff, "templates": templates, "checklists": checklists}, request=request)
    return UnifiedResponse(data={
        "staff": staff,
        "templates": templates,
        "checklists": checklists,
        "org_summary": get_org_summary(),
        "audit_id": audit_id,
    })


@router.post("/rag/index")
async def index_rag_knowledge(request: Request):
    """索引全部临床知识到 Milvus 四层。"""
    from ..services.management_access import require_management_operation
    require_management_operation(request, "rag_reindex")
    from ..agent.rag_engine import RagIndexError, get_rag_stats, index_all

    try:
        results = await run_in_threadpool(index_all)
    except RagIndexError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": "知识源校验失败，未执行索引重建", "error": str(exc)},
        ) from exc
    except Exception as exc:
        logger.exception("RAG rebuild failed through legacy endpoint")
        raise HTTPException(
            status_code=503,
            detail={"message": "知识索引服务重建失败，请检查 Milvus 与嵌入模型", "error": type(exc).__name__},
        ) from exc
    from ..agent.audit import write_management_audit_event
    audit_id = await write_management_audit_event(action_type="rag_reindexed", detail={"layers": results}, request=request)
    return UnifiedResponse(data={
        "layers": results,
        "total": sum(results.values()),
        "stats": get_rag_stats(),
        "audit_id": audit_id,
    })


@router.get("/rag/search")
async def search_rag(
    query: str,
    layer: str | None = None,
    top_k: int = 5,
    disease_id: str | None = None,
    department: str | None = None,
):
    """分层语义检索 (L1/L2/L3/L4)。"""
    from ..agent.rag_engine import search
    results = await search(query, layer=layer, top_k=top_k, disease_id=disease_id, department=department)
    return UnifiedResponse(data={"query": query, "layer": layer, "results": results, "count": len(results)})


@router.get("/rag/stats")
async def get_rag_status():
    """RAG 知识库状态。"""
    from ..agent.rag_engine import get_rag_stats
    return UnifiedResponse(data=get_rag_stats())


@router.get("/rag/browse")
async def browse_rag(layer: str | None = None, page: int = 1, page_size: int = 20):
    """浏览知识库 — 按层分页查看已索引条目。"""
    from ..agent.rag_engine import _c, LAYERS
    client = _c()
    colls = [LAYERS[layer]] if layer and layer in LAYERS else list(LAYERS.values())
    results = {}
    for coll_name in colls:
        try:
            lk = [k for k, v in LAYERS.items() if v == coll_name][0]
            res = client.query(coll_name, filter="source != ''",
                              output_fields=["source","category","topic","disease_id","department","text"],
                              limit=page_size, offset=(page-1)*page_size)
            items = [{"topic": r.get("topic",""), "category": r.get("category",""),
                      "disease_id": r.get("disease_id",""), "department": r.get("department",""),
                      "text": (r.get("text","") or "")[:200]} for r in res]
            results[lk] = {"collection": coll_name, "items": items, "page": page}
        except Exception as e:
            results[lk] = {"error": str(e)}
    return UnifiedResponse(data=results)


@router.get("/rag/validate")
async def validate_rag():
    """验证知识库完整性 — 期望 vs 实际条目数。"""
    from ..agent.rag_engine import _c, LAYERS, collection_row_count, expected_document_counts
    expected = expected_document_counts()
    client, issues, layers = _c(), [], {}
    for layer, cn in LAYERS.items():
        try:
            actual = collection_row_count(cn) if client.has_collection(cn) else 0
            exp = expected.get(layer,0)
            layers[layer] = {"collection":cn,"expected":exp,"actual":actual,"status":"ok" if actual>=exp else "incomplete"}
            if actual < exp: issues.append(f"{layer}: 期望{exp}条 实际{actual}条")
        except Exception as e:
            layers[layer] = {"expected":exp,"actual":0,"status":"error","error":str(e)}
    return UnifiedResponse(data={"layers":layers,"issues":issues,"needs_reindex":len(issues)>0})


@router.get("/templates")
async def get_templates():
    """列出所有病种模板（从数据库读取）。"""
    from .state_store import list_templates
    templates = list_templates()
    return UnifiedResponse(data={"templates": templates, "count": len(templates)})


@router.get("/templates/{disease_id}")
async def get_template_detail(disease_id: str):
    """Return the read-only clinical path used by a disease template."""
    safe_id = disease_id.strip().lower()
    if not safe_id or safe_id != Path(safe_id).name:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": "未找到病种模板"})

    template_path = _TEMPLATE_DIR / f"{safe_id}.json"
    if not template_path.is_file():
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": "未找到病种模板"})
    try:
        payload = json.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read disease template: %s", safe_id)
        return UnifiedResponse(error={"code": "TEMPLATE_UNAVAILABLE", "message": "病种模板暂时不可读取"})

    return UnifiedResponse(data={
        "disease_id": payload.get("disease_id", safe_id),
        "name": payload.get("name") or safe_id,
        "department": payload.get("department") or "",
        "monitoring_interval_hours": payload.get("monitoring_interval_hours"),
        "vital_signs": payload.get("vital_signs") or [],
        "risk_factors": payload.get("risk_factors") or [],
        "discharge_criteria": payload.get("discharge_criteria") or [],
        "handoff_instructions": payload.get("handoff_instructions") or [],
        "followup_questions": payload.get("followup_questions") or [],
        "requires_doctor_review": bool((payload.get("agent_config") or {}).get("require_doctor_review")),
    })


async def _clear_demo_patient_records(*, purge_runtime: bool) -> list[str]:
    """Remove only states conclusively owned by the demo fixtures."""
    from sqlalchemy import delete

    from ..agent.loop import cleanup_patient_loop
    from ..main import async_session_factory
    from ..models import ClinicalWorkflowState, FollowUpContact
    from .state_store import delete_states, list_persisted_state_ids, list_states

    legacy_ids = set(LEGACY_DEMO_PATIENT_IDS) | {DASHBOARD_CARE_FIXTURE_ID, *PATIENTS.keys()}
    existing = list_states()
    patient_ids = (
        sorted(set(list_persisted_state_ids()))
        if purge_runtime
        else sorted(
            patient_id
            for patient_id, state in existing.items()
            if patient_id in legacy_ids or bool((state or {}).get("demo_seed"))
        )
    )
    if not patient_ids:
        return []

    delete_states(patient_ids)
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(delete(ClinicalWorkflowState).where(ClinicalWorkflowState.patient_id.in_(patient_ids)))
            await session.execute(delete(FollowUpContact).where(FollowUpContact.patient_id.in_(patient_ids)))
    for patient_id in patient_ids:
        cleanup_patient_loop(patient_id)
    return patient_ids


@router.post("/fixtures/reset-demo")
async def reset_demo_patient_pack(body: DemoPatientResetRequest, request: Request):
    """Replace only fictional demo records with the current two-department pack."""
    from ..services.management_access import require_management_operation

    require_management_operation(request, "demo_patient_reset")
    if os.environ.get("APP_ENV", "dev").strip().lower() == "production":
        raise HTTPException(status_code=403, detail="Demo patient reset is disabled in production.")
    if not body.confirmed:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required.")

    from ..agent.audit import write_management_audit_event
    from ..services.follow_up_contacts import follow_up_contact_service
    from .state_store import set_state

    removed_ids = await _clear_demo_patient_records(purge_runtime=body.purge_runtime)
    states = build_demo_patient_states()
    for patient_id, state in states.items():
        set_state(patient_id, state)
        if state.get("follow_up_tasks"):
            patient_data = state.get("patient_data") or {}
            await follow_up_contact_service.save(
                patient_id,
                {
                    "mobile_phone": patient_data.get("mobile_phone"),
                    "alternate_contact_name": "演示联系人",
                    "alternate_contact_relation": "家属",
                    "alternate_contact_phone": "15500009999",
                    "preferred_channel": "phone",
                    "follow_up_consent": True,
                },
                expected_contact_version=0,
            )
    audit_id = await write_management_audit_event(
        action_type="demo_patient_pack_reset",
        detail={
            "pack_version": DEMO_PACK_VERSION,
            "removed": len(removed_ids),
            "purge_runtime": body.purge_runtime,
            "total": len(states),
            "by_department": DEMO_DEPARTMENTS,
        },
        request=request,
    )
    return UnifiedResponse(data={
        "pack_version": DEMO_PACK_VERSION,
        "removed": len(removed_ids),
        "purge_runtime": body.purge_runtime,
        "total": len(states),
        "by_department": DEMO_DEPARTMENTS,
        "patient_ids": sorted(states),
        "audit_id": audit_id,
    })


@router.post("/fixtures/load/dashboard-care")
async def load_dashboard_care_fixture():
    """Load one deterministic development fixture for patient-detail end-to-end checks."""
    if os.environ.get("APP_ENV", "dev").strip().lower() == "production":
        return UnifiedResponse(error={
            "code": "FIXTURE_ENDPOINT_DISABLED",
            "message": "Fixture workflow execution is disabled in production.",
        })

    from sqlalchemy import delete

    from ..agent.loop import cleanup_patient_loop
    from ..agent.nodes import load_template
    from ..main import async_session_factory
    from ..models import ClinicalWorkflowState
    from .state_store import delete_states, get_state, set_state

    # 清掉内存 + SQLite 中可能残留的同名记录
    delete_states([DASHBOARD_CARE_FIXTURE_ID])
    # 清掉 ClinicalWorkflowState 事务表
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(ClinicalWorkflowState).where(
                    ClinicalWorkflowState.patient_id == DASHBOARD_CARE_FIXTURE_ID
                )
            )
    cleanup_patient_loop(DASHBOARD_CARE_FIXTURE_ID)
    set_state(DASHBOARD_CARE_FIXTURE_ID, build_dashboard_care_fixture(load_template("heart_failure")))
    state = get_state(DASHBOARD_CARE_FIXTURE_ID) or {}
    return UnifiedResponse(data={
        "patient_id": DASHBOARD_CARE_FIXTURE_ID,
        "state_version": state.get("state_version", 0),
        "message": "Dashboard care fixture loaded.",
    })


@router.post("/fixtures/load/{patient_key}")
async def load_fixture_patient(patient_key: str):
    """加载预置患者数据并执行完整入院→出院流程。"""
    if os.environ.get("APP_ENV", "dev").strip().lower() == "production":
        return UnifiedResponse(error={
            "code": "FIXTURE_ENDPOINT_DISABLED",
            "message": "Fixture workflow execution is disabled in production.",
        })
    if patient_key not in PATIENTS:
        return UnifiedResponse(data={"error": f"未知患者: {patient_key}"}, error={"code": "NOT_FOUND"})

    from ..agent.loop import get_patient_loop, get_patient_lock
    from ..agent.nodes import load_template
    from .state_store import set_state, get_state, update_state

    # ── O6: 持锁包裹整个 fixture 流程 ──
    lock = get_patient_lock(patient_key)
    async with lock:
        p = PATIENTS[patient_key]

        # 1. 创建入院
        loop = get_patient_loop(patient_key)
        state = loop.gen_input("new_admission")
        state["patient_id"] = patient_key
        state["patient_data"] = p["patient_data"]
        state["patient_history"] = p["patient_history"]
        state["allergies"] = p["allergies"]
        state["disease_template"] = load_template(p["disease_id"])

        result = await loop.plan_turn(state)
        set_state(patient_key, result)

        # Batch 0: fixture 可能因 pending_review 被挂起——自动 approve 续跑
        from ..agent.config import is_doctor_auto_approve
        _auto_approve = is_doctor_auto_approve()
        if isinstance(result, dict) and result.get("status") == "pending_review":
            if not _auto_approve:
                return UnifiedResponse(data={
                    "patient_key": patient_key,
                    "name": p["name"],
                    "disease": p["disease_id"],
                    "final_phase": "pending_review",
                    "vital_signs_count": 0,
                    "handoff_items": 0,
                    "discharge_decision": "pending_review",
                    "document_chain": [],
                    "traces": len(loop.traces),
                    "message": "医生审核待处理，请通过 POST /inpatient/review/{patient_key} 提交审核决策",
                })
            state = get_state(patient_key)
            state["doctor_confirm_status"] = "approved"
            result = await loop.plan_turn(state)
            set_state(patient_key, result)

        # 2. 逐步上报体征
        for i, vs in enumerate(p["vital_signs_sequence"]):
            current = get_state(patient_key)
            vss = current.get("vital_signs", []) + [vs]
            update_state(patient_key, {"vital_signs": vss})
            result = await loop.plan_turn(get_state(patient_key))
            set_state(patient_key, result)

            # 检测 pending_review —— fixture 场景自动 approve 续跑
            if isinstance(result, dict) and result.get("status") == "pending_review":
                if not _auto_approve:
                    continue  # 不能自动审批，跳过本轮等待医生审核
                state = get_state(patient_key)
                state["doctor_confirm_status"] = "approved"
                result = await loop.plan_turn(state)
                set_state(patient_key, result)

            # 如果已自动出院或满足出院条件，触发完整出院链路
            if isinstance(result, dict) and result.get("status") != "pending_review":
                if result.get("phase") in ("discharge", "handoff", "review", "confirm"):
                    break
                if result.get("discharge_decision") == "approved":
                    state = get_state(patient_key)
                    result = await loop.plan_turn(state)
                    set_state(patient_key, result)

                    break

        return UnifiedResponse(data={
            "patient_key": patient_key,
            "name": p["name"],
            "disease": p["disease_id"],
            "final_phase": result.get("phase") if isinstance(result, dict) and result.get("status") != "pending_review" else "pending_review",
            "vital_signs_count": len(result.get("vital_signs", [])) if isinstance(result, dict) else 0,
            "handoff_items": len(result.get("handoff_items", [])) if isinstance(result, dict) else 0,
            "discharge_decision": result.get("discharge_decision") if isinstance(result, dict) and result.get("status") != "pending_review" else "pending_review",
            "document_chain": result.get("document_chain", []) if isinstance(result, dict) else [],
            "traces": len(loop.traces),
        })


# ═══════════════════════════════════════════════════════════
# SQLite 持久化管理
# ═══════════════════════════════════════════════════════════

@router.get("/db-stats")
async def get_db_stats(request: Request):
    """数据库统计 — SQLite 行数、文件大小。"""
    from ..services.management_access import require_management_operation
    require_management_operation(request, "database_stats", write=False)
    from .state_store import get_db_stats, get_store_size
    stats = get_db_stats()
    return UnifiedResponse(data={
        **stats,
        "memory_entries": get_store_size(),
        "file_size_mb": round(stats.get("file_size_bytes", 0) / 1048576, 2),
    })


@router.post("/clear-expired")
async def clear_expired(request: Request):
    """手动清理过期条目 — 调用后台清理逻辑。"""
    from ..services.management_access import require_management_operation
    require_management_operation(request, "clear_expired")
    from .state_store import force_cleanup, get_store_size
    removed = force_cleanup()
    from ..agent.audit import write_management_audit_event
    audit_id = await write_management_audit_event(action_type="expired_state_cleared", detail={"removed": removed, "remaining": get_store_size()}, request=request)
    return UnifiedResponse(data={
        "removed": removed,
        "remaining": get_store_size(),
        "audit_id": audit_id,
    })
