from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

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
        if snapshots is None:
            snapshots = ReleaseSnapshots.empty(repository_identity)
        else:
            snapshots.verify_repository(repository_identity)
        updated_snapshots = snapshots.replace(tag, release)
        rendered_index = self._renderer.render(updated_snapshots)
        self._snapshot_store.save(artifact_ref, updated_snapshots)
        self._writer.write(rendered_index, output_dir)


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

    def load(self, artifact_ref: ArtifactReference) -> ReleaseSnapshots | None:
        return self._state.get(artifact_ref)

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
    stale_snapshot: ReleaseSnapshot,
) -> SnapshotState:
    snapshots = ReleaseSnapshots(
        repository=repository_identity,
        releases={
            EXISTING_TAG: existing_snapshot,
            TAG: stale_snapshot,
        },
    )
    return {
        ARTIFACT_REF: snapshots,
    }


@pytest.fixture
def output_state() -> OutputState:
    return {}


@pytest.fixture
def stale_snapshot() -> ReleaseSnapshot:
    return ReleaseSnapshot(
        github_api_version="2022-11-28",
        release={"tag_name": TAG, "name": "stale"},
    )


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


def test_release_snapshots_empty(
    repository_identity: RepositoryIdentity,
) -> None:
    snapshots = ReleaseSnapshots.empty(repository_identity)

    assert snapshots.repository == repository_identity
    assert snapshots.releases == {}


def test_release_snapshots_are_immutable_and_isolated_from_input(
    repository_identity: RepositoryIdentity,
    existing_snapshot: ReleaseSnapshot,
    release_snapshot: ReleaseSnapshot,
) -> None:
    releases = {EXISTING_TAG: existing_snapshot}
    snapshots = ReleaseSnapshots(
        repository=repository_identity,
        releases=releases,
    )

    releases[TAG] = release_snapshot

    assert snapshots.releases == {EXISTING_TAG: existing_snapshot}
    mutable_releases = cast(
        "dict[ReleaseTag, ReleaseSnapshot]",
        snapshots.releases,
    )
    with pytest.raises(TypeError):
        mutable_releases[TAG] = release_snapshot
    repository_attribute = "repository"
    with pytest.raises(FrozenInstanceError):
        setattr(
            snapshots,
            repository_attribute,
            RepositoryIdentity(id=2, full_name="owner/other"),
        )


def test_release_snapshots_verify_matching_repository(
    repository_identity: RepositoryIdentity,
) -> None:
    snapshots = ReleaseSnapshots.empty(repository_identity)

    snapshots.verify_repository(repository_identity)


@pytest.mark.parametrize(
    "repository",
    [
        RepositoryIdentity(id=2, full_name=REPOSITORY),
        RepositoryIdentity(id=1, full_name="owner/renamed"),
    ],
)
def test_release_snapshots_reject_repository_mismatch(
    repository_identity: RepositoryIdentity,
    repository: RepositoryIdentity,
) -> None:
    snapshots = ReleaseSnapshots.empty(repository_identity)

    with pytest.raises(
        ValueError,
        match="snapshot repository does not match requested repository",
    ):
        snapshots.verify_repository(repository)


def test_release_snapshots_replace_returns_new_collection(
    repository_identity: RepositoryIdentity,
    existing_snapshot: ReleaseSnapshot,
    stale_snapshot: ReleaseSnapshot,
    release_snapshot: ReleaseSnapshot,
) -> None:
    snapshots = ReleaseSnapshots(
        repository=repository_identity,
        releases={
            EXISTING_TAG: existing_snapshot,
            TAG: stale_snapshot,
        },
    )

    updated = snapshots.replace(TAG, release_snapshot)

    assert updated is not snapshots
    assert updated.repository == repository_identity
    assert updated.releases == {
        EXISTING_TAG: existing_snapshot,
        TAG: release_snapshot,
    }
    assert snapshots.releases[TAG] is stale_snapshot


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


def test_update_starts_with_empty_snapshots_when_artifact_is_absent(
    github_gateway: GitHubGateway,
    index_renderer: IndexRenderer,
    index_writer: IndexWriter,
    repository_identity: RepositoryIdentity,
    release_snapshot: ReleaseSnapshot,
    rendered_index: RenderedIndex,
    output_state: OutputState,
) -> None:
    snapshot_state: SnapshotState = {}
    package_index = PackageIndexUseCase(
        github=github_gateway,
        snapshot_store=FakeSnapshotStore(snapshot_state),
        renderer=index_renderer,
        writer=index_writer,
    )

    package_index.update(
        repository=REPOSITORY,
        tag=TAG,
        artifact_ref=ARTIFACT_REF,
        output_dir=OUTPUT_DIR,
    )

    saved_snapshots = snapshot_state[ARTIFACT_REF]
    assert saved_snapshots.repository == repository_identity
    assert saved_snapshots.releases == {TAG: release_snapshot}
    assert output_state == {
        OUTPUT_DIR / relative_path: contents
        for relative_path, contents in rendered_index.files.items()
    }


def test_update_rejects_snapshot_for_different_repository(
    github_gateway: GitHubGateway,
    index_renderer: IndexRenderer,
    index_writer: IndexWriter,
    release_snapshot: ReleaseSnapshot,
    output_state: OutputState,
) -> None:
    other_repository = RepositoryIdentity(id=2, full_name="owner/other")
    original_snapshots = ReleaseSnapshots(
        repository=other_repository,
        releases={TAG: release_snapshot},
    )
    snapshot_state = {ARTIFACT_REF: original_snapshots}
    package_index = PackageIndexUseCase(
        github=github_gateway,
        snapshot_store=FakeSnapshotStore(snapshot_state),
        renderer=index_renderer,
        writer=index_writer,
    )

    with pytest.raises(
        ValueError,
        match="snapshot repository does not match requested repository",
    ):
        package_index.update(
            repository=REPOSITORY,
            tag=TAG,
            artifact_ref=ARTIFACT_REF,
            output_dir=OUTPUT_DIR,
        )

    assert snapshot_state == {ARTIFACT_REF: original_snapshots}
    assert output_state == {}
