import pytest

from jobfinder.api import _auto_init_db_enabled


def test_auto_init_db_defaults_on_for_local_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("AUTO_INIT_DB", raising=False)
    assert _auto_init_db_enabled() is True


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_auto_init_db_defaults_off_for_hosted_environments(monkeypatch, environment):
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.delenv("AUTO_INIT_DB", raising=False)
    assert _auto_init_db_enabled() is False


def test_auto_init_db_can_be_explicitly_enabled_for_disposable_demo(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTO_INIT_DB", "true")
    assert _auto_init_db_enabled() is True


def test_auto_init_db_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("AUTO_INIT_DB", "yes")
    with pytest.raises(RuntimeError, match="AUTO_INIT_DB"):
        _auto_init_db_enabled()
