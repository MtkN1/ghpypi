"""Interfaces and domain types shared by the update workflow and its adapters."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
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

    def __post_init__(self) -> None:
        """Validate, copy, and freeze the rendered file mapping."""
        for relative_path in self.files:
            path = Path(relative_path)
            if path == Path() or path.is_absolute() or ".." in path.parts:
                msg = f"rendered file path must stay within the output directory: {relative_path!r}"
                raise ValueError(msg)
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))


@dataclass(frozen=True, slots=True)
class ReleaseSnapshots:
    """An immutable collection of one repository's release snapshots."""

    repository: RepositoryIdentity
    releases: Mapping[ReleaseTag, ReleaseSnapshot]

    def __post_init__(self) -> None:
        """Copy and freeze the release mapping."""
        object.__setattr__(self, "releases", MappingProxyType(dict(self.releases)))

    @classmethod
    def empty(cls, repository: RepositoryIdentity) -> Self:
        """Create an empty snapshot collection for *repository*."""
        return cls(repository=repository, releases={})

    def verify_repository(self, repository: RepositoryIdentity) -> None:
        """Verify that *repository* identifies this collection's repository."""
        if self.repository != repository:
            msg = (
                "snapshot repository does not match requested repository: "
                f"{self.repository!r} != {repository!r}"
            )
            raise ValueError(msg)

    def replace(self, tag: ReleaseTag, snapshot: ReleaseSnapshot) -> Self:
        """Return a collection in which *tag* refers to *snapshot*."""
        return type(self)(
            repository=self.repository,
            releases={**self.releases, tag: snapshot},
        )


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

    def load(self, artifact_ref: ArtifactReference) -> ReleaseSnapshots | None:
        """Load snapshots, or return ``None`` when the artifact does not exist."""
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
