"""知识管理路由模块。"""

from zhenhu.knowledge.routes.documents import router as documents_router
from zhenhu.knowledge.routes.search import router as search_router
from zhenhu.knowledge.routes.admin import router as admin_router

__all__ = ["documents_router", "search_router", "admin_router"]
