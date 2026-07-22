"""FHIR write-path configuration coverage."""


def test_fhir_sync_uses_the_shared_fhir_adapter_default_url():
    from zhenhu.inpatient.agent.fhir_sync import FHIR_BASE_URL

    assert FHIR_BASE_URL == "http://localhost:8300/fhir"
