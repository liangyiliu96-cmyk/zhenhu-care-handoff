"""Agent工具模块 + metrics + interrupt 测试。"""
import asyncio
import pytest


class TestMetrics:
    def test_record_and_get(self):
        from zhenhu.inpatient.agent.metrics import record, get_metrics
        record("test_node")
        record("test_node")
        record("test_node_2")
        metrics_text = get_metrics()
        assert "zhenhu_node_calls_total" in metrics_text
        assert "test_node" in metrics_text
        assert "zhenhu_uptime_seconds" in metrics_text

    def test_error_record(self):
        from zhenhu.inpatient.agent.metrics import record, get_metrics
        record("error_node", error=True)
        metrics_text = get_metrics()
        assert "zhenhu_node_errors_total" in metrics_text
        assert "error_node" in metrics_text


class TestInterrupt:
    def test_request_doctor_review_returns_default(self):
        """外部审核不可用时返回默认值。"""
        from zhenhu.inpatient.agent.interrupt import request_doctor_review
        items = [{"type": "medication", "content": "阿司匹林 100mg qd", "feedback": None}]
        result = asyncio.run(request_doctor_review(items))
        assert result["status"] == "not_reviewed"
        assert result["handoff_items"] == items

    def test_interrupt_passes_through_items(self):
        from zhenhu.inpatient.agent.interrupt import request_doctor_review
        items = [{"type": "monitoring", "content": "每日测血压", "feedback": None}]
        result = asyncio.run(request_doctor_review(items))
        assert len(result["handoff_items"]) == 1


class TestTools:
    @pytest.mark.asyncio
    async def test_search_knowledge_returns_empty(self):
        """无知识库服务时返回空列表。"""
        from zhenhu.inpatient.agent.tools import search_knowledge
        results = await search_knowledge("高血压饮食")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_check_discharge_criteria_empty_template(self):
        """空模板返回False。"""
        from zhenhu.inpatient.agent.tools import check_discharge_criteria
        result = await check_discharge_criteria({}, [])
        assert result is False

    @pytest.mark.asyncio
    async def test_check_discharge_with_criteria(self):
        """有出院标准但无体征→False。"""
        from zhenhu.inpatient.agent.tools import check_discharge_criteria
        template = {"discharge_criteria": [{"condition": "bp_stable", "description": "血压稳定"}]}
        result = await check_discharge_criteria(template, [])
        assert result is False
