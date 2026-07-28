"""FHIR write-path configuration coverage."""

import os


def test_fhir_sync_uses_the_configured_fhir_adapter_url():
    from zhenhu.inpatient.agent.fhir_sync import FHIR_BASE_URL

    expected = os.environ.get("FHIR_ADAPTER_URL", "http://localhost:8300/fhir")
    assert FHIR_BASE_URL == expected
