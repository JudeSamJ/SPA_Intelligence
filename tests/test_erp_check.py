from app.erp import check as ck

XML = """<?xml version="1.0"?><edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0"><edmx:DataServices>
<Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="Microsoft.Dynamics.DataEntities">
<EntityType Name="TestScheduleLine"><Key><PropertyRef Name="Id"/></Key>
 <Property Name="Id" Type="Edm.String" Nullable="false"/><Property Name="Ref" Type="Edm.String"/><Property Name="Amt" Type="Edm.Decimal"/>
 <Property Name="Due" Type="Edm.DateTimeOffset"/><Property Name="Cur" Type="Edm.String"/><Property Name="Dataarea" Type="Edm.String" Nullable="false"/></EntityType>
<EntityContainer Name="Container"><EntitySet Name="TestScheduleLines" EntityType="Microsoft.Dynamics.DataEntities.TestScheduleLine"/></EntityContainer>
</Schema></edmx:DataServices></edmx:Edmx>"""

M = {"entities": {"schedule_lines": "TestScheduleLines"},
     "fields": [{"source": "contract_ref", "target": "Ref", "type": "string"}, {"source": "amount", "target": "Amt", "type": "decimal"},
                {"source": "due_date", "target": "Due", "type": "date"}, {"source": "currency", "target": "Cur", "type": "string"}]}


def test_parse_metadata():
    meta = ck.parse_metadata(XML)
    assert set(meta["TestScheduleLines"]["props"]) == {"Id", "Ref", "Amt", "Due", "Cur", "Dataarea"}


def test_good_mapping_ok_with_required_field_warning():
    r = ck.check(M, ck.parse_metadata(XML))
    assert r["ok"] and any("Id, Dataarea" in w for w in r["warnings"])


def test_wrong_names_and_types_reported():
    bad = {"entities": {"schedule_lines": "TestScheduleLines"},
           "fields": [{"source": "a", "target": "Nope", "type": "string"}, {"source": "b", "target": "Ref", "type": "decimal"},
                      {"source": "c", "target": "Amt", "type": "date"}]}
    r = ck.check(bad, ck.parse_metadata(XML))
    assert not r["ok"] and len(r["errors"]) == 3


def test_missing_entity_suggests_similar():
    r = ck.check({**M, "entities": {"schedule_lines": "testscheduleline"}}, ck.parse_metadata(XML))
    assert not r["ok"] and "TestScheduleLines" in r["errors"][0]


def test_shipped_placeholder_mapping_is_not_ready():
    from app.erp.d365 import mapping
    r = ck.check(mapping(), ck.parse_metadata(XML))
    assert not r["ok"] and any("placeholder" in e for e in r["errors"])
