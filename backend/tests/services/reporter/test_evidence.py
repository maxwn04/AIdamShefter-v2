from dataclasses import replace

import pytest

from backend.services.reporter.runner.evidence import EvidenceCatalog, EvidenceRecord


def test_catalog_missing_duplicate_and_defensive_reads():
    catalog = EvidenceCatalog()
    record = EvidenceRecord("e1_0.r0", "e1_0", "standings", "found", fields={"wins": 10})
    catalog.register("e1_0", (record,))
    record.fields["wins"] = 99
    assert catalog.resolve("e1_0.r0").fields["wins"] == 10
    catalog.resolve("e1_0.r0").fields["wins"] = 100
    assert catalog.records_for("e1_0")[0].fields["wins"] == 10
    assert catalog.resolve("fabricated") is None
    with pytest.raises(ValueError):
        catalog.register("e1_0", (record,))
    with pytest.raises(ValueError):
        catalog.register("e2_0", (replace(record, source="e1_0"),))
