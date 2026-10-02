import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dispatch/

import images  # noqa: E402

pytestmark = pytest.mark.ai_generated


@pytest.mark.parametrize(
    ("image", "registry", "repository", "tag", "digest"),
    [
        ("ghcr.io/brain-bbqs/dandi-cli:latest", "ghcr.io", "brain-bbqs/dandi-cli", "latest", None),
        ("ghcr.io/brain-bbqs/dandi-cli", "ghcr.io", "brain-bbqs/dandi-cli", "latest", None),
        ("docker://ghcr.io/org/x@sha256:abc", "ghcr.io", "org/x", None, "sha256:abc"),
        ("localhost:5000/x:1.0", "localhost:5000", "x", "1.0", None),
        ("python:3.13-slim", "registry-1.docker.io", "library/python", "3.13-slim", None),
        ("someone/tool", "registry-1.docker.io", "someone/tool", "latest", None),
    ],
)
def test_parse_image_applies_docker_defaults(image, registry, repository, tag, digest):
    ref = images.parse_image(image)
    assert (ref.registry, ref.repository, ref.tag, ref.digest) == (registry, repository, tag, digest)


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("ghcr.io/brain-bbqs/kemere-r34da059514-ingest:latest", "kemere-r34da059514-ingest"),
        ("ghcr.io/org/some_image.v2:tag", "some-image-v2"),
    ],
)
def test_container_name_is_safe_for_containers_add(image, expected):
    assert images.container_name(image) == expected


def test_resolve_digest_returns_pinned_reference_without_network(monkeypatch):
    monkeypatch.setattr(images.urllib.request, "urlopen", lambda *a, **k: pytest.fail("no network expected"))
    assert images.resolve_digest("ghcr.io/org/x@sha256:abc") == "docker://ghcr.io/org/x@sha256:abc"


class FakeResponse:
    def __init__(self, *, headers=None, body=b""):
        self.headers = headers or {}
        self._body = body

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_resolve_digest_fetches_an_anonymous_token_on_401(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        requests.append((url, None if isinstance(request, str) else request.get_header("Authorization")))
        if url.startswith("https://ghcr.io/token"):
            return FakeResponse(body=b'{"token": "anon"}')
        if request.get_header("Authorization") is None:
            headers = Message()
            headers["WWW-Authenticate"] = (
                'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:org/x:pull"'
            )
            raise urllib.error.HTTPError(url, 401, "Unauthorized", headers, None)
        return FakeResponse(headers={"Docker-Content-Digest": "sha256:def"})

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    assert images.resolve_digest("ghcr.io/org/x:latest") == "docker://ghcr.io/org/x@sha256:def"
    assert requests[-1] == ("https://ghcr.io/v2/org/x/manifests/latest", "Bearer anon")
