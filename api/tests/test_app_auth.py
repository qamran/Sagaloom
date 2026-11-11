import pytest
from httpx import ASGITransport, AsyncClient

from sagaloom.config import Settings
from sagaloom.web.app import AppDeps, create_app
from stubs import TOKEN_A, USER_A, FakeDirectory, FakeVerifier, bearer

SECRET = "test-secret"
ORIGIN = "http://localhost:3000"


@pytest.fixture
def client(aclose_later, tmp_path):
    settings = Settings(
        _env_file=None,
        openrouter_api_key="test-key",
        api_shared_secret=SECRET,
        web_origin=ORIGIN,
        data_dir=tmp_path,  # never the developer's api/data/
    )
    app = create_app(settings, AppDeps(verifier=FakeVerifier({TOKEN_A: USER_A}), directory=FakeDirectory()))
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    aclose_later(c)
    return c


async def test_health_needs_no_secret(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_protected_route_rejects_missing_secret(client):
    r = await client.get("/api/worlds")
    assert r.status_code == 401
    assert r.json() == {"detail": "unauthorised"}


async def test_protected_route_rejects_wrong_secret(client):
    r = await client.get("/api/worlds", headers={"X-Sagaloom-Secret": "nope"})
    assert r.status_code == 401


async def test_protected_route_accepts_right_secret(client):
    r = await client.get("/api/worlds", headers={"X-Sagaloom-Secret": SECRET, **bearer()})
    assert r.status_code == 200
    assert r.json() == []


async def test_cors_allows_only_web_origin(client):
    headers = {"Access-Control-Request-Method": "GET"}
    bad = await client.options("/api/worlds", headers={**headers, "Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in bad.headers
    good = await client.options("/api/worlds", headers={**headers, "Origin": ORIGIN})
    assert good.headers["access-control-allow-origin"] == ORIGIN


def test_settings_secrets_do_not_leak_in_repr():
    s = Settings(_env_file=None, openrouter_api_key="sk-LEAK-1", api_shared_secret="shh-LEAK-2")
    assert "LEAK" not in repr(s) and "LEAK" not in str(s)
    assert s.openrouter_api_key.get_secret_value() == "sk-LEAK-1"
