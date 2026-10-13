"""Tolerant author lookup: spelling variants, similarity, tier order (offline)."""
from src.pathfinding.author_search import (
    name_similarity,
    name_variants,
    search_author_candidates,
)


class FakeClient:
    """Answers OpenAlex calls from a table of {query: [display names]}."""

    def __init__(self, by_display_name=None, by_search=None):
        self.by_display_name = by_display_name or {}
        self.by_search = by_search or {}
        self.calls = []

    def _make_request(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if endpoint == "/authors" and "filter" in params and params["filter"].startswith("display_name.search:"):
            names = self.by_display_name.get(params["filter"].split(":", 1)[1], [])
        elif endpoint == "/authors" and "search" in params:
            names = self.by_search.get(params["search"], [])
        else:
            names = []
        return {"results": [{"id": f"https://openalex.org/A{i}{n}", "display_name": n, "works_count": 10}
                            for i, n in enumerate(names)]}


def test_variants_join_and_split_particles():
    assert "Yann LeCun" in name_variants("Yann Le Cun")
    assert "Yann Le Cun" in name_variants("Yann LeCun")


def test_variants_drop_accents_and_hyphens():
    assert "jean paul sartre" in name_variants("Jean-Paul Sàrtre")


def test_similarity_tolerates_typos_and_order():
    assert name_similarity("Yan Lecun", "Yann LeCun") >= 0.8
    assert name_similarity("Charpentier Emmanuelle", "Emmanuelle Charpentier") >= 0.95
    assert name_similarity("Jennifer Doudna", "Jennifer A. Doudna") >= 0.95


def test_similarity_rejects_other_people():
    assert name_similarity("Yan Lecun", "Lecun Wang") < name_similarity("Yan Lecun", "Yann LeCun")
    assert name_similarity("Yann LeCun", "Yoshua Bengio") < 0.5


def test_exact_match_is_not_approximate():
    client = FakeClient(by_display_name={"Yann LeCun": ["Yann LeCun"]})
    authors, approximate = search_author_candidates("Yann LeCun", client)
    assert [a["display_name"] for a in authors] == ["Yann LeCun"]
    assert approximate is False


def test_spaced_particle_falls_back_to_variant():
    client = FakeClient(by_display_name={"Yann LeCun": ["Yann LeCun"]})
    authors, approximate = search_author_candidates("Yann Le Cun", client)
    assert [a["display_name"] for a in authors] == ["Yann LeCun"]
    assert approximate is False


def test_typo_uses_family_name_and_ranks_by_closeness():
    client = FakeClient(by_search={"lecun": ["Lecun Wang", "Yann LeCun", "Bertrand Lecun"]})
    authors, approximate = search_author_candidates("Yan Lecun", client)
    assert approximate is True
    assert authors[0]["display_name"] == "Yann LeCun"


def test_unknown_name_returns_nothing():
    authors, approximate = search_author_candidates("Zzzqx Blorpton", FakeClient())
    assert authors == [] and approximate is False
