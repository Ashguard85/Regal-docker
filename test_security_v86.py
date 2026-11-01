from app.security import parse_allowed_origins


def test_multiple_cors_origins_and_legacy_are_normalized():
    valid, invalid = parse_allowed_origins(
        "https://ashguard85.github.io, http://192.168.1.127:8190;https://EXAMPLE.com:443/",
        "https://legacy.example.org/",
    )
    assert valid == [
        "https://ashguard85.github.io",
        "http://192.168.1.127:8190",
        "https://example.com",
        "https://legacy.example.org",
    ]
    assert invalid == []


def test_cors_origins_reject_paths_credentials_and_queries():
    valid, invalid = parse_allowed_origins(
        "https://good.example,https://bad.example/path,https://user:pass@example.org,https://bad.example?x=1"
    )
    assert valid == ["https://good.example"]
    assert len(invalid) == 3


def test_duplicate_origins_are_removed():
    valid, invalid = parse_allowed_origins("https://example.org/,https://example.org")
    assert valid == ["https://example.org"]
    assert invalid == []
