import pytest
from sqlalchemy import create_engine

from jobfinder import db


def test_multitenant_validator_reuses_supplied_connection(monkeypatch):
    validation_engine = create_engine("sqlite:///:memory:")
    try:
        with validation_engine.connect() as connection:
            def unexpected_connection():
                pytest.fail("O validador abriu uma segunda conexão pelo engine global.")

            monkeypatch.setattr(db.engine, "connect", unexpected_connection)

            with pytest.raises(RuntimeError, match="tabela user_sessions ausente"):
                db.validate_multitenant_schema(connection)
    finally:
        validation_engine.dispose()
