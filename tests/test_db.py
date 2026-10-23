import pytest

from ingest import db

ENV = {
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "secret",
    "POSTGRES_DB": "retail",
    "POSTGRES_HOST": "dbhost",
    "POSTGRES_PORT": "6543",
}


def test_get_engine_builds_url_from_env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    url = db.get_engine().url
    assert url.username == "user"
    assert url.password == "secret"
    assert url.host == "dbhost"
    assert url.port == 6543
    assert url.database == "retail"


def test_missing_env_raises(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("POSTGRES_PASSWORD")
    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        db.get_engine()
