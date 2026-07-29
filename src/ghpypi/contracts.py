"""Public contracts for the ghpypi update workflow.

This module intentionally defines structure without implementing the update,
rendering, or persistence behavior.  The contracts mirror the components in
the architecture documentation and form the boundary for later adapters.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Self

type RepositoryName = str
"""A GitHub repository name in ``owner/repository`` form."""

type ReleaseTag = str
"""A GitHub Release tag."""

type ArtifactReference = str
"""An OCI artifact reference used by the snapshot store."""

type GitHubAPIVersion = str
"""The GitHub REST API version used to retrieve a release."""

type JSONScalar = None | bool | int | float | str
"""A scalar JSON value."""

type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
"""A value returned in a JSON document."""

type GitHubRelease = dict[str, JSONValue]
"""A raw JSON object returned by GitHub's Release API."""

type RenderedFiles = Mapping[str, str]
"""UTF-8 text files keyed by paths relative to the output directory."""


@dataclass(frozen=True, slots=True)
class RepositoryIdentity:
    """The stable identity recorded for a GitHub repository."""

    id: int
    full_name: RepositoryName


@dataclass(frozen=True, slots=True)
class ReleaseSnapshot:
    """A raw GitHub Release response and the API version that produced it."""

    github_api_version: GitHubAPIVersion
    release: GitHubRelease


@dataclass(frozen=True, slots=True)
class RenderedIndex:
    """A complete, validated Simple Repository API index."""

    files: RenderedFiles


class ReleaseSnapshots(Protocol):
    """The state and replacement operations for one repository's snapshots."""

    @property
    def repository(self) -> RepositoryIdentity:
        """Return the repository recorded by this collection."""
        raise NotImplementedError

    @property
    def releases(self) -> Mapping[ReleaseTag, ReleaseSnapshot]:
        """Return the snapshots keyed by release tag."""
        raise NotImplementedError

    @classmethod
    def empty(cls, repository: RepositoryIdentity) -> Self:
        """Create an empty snapshot collection for *repository*."""
        raise NotImplementedError

    def verify_repository(self, repository: RepositoryIdentity) -> None:
        """Verify that *repository* identifies this collection's repository."""
        raise NotImplementedError

    def replace(self, tag: ReleaseTag, snapshot: ReleaseSnapshot) -> Self:
        """Return a collection in which *tag* refers to *snapshot*."""
        raise NotImplementedError


class GitHubGateway(Protocol):
    """Read repository and release data from GitHub."""

    def get_repository(self, repository: RepositoryName) -> RepositoryIdentity:
        """Return the identity of *repository*."""
        raise NotImplementedError

    def get_release(
        self, repository: RepositoryName, tag: ReleaseTag
    ) -> ReleaseSnapshot:
        """Return the current snapshot for *tag* in *repository*."""
        raise NotImplementedError


class SnapshotStore(Protocol):
    """Load and save repository-scoped release snapshot collections."""

    def load(self, artifact_ref: ArtifactReference) -> ReleaseSnapshots:
        """Load snapshots from *artifact_ref*."""
        raise NotImplementedError

    def save(
        self, artifact_ref: ArtifactReference, snapshots: ReleaseSnapshots
    ) -> None:
        """Save *snapshots* at *artifact_ref*."""
        raise NotImplementedError


class IndexWriter(Protocol):
    """Write a rendered index to an output directory."""

    def write(self, index: RenderedIndex, output_dir: Path) -> None:
        """Write *index* beneath *output_dir*."""
        raise NotImplementedError


class IndexRenderer(Protocol):
    """Render validated Simple Repository API indexes."""

    def render(self, snapshots: ReleaseSnapshots) -> RenderedIndex:
        """Render and validate the complete index for *snapshots*."""
        raise NotImplementedError


class PackageIndex(Protocol):
    """Coordinate repository release-snapshot updates."""

    def update(
        self,
        repository: RepositoryName,
        tag: ReleaseTag,
        artifact_ref: ArtifactReference,
        output_dir: Path,
    ) -> None:
        """Update one release snapshot and write the rebuilt index."""
        raise NotImplementedError
