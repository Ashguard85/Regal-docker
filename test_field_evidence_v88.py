from app.evidence import build_field_evidence


def web_bundle(name, url, source_class, source_label, extracted):
    return {
        "kind": "web_page",
        "title": name,
        "url": url,
        "source_class": source_class,
        "source_label": source_label,
        "extracted": extracted,
    }


def test_official_source_marks_direct_field_safe():
    proposed = {"min_players": 1, "max_players": 5, "publisher": "Feuerland Spiele", "description": "Deutsch zusammengefasst"}
    bundles = [web_bundle(
        "Scythe - Feuerland Spiele",
        "https://www.feuerland-spiele.de/spiele/scythe/",
        "official",
        "Offizielle Verlags-/Herstellerseite",
        {"min_players": 1, "max_players": 5, "publisher": "Feuerland Spiele"},
    )]
    evidence = build_field_evidence(proposed, bundles)
    assert evidence["min_players"]["level"] == "primary"
    assert evidence["min_players"]["safe_to_apply"] is True
    assert evidence["publisher"]["safe_to_apply"] is True
    assert evidence["description"]["level"] == "derived"
    assert evidence["description"]["safe_to_apply"] is False


def test_two_independent_sources_are_strong():
    proposed = {"year": 2016}
    bundles = [
        web_bundle("Quelle A", "https://example-a.invalid/scythe", "reference", "Referenzquelle", {"year": 2016}),
        web_bundle("Quelle B", "https://example-b.invalid/scythe", "product", "Produktseite", {"year": 2016}),
    ]
    evidence = build_field_evidence(proposed, bundles)
    assert evidence["year"]["level"] == "strong"
    assert evidence["year"]["safe_to_apply"] is True


def test_conflicting_source_blocks_bulk_apply():
    proposed = {"play_time_min": 115}
    bundles = [
        web_bundle("Verlag", "https://publisher.invalid/game", "official", "Offizielle Verlags-/Herstellerseite", {"play_time_min": 115}),
        web_bundle("Shop", "https://shop.invalid/game", "retailer", "Händler/Shop", {"play_time_min": 120}),
    ]
    evidence = build_field_evidence(proposed, bundles)
    assert evidence["play_time_min"]["level"] == "conflict"
    assert evidence["play_time_min"]["safe_to_apply"] is False
    assert evidence["play_time_min"]["conflicts"][0]["value"] == 120


def test_title_never_bulk_applies_even_when_official():
    proposed = {"title": "Scythe"}
    bundles = [web_bundle("Scythe", "https://publisher.invalid/scythe", "official", "Offizielle Verlags-/Herstellerseite", {"title": "Scythe"})]
    evidence = build_field_evidence(proposed, bundles)
    assert evidence["title"]["level"] == "primary"
    assert evidence["title"]["safe_to_apply"] is False
