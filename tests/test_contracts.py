from types import MappingProxyType

import pytest

from ghpypi import (
    ReleaseSnapshot,
    ReleaseSnapshots,
    RenderedIndex,
    RepositoryIdentity,
)

REPOSITORY = RepositoryIdentity(id=1, full_name="owner/example")
SNAPSHOT = ReleaseSnapshot(
    github_api_version="2022-11-28",
    release={"tag_name": "v1.0.0"},
)


def test_empty_release_snapshots_belong_to_repository() -> None:
    """Create an empty immutable collection for one repository."""
    snapshots = ReleaseSnapshots.empty(REPOSITORY)

    assert snapshots.repository == REPOSITORY
    assert snapshots.releases == {}


def test_release_snapshots_copy_the_input_mapping() -> None:
    """Keep later input mutations out of a snapshot collection."""
    releases = {"v1.0.0": SNAPSHOT}
    snapshots = ReleaseSnapshots(repository=REPOSITORY, releases=releases)

    releases.clear()

    assert snapshots.releases == {"v1.0.0": SNAPSHOT}
    assert isinstance(snapshots.releases, MappingProxyType)


def test_release_snapshots_accept_the_same_repository() -> None:
    """Accept the repository identity stored with the snapshots."""
    snapshots = ReleaseSnapshots.empty(REPOSITORY)

    snapshots.verify_repository(REPOSITORY)


@pytest.mark.parametrize(
    "repository",
    [
        RepositoryIdentity(id=2, full_name=REPOSITORY.full_name),
        RepositoryIdentity(id=REPOSITORY.id, full_name="owner/renamed"),
    ],
)
def test_release_snapshots_reject_another_repository(
    repository: RepositoryIdentity,
) -> None:
    """Reject snapshots whose stable repository identity differs."""
    snapshots = ReleaseSnapshots.empty(REPOSITORY)

    with pytest.raises(
        ValueError,
        match="snapshot repository does not match requested repository",
    ):
        snapshots.verify_repository(repository)


def test_replacing_a_release_returns_a_new_collection() -> None:
    """Replace one tag without mutating the original snapshots."""
    stale = ReleaseSnapshot(
        github_api_version="2022-11-28",
        release={"tag_name": "v2.0.0", "name": "stale"},
    )
    current = ReleaseSnapshot(
        github_api_version="2022-11-28",
        release={"tag_name": "v2.0.0", "name": "current"},
    )
    snapshots = ReleaseSnapshots(
        repository=REPOSITORY,
        releases={"v1.0.0": SNAPSHOT, "v2.0.0": stale},
    )

    updated = snapshots.replace("v2.0.0", current)

    assert updated is not snapshots
    assert updated.releases == {"v1.0.0": SNAPSHOT, "v2.0.0": current}
    assert snapshots.releases["v2.0.0"] is stale


def test_rendered_index_copies_the_input_mapping() -> None:
    """Keep later input mutations out of a rendered index."""
    files = {"index.html": "contents"}
    index = RenderedIndex(files)

    files.clear()

    assert index.files == {"index.html": "contents"}
    assert isinstance(index.files, MappingProxyType)


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        "/outside.html",
        "../outside.html",
    ],
)
def test_rendered_index_rejects_paths_outside_output_directory(
    relative_path: str,
) -> None:
    """Reject paths that could write outside the output directory."""
    with pytest.raises(
        ValueError,
        match="rendered file path must stay within the output directory",
    ):
        RenderedIndex({relative_path: "contents"})
