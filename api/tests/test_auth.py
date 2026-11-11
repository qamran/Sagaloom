import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from sagaloom.auth import AuthError, AuthUnavailable, ClerkDirectory, ClerkVerifier

ISSUER = "https://clerk.example.test"
ORIGIN = "http://localhost:3000"
SECRET = "sk_test_supersecretvalue"


class FakeJwks:
    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        class K:
            pass

        k = K()
        k.key = self._key.public_key()
        return k


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(key, **over):
    now = int(time.time())
    claims = {"sub": "user_1", "iss": ISSUER, "azp": ORIGIN, "iat": now, "nbf": now - 1, "exp": now + 300}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def verifier(key):
    return ClerkVerifier(ISSUER, ORIGIN, jwks_client=FakeJwks(key))


def test_valid_token(verifier, key):
    assert verifier.verify(make_token(key)).sub == "user_1"


def test_expired_token_rejected(verifier, key):
    with pytest.raises(AuthError):
        verifier.verify(make_token(key, exp=int(time.time()) - 60))


def test_wrong_issuer_rejected(verifier, key):
    with pytest.raises(AuthError):
        verifier.verify(make_token(key, iss="https://evil.example"))


def test_wrong_azp_rejected(verifier, key):
    with pytest.raises(AuthError):
        verifier.verify(make_token(key, azp="https://evil.example"))


def test_bad_signature_rejected(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        verifier.verify(make_token(other))


def test_missing_azp_accepted(verifier, key):
    assert verifier.verify(make_token(key, azp=None)).sub == "user_1"


def test_garbage_token_rejected(verifier):
    with pytest.raises(AuthError):
        verifier.verify("not-a-jwt")


def directory(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ClerkDirectory(SECRET, http)


def user_json(**over):
    body = {
        "id": "user_1",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "primary_email_address_id": "idn_2",
        "email_addresses": [
            {"id": "idn_1", "email_address": "other@x.test", "verification": {"status": "verified"}},
            {"id": "idn_2", "email_address": "ada@x.test", "verification": {"status": "verified"}},
        ],
    }
    body.update(over)
    return body


async def test_profile_uses_primary_verified_email():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json=user_json())

    p = await directory(handler).fetch("user_1")
    assert (p.email, p.email_verified, p.display_name) == ("ada@x.test", True, "Ada Lovelace")
    assert seen["url"] == "https://api.clerk.com/v1/users/user_1"
    assert seen["auth"] == f"Bearer {SECRET}"


async def test_profile_unverified():
    body = user_json(
        email_addresses=[{"id": "idn_2", "email_address": "ada@x.test", "verification": {"status": "unverified"}}]
    )
    p = await directory(lambda r: httpx.Response(200, json=body)).fetch("user_1")
    assert p.email == "ada@x.test"
    assert p.email_verified is False


async def test_display_name_fallback_to_email_local_part():
    body = user_json(first_name=None, last_name=None)
    p = await directory(lambda r: httpx.Response(200, json=body)).fetch("user_1")
    assert p.display_name == "ada"


async def test_secret_not_in_error_message():
    with pytest.raises(AuthError) as exc:
        await directory(lambda r: httpx.Response(500, text="boom")).fetch("user_1")
    assert SECRET not in str(exc.value)


class UnreachableJwks:
    def get_signing_key_from_jwt(self, token):
        raise jwt.PyJWKClientConnectionError("Fail to fetch data from the url, err: secret-ish detail")


class UnknownKidJwks:
    def get_signing_key_from_jwt(self, token):
        raise jwt.PyJWKClientError("Unable to find a signing key that matches")


def test_unreachable_jwks_is_unavailable_not_invalid(key):
    v = ClerkVerifier(ISSUER, ORIGIN, jwks_client=UnreachableJwks())
    with pytest.raises(AuthUnavailable) as err:
        v.verify(make_token(key))
    assert isinstance(err.value, AuthError) and "detail" not in str(err.value)


def test_unknown_signing_key_is_still_invalid(key):
    v = ClerkVerifier(ISSUER, ORIGIN, jwks_client=UnknownKidJwks())
    with pytest.raises(AuthError) as err:
        v.verify(make_token(key))
    assert not isinstance(err.value, AuthUnavailable)
