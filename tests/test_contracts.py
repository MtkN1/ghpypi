from pathlib import Path

import pytest

from ghpypi import (
    ArtifactReference,
    GitHubGateway,
    IndexRenderer,
    IndexWriter,
    PackageIndex,
    ReleaseSnapshot,
    ReleaseSnapshots,
    ReleaseTag,
    RenderedIndex,
    RepositoryIdentity,
    RepositoryName,
    SnapshotStore,
)


class PackageIndexUseCase:
    """A typed sketch of the update flow from the architecture document."""

    def __init__(
        self,
        *,
        github: GitHubGateway,
        snapshot_store: SnapshotStore,
        renderer: IndexRenderer,
        writer: IndexWriter,
    ) -> None:
        self._github = github
        self._snapshot_store = snapshot_store
        self._renderer = renderer
        self._writer = writer

    def update(
        self,
        repository: RepositoryName,
        tag: ReleaseTag,
        artifact_ref: ArtifactReference,
        output_dir: Path,
    ) -> None:
        repository_identity = self._github.get_repository(repository)
        release = self._github.get_release(repository, tag)
        snapshots = self._snapshot_store.load(artifact_ref)
        snapshots.verify_repository(repository_identity)
        updated_snapshots = snapshots.replace(tag, release)
        rendered_index = self._renderer.render(updated_snapshots)
        self._snapshot_store.save(artifact_ref, updated_snapshots)
        self._writer.write(rendered_index, output_dir)


class PendingGitHubGateway:
    def get_repository(self, repository: RepositoryName) -> RepositoryIdentity:
        raise NotImplementedError

    def get_release(
        self, repository: RepositoryName, tag: ReleaseTag
    ) -> ReleaseSnapshot:
        raise NotImplementedError


class PendingSnapshotStore:
    def load(self, artifact_ref: ArtifactReference) -> ReleaseSnapshots:
        raise NotImplementedError

    def save(
        self, artifact_ref: ArtifactReference, snapshots: ReleaseSnapshots
    ) -> None:
        raise NotImplementedError


class PendingIndexRenderer:
    def render(self, snapshots: ReleaseSnapshots) -> RenderedIndex:
        raise NotImplementedError


class PendingIndexWriter:
    def write(self, index: RenderedIndex, output_dir: Path) -> None:
        raise NotImplementedError


@pytest.fixture
def github_gateway() -> GitHubGateway:
    return PendingGitHubGateway()


@pytest.fixture
def snapshot_store() -> SnapshotStore:
    return PendingSnapshotStore()


@pytest.fixture
def index_renderer() -> IndexRenderer:
    return PendingIndexRenderer()


@pytest.fixture
def index_writer() -> IndexWriter:
    return PendingIndexWriter()


def test_typed_update_use_case_stops_at_an_unimplemented_boundary(
    github_gateway: GitHubGateway,
    snapshot_store: SnapshotStore,
    index_renderer: IndexRenderer,
    index_writer: IndexWriter,
) -> None:
    package_index: PackageIndex = PackageIndexUseCase(
        github=github_gateway,
        snapshot_store=snapshot_store,
        renderer=index_renderer,
        writer=index_writer,
    )

    with pytest.raises(NotImplementedError):
        package_index.update(
            repository="owner/example",
            tag="v1.0.0",
            artifact_ref="ghcr.io/owner/ghpypi/example:latest",
            output_dir=Path("site/simple"),
        )
