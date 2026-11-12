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


@pytest.mark.parametrize(
    "app_env,session_hours,cookie_secure",
    [
        ("development", 24, False),
        ("test", 1, False),
        ("staging", 24, True),
        ("production", 24, True),
        ("production", 720, True),
    ],
)
def test_session_configuration_accepts_safe_values(app_env, session_hours, cookie_secure):
    from jobfinder.config import validate_session_configuration

    validate_session_configuration(app_env, session_hours, cookie_secure)


@pytest.mark.parametrize(
    "app_env,session_hours,cookie_secure",
    [
        ("unknown", 24, True),
        ("production", 24, False),
        ("staging", 24, False),
        ("development", 0, False),
        ("production", 721, True),
    ],
)
def test_session_configuration_rejects_unsafe_values(app_env, session_hours, cookie_secure):
    from jobfinder.config import validate_session_configuration

    with pytest.raises(ValueError):
        validate_session_configuration(app_env, session_hours, cookie_secure)
