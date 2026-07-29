from collections.abc import Mapping
from pathlib import Path
from typing import Self

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

REPOSITORY = "owner/example"
EXISTING_TAG = "v0.9.0"
TAG = "v1.0.0"
ARTIFACT_REF = "ghcr.io/owner/ghpypi/example:latest"
OUTPUT_DIR = Path("site/simple")

type SnapshotState = dict[ArtifactReference, ReleaseSnapshots]
type OutputState = dict[Path, str]


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


class FakeReleaseSnapshots:
    def __init__(
        self,
        repository: RepositoryIdentity,
        releases: Mapping[ReleaseTag, ReleaseSnapshot],
    ) -> None:
        self._repository = repository
        self._releases = releases

    @property
    def repository(self) -> RepositoryIdentity:
        return self._repository

    @property
    def releases(self) -> Mapping[ReleaseTag, ReleaseSnapshot]:
        return self._releases

    @classmethod
    def empty(cls, repository: RepositoryIdentity) -> Self:
        return cls(repository=repository, releases={})

    def verify_repository(self, repository: RepositoryIdentity) -> None:
        return None

    def replace(self, tag: ReleaseTag, snapshot: ReleaseSnapshot) -> Self:
        return type(self)(
            repository=self.repository,
            releases={**self.releases, tag: snapshot},
        )


class FakeGitHubGateway:
    def __init__(
        self,
        repositories: Mapping[RepositoryName, RepositoryIdentity],
        releases: Mapping[tuple[RepositoryName, ReleaseTag], ReleaseSnapshot],
    ) -> None:
        self._repositories = repositories
        self._releases = releases

    def get_repository(self, repository: RepositoryName) -> RepositoryIdentity:
        return self._repositories[repository]

    def get_release(
        self, repository: RepositoryName, tag: ReleaseTag
    ) -> ReleaseSnapshot:
        return self._releases[repository, tag]


class FakeSnapshotStore:
    def __init__(self, state: SnapshotState) -> None:
        self._state = state

    def load(self, artifact_ref: ArtifactReference) -> ReleaseSnapshots:
        return self._state[artifact_ref]

    def save(
        self, artifact_ref: ArtifactReference, snapshots: ReleaseSnapshots
    ) -> None:
        self._state[artifact_ref] = snapshots


class FakeIndexRenderer:
    def __init__(self, index: RenderedIndex) -> None:
        self._index = index

    def render(self, snapshots: ReleaseSnapshots) -> RenderedIndex:
        return self._index


class FakeIndexWriter:
    def __init__(self, state: OutputState) -> None:
        self._state = state

    def write(self, index: RenderedIndex, output_dir: Path) -> None:
        self._state.update(
            {
                output_dir / relative_path: contents
                for relative_path, contents in index.files.items()
            }
        )


@pytest.fixture
def repository_identity() -> RepositoryIdentity:
    return RepositoryIdentity(id=1, full_name=REPOSITORY)


@pytest.fixture
def existing_snapshot() -> ReleaseSnapshot:
    return ReleaseSnapshot(
        github_api_version="2022-11-28",
        release={"tag_name": EXISTING_TAG},
    )


@pytest.fixture
def release_snapshot() -> ReleaseSnapshot:
    filename = "example_package-1.0.0-py3-none-any.whl"
    return ReleaseSnapshot(
        github_api_version="2022-11-28",
        release={
            "tag_name": TAG,
            "assets": [
                {
                    "name": filename,
                    "browser_download_url": (
                        f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{filename}"
                    ),
                    "size": 1234,
                    "digest": "sha256:0123456789abcdef",
                }
            ],
        },
    )


@pytest.fixture
def rendered_index() -> RenderedIndex:
    filename = "example_package-1.0.0-py3-none-any.whl"
    download_url = f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{filename}"
    return RenderedIndex(
        files={
            "index.html": '<a href="example-package/">example-package</a>\n',
            "example-package/index.html": (
                f'<a href="{download_url}#sha256=0123456789abcdef">{filename}</a>\n'
            ),
        }
    )


@pytest.fixture
def snapshot_state(
    repository_identity: RepositoryIdentity,
    existing_snapshot: ReleaseSnapshot,
) -> SnapshotState:
    snapshots = FakeReleaseSnapshots.empty(repository_identity).replace(
        EXISTING_TAG, existing_snapshot
    )
    return {
        ARTIFACT_REF: snapshots,
    }


@pytest.fixture
def output_state() -> OutputState:
    return {}


@pytest.fixture
def github_gateway(
    repository_identity: RepositoryIdentity,
    release_snapshot: ReleaseSnapshot,
) -> GitHubGateway:
    return FakeGitHubGateway(
        repositories={REPOSITORY: repository_identity},
        releases={(REPOSITORY, TAG): release_snapshot},
    )


@pytest.fixture
def snapshot_store(snapshot_state: SnapshotState) -> SnapshotStore:
    return FakeSnapshotStore(snapshot_state)


@pytest.fixture
def index_renderer(rendered_index: RenderedIndex) -> IndexRenderer:
    return FakeIndexRenderer(rendered_index)


@pytest.fixture
def index_writer(output_state: OutputState) -> IndexWriter:
    return FakeIndexWriter(output_state)


@pytest.fixture
def package_index(
    github_gateway: GitHubGateway,
    snapshot_store: SnapshotStore,
    index_renderer: IndexRenderer,
    index_writer: IndexWriter,
) -> PackageIndex:
    return PackageIndexUseCase(
        github=github_gateway,
        snapshot_store=snapshot_store,
        renderer=index_renderer,
        writer=index_writer,
    )


def test_update_replaces_snapshot_and_writes_index(
    package_index: PackageIndex,
    repository_identity: RepositoryIdentity,
    existing_snapshot: ReleaseSnapshot,
    release_snapshot: ReleaseSnapshot,
    rendered_index: RenderedIndex,
    snapshot_state: SnapshotState,
    output_state: OutputState,
) -> None:
    package_index.update(
        repository=REPOSITORY,
        tag=TAG,
        artifact_ref=ARTIFACT_REF,
        output_dir=OUTPUT_DIR,
    )

    saved_snapshots = snapshot_state[ARTIFACT_REF]
    assert saved_snapshots.repository == repository_identity
    assert saved_snapshots.releases == {
        EXISTING_TAG: existing_snapshot,
        TAG: release_snapshot,
    }
    assert output_state == {
        OUTPUT_DIR / relative_path: contents
        for relative_path, contents in rendered_index.files.items()
    }
