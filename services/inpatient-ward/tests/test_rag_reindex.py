from __future__ import annotations

import pytest


def test_knowledge_sources_build_all_layers_with_mixed_drug_formats():
    from zhenhu.inpatient.agent.rag_engine import build_index_documents, expected_document_counts

    documents = build_index_documents()

    assert set(documents) == {f"L{index}" for index in range(1, 17)}
    assert sum(len(rows) for rows in documents.values()) == 385
    assert expected_document_counts()["L5"] == 25
    assert any(row["topic"] == "华法林+多种药物 交互矩阵" for row in documents["L5"])
    assert all(row["text"] for row in documents["L9"])


def test_collection_row_count_uses_milvus_stats(monkeypatch):
    from zhenhu.inpatient.agent import rag_engine

    class Client:
        def get_collection_stats(self, collection_name: str):
            assert collection_name == "patient_education"
            return {"row_count": "51"}

    monkeypatch.setattr(rag_engine, "_c", lambda: Client())

    assert rag_engine.collection_row_count("patient_education") == 51


def test_reindex_prepares_all_embeddings_before_resetting_any_collection(monkeypatch):
    from zhenhu.inpatient.agent import rag_engine

    documents = {
        "L1": [{"text": "first"}],
        "L2": [{"text": "second"}],
    }
    reset_layers: list[list[str]] = []

    monkeypatch.setattr(rag_engine, "build_index_documents", lambda: documents)

    def fail_on_second_embedding(texts):
        if texts == ["second"]:
            raise RuntimeError("embedding service unavailable")
        return [[0.0] * rag_engine.DIM]

    monkeypatch.setattr(rag_engine, "_enc", fail_on_second_embedding)
    monkeypatch.setattr(rag_engine, "_reset_collections", lambda layers: reset_layers.append(list(layers)))

    try:
        rag_engine.index_all(["L1", "L2"])
    except rag_engine.RagIndexError as exc:
        assert "未修改现有索引" in str(exc)
    else:
        raise AssertionError("index_all should fail while preparing embeddings")

    assert reset_layers == []


@pytest.mark.asyncio
async def test_entry_search_matches_content_without_interpolating_user_text_into_milvus(monkeypatch):
    from zhenhu.inpatient.agent import rag_engine
    from zhenhu.inpatient.routes.rag_admin import list_entries

    calls = []

    class Client:
        def query(self, collection_name, *, filter, output_fields, limit, offset):
            calls.append({"collection": collection_name, "filter": filter, "limit": limit, "offset": offset})
            assert filter == 'source != ""'
            return [
                {
                    "id": 1,
                    "source": "guideline",
                    "category": "medication",
                    "topic": "diabetes",
                    "disease_id": "diabetes",
                    "department": "endocrinology",
                    "text": 'Use GLP-1RA for the matching "patient" group.',
                    "indexed_at": 1.0,
                },
                {
                    "id": 2,
                    "source": "guideline",
                    "category": "monitoring",
                    "topic": "hypertension",
                    "disease_id": "hypertension",
                    "department": "cardiology",
                    "text": "Monitor blood pressure.",
                    "indexed_at": 1.0,
                },
            ]

    monkeypatch.setattr(rag_engine, "_c", lambda: Client())
    monkeypatch.setattr(rag_engine, "collection_row_count", lambda _collection: 2)

    response = await list_entries(layer="L5", search='GLP-1RA "patient"', page=1, page_size=30)
    data = response.model_dump(mode="json")["data"]

    assert calls == [{"collection": "drug_safety", "filter": 'source != ""', "limit": 30, "offset": 0}]
    assert [item["id"] for item in data["layers"]["L5"]["items"]] == [1]
