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


def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(**over):
    now = int(time.time())
    claims = {"sub": "user_1", "iss": ISSUER, "azp": ORIGIN, "iat": now, "nbf": now - 1, "exp": now + 300}
    claims.update(over)
    return {k: v for k, v in claims.items() if v is not None}


def _assert_clean(err):
    """No chained exception (its text could carry token details) reaches a log."""
    assert err.value.__cause__ is None and err.value.__suppress_context__ is True


def test_alg_none_rejected(verifier):
    import json

    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    token = f"{header}.{_b64(json.dumps(_claims()).encode())}."
    with pytest.raises(AuthError) as err:
        verifier.verify(token)
    _assert_clean(err)


def test_hs256_signed_with_the_public_key_rejected(verifier, key):
    """Algorithm confusion: an HMAC token keyed with the RSA public key's PEM."""
    import hashlib
    import hmac
    import json

    from cryptography.hazmat.primitives import serialization

    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    signing_input = f"{header}.{_b64(json.dumps(_claims()).encode())}"
    sig = hmac.new(pem, signing_input.encode(), hashlib.sha256).digest()
    with pytest.raises(AuthError) as err:
        verifier.verify(f"{signing_input}.{_b64(sig)}")
    _assert_clean(err)


def test_future_nbf_rejected(verifier, key):
    with pytest.raises(AuthError) as err:
        verifier.verify(make_token(key, nbf=int(time.time()) + 600))
    _assert_clean(err)


@pytest.mark.parametrize("missing", ["exp", "sub"])
def test_missing_required_claim_rejected(verifier, key, missing):
    claims = _claims()
    del claims[missing]
    with pytest.raises(AuthError) as err:
        verifier.verify(jwt.encode(claims, key, algorithm="RS256"))
    _assert_clean(err)


def test_issuer_trailing_slash_is_ignored(key):
    v = ClerkVerifier(ISSUER + "/", ORIGIN, jwks_client=FakeJwks(key))
    assert v.verify(make_token(key)).sub == "user_1"


def test_default_jwks_client_url_and_timeout():
    v = ClerkVerifier(ISSUER + "/", ORIGIN)
    assert v._jwks.uri == f"{ISSUER}/.well-known/jwks.json"
    assert v._jwks.timeout == 5


@pytest.mark.parametrize(
    "body",
    [
        [],
        "just a string",
        {"primary_email_address_id": "idn_2", "email_addresses": [{"id": "idn_2"}]},
        {"primary_email_address_id": "idn_2", "email_addresses": "nope"},
        {"primary_email_address_id": "idn_2", "email_addresses": [{"id": "idn_2", "email_address": 7}]},
    ],
)
async def test_malformed_profile_is_an_auth_error(body):
    with pytest.raises(AuthError):
        await directory(lambda r: httpx.Response(200, json=body)).fetch("user_1")


async def test_http_error_names_the_status_not_the_body():
    with pytest.raises(AuthError) as exc:
        await directory(lambda r: httpx.Response(404, text=f"no such user {SECRET}")).fetch("user_1")
    assert "404" in str(exc.value) and SECRET not in str(exc.value) and "no such" not in str(exc.value)
    assert exc.value.__cause__ is None
