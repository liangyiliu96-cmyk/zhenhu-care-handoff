"""管理路由 —— 阶段D: 病种模板管理、系统状态等管理功能。合并迁入。

提供 GET /inpatient/templates 列出所有可用病种模板(JSON 配置化)。
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter
from ..schemas import UnifiedResponse

# 合并迁入: 直接引用 disease_templates 目录, 不依赖 app.domain.templates
_TEMPLATE_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "disease_templates")).resolve()

router = APIRouter(prefix="/inpatient", tags=["admin"])


@router.get("/templates")
async def list_templates():
    """列出所有可用病种模板。"""
    templates = []
    for f in sorted(_TEMPLATE_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        templates.append({"disease_id": d["disease_id"], "name": d["name"]})
    return UnifiedResponse(data={"templates": templates})
