"""Medication-safety dashboard projection coverage."""

from __future__ import annotations

import pytest

from request_helpers import doctor_request


@pytest.mark.asyncio
async def test_dashboard_projects_persisted_medication_findings_with_traceability(isolated_state_store, monkeypatch):
    from zhenhu.inpatient.routes import dashboard
    from zhenhu.inpatient.routes.state_store import set_state

    async def no_checklist(_state):
        return []

    monkeypatch.setattr(dashboard, "_compute_checklist", no_checklist)
    set_state("dashboard-medication-safety", {
        "patient_id": "dashboard-medication-safety",
        "disease_template": {"name": "心力衰竭"},
        "document_chain": ["medication_reconciliation"],
        "medication_findings": {
            "conflicts": [
                {
                    "drug_pair": "华法林 + 布洛芬",
                    "severity": "contraindicated",
                    "mechanism": "出血风险增加",
                    "consequence": "消化道出血风险升高",
                    "recommendation": "避免联用",
                    "evidence": "A",
                    "source": "ACCP 抗栓指南",
                },
                {
                    "drug_pair": "模型补充组合",
                    "severity": "moderate",
                    "evidence": "LLM",
                },
            ],
            "allergy_contraindications": [{"medication": "阿莫西林", "allergen": "青霉素", "severity": "major", "recommendation": "避免使用"}],
            "gaps": ["缺少出院带药记录"],
        },
    })

    response = await dashboard.get_dashboard("dashboard-medication-safety", doctor_request())
    safety = response.data["medication_safety"]

    assert safety["status"] == "complete"
    assert safety["conflicts"][0]["source"] == "ACCP 抗栓指南"
    assert safety["conflicts"][0]["model_suggested"] is False
    assert safety["conflicts"][1]["source"] == "模型补充，需临床复核"
    assert safety["conflicts"][1]["model_suggested"] is True
    assert safety["allergy_contraindications"][0]["allergen"] == "青霉素"
