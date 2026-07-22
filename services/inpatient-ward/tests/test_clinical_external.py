"""External clinical API collection coverage."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_collect_api_data_normalizes_drug_and_icd_evidence(monkeypatch):
    from zhenhu.inpatient.agent import clinical_external

    async def fake_enrich_medications(names):
        assert names == ["metoprolol"]
        return [{
            "original": "metoprolol",
            "rxnorm_id": "6918",
            "standard_name": "metoprolol tartrate",
            "label": {
                "warnings": "Do not stop suddenly.",
                "contraindications": "Cardiogenic shock.",
                "interactions": "Monitor with other rate-lowering medicines.",
            },
        }]

    async def fake_icd10_search(term, max_results=5):
        assert term == "heart failure"
        assert max_results == 3
        return [{"code": "I50.9", "name": "Heart failure, unspecified"}]

    monkeypatch.delenv("SKIP_EXTERNAL", raising=False)
    monkeypatch.setattr(clinical_external, "enrich_medications", fake_enrich_medications)
    monkeypatch.setattr(clinical_external, "icd10_search", fake_icd10_search)

    result = await clinical_external.collect_api_data({
        "medication_list": ["metoprolol"],
        "ddx_list": [{"name": "heart failure"}],
    })

    assert result["drug_evidence"] == [{
        "drug": "metoprolol",
        "rxnorm_id": "6918",
        "standard_name": "metoprolol tartrate",
        "warnings": "Do not stop suddenly.",
        "contraindications": "Cardiogenic shock.",
        "interactions": "Monitor with other rate-lowering medicines.",
        "source": "OpenFDA/RxNorm",
        "status": "available",
    }]
    assert result["icd10_codes"] == [{"code": "I50.9", "name": "Heart failure, unspecified"}]


@pytest.mark.asyncio
async def test_collect_api_data_degrades_without_claiming_external_safety(monkeypatch):
    from zhenhu.inpatient.agent import clinical_external

    async def unavailable_medications(_names):
        raise RuntimeError("upstream unavailable")

    monkeypatch.delenv("SKIP_EXTERNAL", raising=False)
    monkeypatch.setattr(clinical_external, "enrich_medications", unavailable_medications)

    result = await clinical_external.collect_api_data({"medication_list": ["metoprolol"]})

    assert result["drug_evidence"] == [{
        "drug": "metoprolol",
        "rxnorm_id": "",
        "standard_name": "",
        "warnings": "",
        "contraindications": "",
        "interactions": "",
        "source": "OpenFDA/RxNorm",
        "status": "unavailable",
    }]


@pytest.mark.asyncio
async def test_collect_api_data_has_a_bounded_external_wait(monkeypatch):
    from zhenhu.inpatient.agent import clinical_external

    async def slow_medications(_names):
        await asyncio.sleep(1)
        return []

    monkeypatch.delenv("SKIP_EXTERNAL", raising=False)
    monkeypatch.setattr(clinical_external, "EXTERNAL_COLLECTION_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(clinical_external, "enrich_medications", slow_medications)

    result = await clinical_external.collect_api_data({"medication_list": ["metoprolol"]})

    assert result["drug_evidence"][0]["status"] == "unavailable"
