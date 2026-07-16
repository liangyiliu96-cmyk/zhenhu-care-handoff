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
    def test_request_doctor_review_returns_accept(self):
        from zhenhu.inpatient.agent.interrupt import request_doctor_review
        items = [{"type": "medication", "content": "测试", "feedback": None}]
        result = asyncio.run(request_doctor_review(items))
        assert result["action"] == "accept"
        assert result["items"] == items

    def test_interrupt_passes_through_items(self):
        from zhenhu.inpatient.agent.interrupt import request_doctor_review
        items = [{"type": "monitoring", "content": "每日测血压", "feedback": None}]
        result = asyncio.run(request_doctor_review(items))
        assert len(result["items"]) == 1


class TestTools:
    @pytest.mark.asyncio
    async def test_search_knowledge_returns_empty(self):
        from zhenhu.inpatient.agent.tools import search_knowledge
        results = await search_knowledge("高血压饮食")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_check_discharge_criteria_empty_template(self):
        from zhenhu.inpatient.agent.tools import check_discharge_criteria
        result = await check_discharge_criteria({}, [])
        assert result is False

    @pytest.mark.asyncio
    async def test_check_discharge_with_criteria(self):
        from zhenhu.inpatient.agent.tools import check_discharge_criteria
        template = {"discharge_criteria": [{"condition": "bp_stable", "description": "血压稳定"}]}
        result = await check_discharge_criteria(template, [])
        assert result is False
