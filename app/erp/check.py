"""Check erp/d365_mapping.yaml against your environment's OData metadata, offline.

    # 1. save the metadata once (browser, signed in):  https://<env>.operations.dynamics.com/data/$metadata   -> metadata.xml
    # 2. python -m app.erp.check metadata.xml

Reports: placeholder (TODO_) names still present; entity set not found; fields not found on the entity; fields that D365 marks
required (Nullable="false") but the mapping does not fill; type mismatches for dates and numbers. It never contacts D365.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from .d365 import mapping

EDM_NUMERIC = {"Edm.Decimal", "Edm.Double", "Edm.Single", "Edm.Int32", "Edm.Int64", "Edm.Int16"}
EDM_DATE = {"Edm.DateTimeOffset", "Edm.Date"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_metadata(xml_text: str) -> dict:
    """{entity_set: {"type": name, "props": {name: {"type", "nullable"}}}}"""
    root = ET.fromstring(xml_text)
    types, sets = {}, {}
    for el in root.iter():
        if _local(el.tag) == "EntityType":
            types[el.get("Name")] = {p.get("Name"): {"type": p.get("Type"), "nullable": p.get("Nullable", "true") != "false"}
                                     for p in el if _local(p.tag) == "Property"}
        elif _local(el.tag) == "EntitySet":
            sets[el.get("Name")] = (el.get("EntityType") or "").rsplit(".", 1)[-1]
    return {s: {"type": t, "props": types.get(t, {})} for s, t in sets.items()}


def check(m: dict, meta: dict) -> dict:
    errors, warnings = [], []
    ent = m["entities"]["schedule_lines"]
    if str(ent).startswith("TODO_"):
        errors.append(f"entity name is still a placeholder: {ent}")
    for f in m["fields"]:
        if str(f["target"]).startswith("TODO_"):
            errors.append(f"field '{f['source']}' still has a placeholder name: {f['target']}")
    if errors and ent.startswith("TODO_"):
        return {"ok": False, "errors": errors, "warnings": warnings}
    spec = meta.get(ent)
    if spec is None:
        near = [s for s in meta if s.lower() == ent.lower() or ent.lower() in s.lower()][:5]
        errors.append(f"entity set '{ent}' not found in the metadata" + (f" (similar: {', '.join(near)})" if near else ""))
        return {"ok": False, "errors": errors, "warnings": warnings}
    props = spec["props"]
    for f in m["fields"]:
        p = props.get(f["target"])
        if p is None:
            errors.append(f"field '{f['target']}' (from '{f['source']}') does not exist on {ent}")
            continue
        if f["type"] in ("decimal", "integer") and p["type"] not in EDM_NUMERIC:
            errors.append(f"'{f['target']}' is {p['type']} in D365 but the mapping sends a number")
        if f["type"] == "date" and p["type"] not in EDM_DATE:
            errors.append(f"'{f['target']}' is {p['type']} in D365 but the mapping sends a date")
        if f["type"] == "string" and p["type"] != "Edm.String":
            warnings.append(f"'{f['target']}' is {p['type']} in D365 but the mapping sends text")
    mapped = {f["target"] for f in m["fields"]}
    missing = [n for n, p in props.items() if not p["nullable"] and n not in mapped]
    if missing:
        warnings.append(f"D365 requires {len(missing)} field(s) the mapping does not fill: {', '.join(missing[:12])}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    res = check(mapping(), parse_metadata(Path(argv[0]).read_text(encoding="utf-8")))
    for e in res["errors"]:
        print("ERROR  ", e)
    for w in res["warnings"]:
        print("WARNING", w)
    print("mapping OK" if res["ok"] else "mapping NOT ready for a live push")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
