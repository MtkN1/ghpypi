"""Build a PyPI-compatible package registry from GitHub Releases."""

from ._contracts import (
    ArtifactReference,
    GitHubAPIVersion,
    GitHubGateway,
    GitHubRelease,
    IndexWriter,
    JSONScalar,
    JSONValue,
    ReleaseSnapshot,
    ReleaseSnapshots,
    ReleaseTag,
    RenderedFiles,
    RenderedIndex,
    RepositoryIdentity,
    RepositoryName,
    SnapshotStore,
)
from ._index import IndexRenderer, PackageIndex
from ._writer import FilesystemIndexWriter

__all__ = [
    "ArtifactReference",
    "FilesystemIndexWriter",
    "GitHubAPIVersion",
    "GitHubGateway",
    "GitHubRelease",
    "IndexRenderer",
    "IndexWriter",
    "JSONScalar",
    "JSONValue",
    "PackageIndex",
    "ReleaseSnapshot",
    "ReleaseSnapshots",
    "ReleaseTag",
    "RenderedFiles",
    "RenderedIndex",
    "RepositoryIdentity",
    "RepositoryName",
    "SnapshotStore",
]
