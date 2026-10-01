"""Resolve a container image reference (e.g. ``ghcr.io/org/name:latest``) to
the immutable digest its tag points at right now, so the tracking dataset
records exactly which image each step ran in rather than a floating tag.

Standard library only: this speaks just enough of the OCI distribution API
(an anonymous bearer token, then a manifest HEAD request) to read the
``Docker-Content-Digest`` header. That covers public images, which is what
every registered image is today. A private image would need credentials
added here.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

DOCKER_HUB_REGISTRY = "registry-1.docker.io"

MANIFEST_MEDIA_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)


@dataclass(frozen=True)
class ImageRef:
    registry: str
    repository: str
    tag: str | None = None
    digest: str | None = None

    @property
    def reference(self) -> str:
        """What to ask the registry for: the digest when pinned, else the tag."""
        return self.digest or self.tag or "latest"

    def pinned(self, *, digest: str) -> str:
        """A ``docker://`` URL for this image, pinned to *digest*."""
        url = f"docker://{self.registry}/{self.repository}@{digest}"
        return url


def parse_image(image: str, /) -> ImageRef:
    """Split *image* into registry, repository, and tag or digest, applying
    Docker's defaults (Docker Hub, the ``library/`` namespace, ``latest``)."""
    remainder = image.removeprefix("docker://")
    digest = None
    if "@" in remainder:
        remainder, digest = remainder.split("@", 1)
    first, _, rest = remainder.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, path = first, rest
    else:
        registry, path = DOCKER_HUB_REGISTRY, remainder
        if "/" not in path:
            path = f"library/{path}"
    tag = None
    name, _, maybe_tag = path.rpartition(":")
    if name and "/" not in maybe_tag:
        path, tag = name, maybe_tag
    if tag is None and digest is None:
        tag = "latest"
    image_ref = ImageRef(registry=registry, repository=path, tag=tag, digest=digest)
    return image_ref


def container_name(image: str, /) -> str:
    """A datalad-container name for *image*: its repository's last path
    component, reduced to the alphanumerics and dashes containers-add
    allows. Named after the image, not the project, since several projects
    may share one image."""
    repository = parse_image(image).repository
    name = re.sub(r"[^0-9a-zA-Z-]+", "-", repository.rsplit("/", 1)[-1]).strip("-")
    return name


def _bearer_token(challenge: str, /) -> str | None:
    params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
    realm = params.pop("realm", None)
    if realm is None:
        return None
    url = f"{realm}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    token = payload.get("token") or payload.get("access_token")
    return token


def resolve_digest(image: str, /) -> str:
    """The ``docker://...@sha256:...`` URL *image* currently resolves to.
    An already-pinned reference is returned as-is, without a network call."""
    ref = parse_image(image)
    if ref.digest is not None:
        return ref.pinned(digest=ref.digest)

    url = f"https://{ref.registry}/v2/{ref.repository}/manifests/{ref.reference}"
    headers = {"Accept": ", ".join(MANIFEST_MEDIA_TYPES)}
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as error:
        challenge = error.headers.get("WWW-Authenticate", "")
        token = _bearer_token(challenge) if error.code == 401 and challenge.startswith("Bearer") else None
        if token is None:
            raise
        headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers, method="HEAD")
        response = urllib.request.urlopen(request, timeout=30)
    with response:
        digest = response.headers["Docker-Content-Digest"]
    pinned = ref.pinned(digest=digest)
    return pinned
