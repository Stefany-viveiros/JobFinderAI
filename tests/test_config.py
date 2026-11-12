import pytest

from jobfinder.config import parse_cors_origins


def test_cors_origins_accept_explicit_https_and_local_development():
    assert parse_cors_origins(
        "https://app.example.com/,http://localhost:5173,http://127.0.0.1:5173"
    ) == [
        "https://app.example.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_cors_origins_deduplicate_normalized_values():
    assert parse_cors_origins("https://app.example.com,https://app.example.com/") == [
        "https://app.example.com"
    ]


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://app.example.com,*",
        "http://app.example.com",
        "https://app.example.com/dashboard",
        "https://user:password@app.example.com",
        "https://app.example.com:porta",
        "",
        ", ,",
    ],
)
def test_cors_origins_reject_wildcard_insecure_or_invalid_values(value):
    with pytest.raises(ValueError):
        parse_cors_origins(value)
