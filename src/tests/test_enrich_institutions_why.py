"""Companies found through OpenAlex affiliations must carry the reason for the link."""
from src.graph.enrich_institutions_from_openalex import enrich_institutions_from_openalex


def _person(pid, label, institutions):
    return {"id": pid, "type": "person", "label": label,
            "attributes": {"openalex_institutions": institutions}}


def test_affiliation_to_a_company_records_who_and_why():
    graph = {
        "meta": {"seed_person_id": "person:seed"},
        "nodes": [
            _person("person:seed", "Alice Test", [
                {"name": "Google (United States)", "is_current": False, "openalex_url": "https://openalex.org/I1"},
            ]),
            _person("person:bob", "Bob Test", [
                {"name": "Google (United States)", "is_current": True, "openalex_url": "https://openalex.org/I1"},
            ]),
        ],
        "edges": [],
    }
    graph = enrich_institutions_from_openalex(graph)
    google = next(n for n in graph["nodes"] if n["type"] == "corporate")
    connections = google["attributes"]["connections"]

    assert {c["scientist_name"] for c in connections} == {"Alice Test", "Bob Test"}
    assert all(c["affiliation_type"] == "employment" for c in connections)
    by_name = {c["scientist_name"]: c["evidence"][0] for c in connections}
    assert by_name["Alice Test"] == {"source": "openalex", "is_current": False, "url": "https://openalex.org/I1"}
    assert by_name["Bob Test"]["is_current"] is True


def test_reason_is_not_duplicated_on_rerun():
    graph = {
        "meta": {"seed_person_id": "person:seed"},
        "nodes": [_person("person:seed", "Alice Test", [
            {"name": "Meta (United States)", "is_current": True, "openalex_url": "https://openalex.org/I2"},
        ])],
        "edges": [],
    }
    graph = enrich_institutions_from_openalex(graph)
    graph = enrich_institutions_from_openalex(graph)
    meta = next(n for n in graph["nodes"] if n["type"] == "corporate")
    assert len(meta["attributes"]["connections"]) == 1
