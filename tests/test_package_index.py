from collections.abc import Mapping
from pathlib import Path

import pytest
from packaging.utils import InvalidName, InvalidSdistFilename, InvalidWheelFilename

from ghpypi import (
    ArtifactReference,
    FilesystemIndexWriter,
    GitHubGateway,
    IndexRenderer,
    JSONValue,
    PackageIndex,
    ReleaseSnapshot,
    ReleaseSnapshots,
    ReleaseTag,
    RepositoryIdentity,
    RepositoryName,
    SnapshotStore,
)

REPOSITORY = "owner/example"
IDENTITY = RepositoryIdentity(id=1, full_name=REPOSITORY)
ARTIFACT_REF = "ghcr.io/owner/ghpypi/example:latest"
SHA256 = "0123456789abcdef" * 4

type SnapshotState = dict[ArtifactReference, ReleaseSnapshots]


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
        self.state = state

    def load(self, artifact_ref: ArtifactReference) -> ReleaseSnapshots | None:
        return self.state.get(artifact_ref)

    def save(
        self, artifact_ref: ArtifactReference, snapshots: ReleaseSnapshots
    ) -> None:
        self.state[artifact_ref] = snapshots


def _asset(
    name: JSONValue,
    *,
    digest: JSONValue = None,
    size: JSONValue = 123,
    url: JSONValue | None = None,
) -> dict[str, JSONValue]:
    if url is None and isinstance(name, str):
        url = f"https://github.com/{REPOSITORY}/releases/download/v1/{name}"
    return {
        "name": name,
        "browser_download_url": url,
        "size": size,
        "digest": digest,
    }


def _release(*assets: JSONValue) -> ReleaseSnapshot:
    return ReleaseSnapshot(
        github_api_version="2022-11-28",
        release={"assets": list(assets)},
    )


def _package_index(
    releases: Mapping[ReleaseTag, ReleaseSnapshot],
    state: SnapshotState,
) -> PackageIndex:
    github: GitHubGateway = FakeGitHubGateway(
        {REPOSITORY: IDENTITY},
        {(REPOSITORY, tag): release for tag, release in releases.items()},
    )
    store: SnapshotStore = FakeSnapshotStore(state)
    return PackageIndex(
        github=github,
        snapshot_store=store,
        renderer=IndexRenderer(),
        writer=FilesystemIndexWriter(),
    )


def test_update_generates_a_simple_repository(tmp_path: Path) -> None:
    """Rebuild a normalized Simple repository from all release snapshots."""
    old_asset = _asset("Friendly.Bard-1.0.tar.gz")
    old_release = _release(old_asset)
    stale_release = _release()
    new_asset = _asset(
        "friendly_bard-2.0-py3-none-any.whl",
        digest=f"sha256:{SHA256}",
    )
    new_sdist = _asset("friendly-bard-2.0.tar.gz")
    new_release = _release(new_asset, new_sdist, {"name": "release-notes.txt"})
    state = {
        ARTIFACT_REF: ReleaseSnapshots(
            repository=IDENTITY,
            releases={"v1.0.0": old_release, "v2.0.0": stale_release},
        )
    }
    output_dir = tmp_path / "simple"
    output_dir.mkdir()
    (output_dir / "stale.html").write_text("stale", encoding="utf-8")
    package_index = _package_index({"v2.0.0": new_release}, state)

    package_index.update(
        repository=REPOSITORY,
        tag="v2.0.0",
        artifact_ref=ARTIFACT_REF,
        output_dir=output_dir,
    )

    assert state[ARTIFACT_REF].releases == {
        "v1.0.0": old_release,
        "v2.0.0": new_release,
    }
    assert sorted(
        path.relative_to(output_dir) for path in output_dir.rglob("*") if path.is_file()
    ) == [Path("friendly-bard/index.html"), Path("index.html")]
    assert (output_dir / "index.html").read_text(encoding="utf-8") == (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        '    <meta name="pypi:repository-version" content="1.0">\n'
        "    <title>Simple index</title>\n"
        "  </head>\n"
        "  <body>\n"
        '    <a href="friendly-bard/">friendly-bard</a>\n'
        "  </body>\n"
        "</html>\n"
    )
    assert (output_dir / "friendly-bard/index.html").read_text(encoding="utf-8") == (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        '    <meta name="pypi:repository-version" content="1.0">\n'
        "    <title>Links for friendly-bard</title>\n"
        "  </head>\n"
        "  <body>\n"
        f'    <a href="{old_asset["browser_download_url"]}">'
        "Friendly.Bard-1.0.tar.gz</a>\n"
        f'    <a href="{new_sdist["browser_download_url"]}">'
        "friendly-bard-2.0.tar.gz</a>\n"
        f'    <a href="{new_asset["browser_download_url"]}#sha256={SHA256}">'
        "friendly_bard-2.0-py3-none-any.whl</a>\n"
        "  </body>\n"
        "</html>\n"
    )


def test_update_starts_an_empty_repository(tmp_path: Path) -> None:
    """Start with empty snapshots when no artifact has been stored."""
    release = _release()
    state: SnapshotState = {}
    output_dir = tmp_path / "simple"
    package_index = _package_index({"v1.0.0": release}, state)

    package_index.update(
        repository=REPOSITORY,
        tag="v1.0.0",
        artifact_ref=ARTIFACT_REF,
        output_dir=output_dir,
    )

    assert state[ARTIFACT_REF].releases == {"v1.0.0": release}
    assert list(output_dir.iterdir()) == [output_dir / "index.html"]
    assert "<a " not in (output_dir / "index.html").read_text(encoding="utf-8")


def test_update_rejects_snapshots_from_another_repository(tmp_path: Path) -> None:
    """Stop before writing when stored snapshots belong elsewhere."""
    release = _release()
    original = ReleaseSnapshots(
        repository=RepositoryIdentity(id=2, full_name="owner/other"),
        releases={},
    )
    state = {ARTIFACT_REF: original}
    output_dir = tmp_path / "simple"
    package_index = _package_index({"v1.0.0": release}, state)

    with pytest.raises(
        ValueError,
        match="snapshot repository does not match requested repository",
    ):
        package_index.update(
            repository=REPOSITORY,
            tag="v1.0.0",
            artifact_ref=ARTIFACT_REF,
            output_dir=output_dir,
        )

    assert state == {ARTIFACT_REF: original}
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "assets",
    [
        None,
        ["not an object"],
    ],
)
def test_renderer_rejects_invalid_asset_collections(assets: JSONValue) -> None:
    """Reject release assets that are not a list of objects."""
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={
            "v1.0.0": ReleaseSnapshot(
                github_api_version="2022-11-28",
                release={"assets": assets},
            )
        },
    )

    with pytest.raises(ValueError, match="release assets must be a list of objects"):
        IndexRenderer().render(snapshots)


def test_renderer_rejects_an_asset_without_a_string_name() -> None:
    """Reject an asset whose filename cannot be classified."""
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={"v1.0.0": _release(_asset(None))},
    )

    with pytest.raises(TypeError, match="release asset name must be a string"):
        IndexRenderer().render(snapshots)


@pytest.mark.parametrize(
    ("url", "size"),
    [
        (123, 123),
        (
            "https://github.com/owner/example/releases/download/v1/example-1.0.tar.gz",
            "123",
        ),
        (
            "https://github.com/owner/example/releases/download/v1/example-1.0.tar.gz",
            True,
        ),
        (
            "https://github.com/owner/example/releases/download/v1/example-1.0.tar.gz",
            -1,
        ),
    ],
)
def test_renderer_rejects_invalid_distribution_metadata(
    url: JSONValue, size: JSONValue
) -> None:
    """Reject distribution assets without a valid URL and size."""
    asset = _asset("example-1.0.tar.gz", url=url, size=size)
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={"v1.0.0": _release(asset)},
    )

    with pytest.raises(ValueError, match="distribution asset has invalid metadata"):
        IndexRenderer().render(snapshots)


@pytest.mark.parametrize(
    "url",
    [
        "/example-1.0.tar.gz",
        "https://example.com/example-1.0.tar.gz",
    ],
)
def test_renderer_requires_an_absolute_github_url(url: str) -> None:
    """Require every distribution link to target GitHub."""
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={"v1.0.0": _release(_asset("example-1.0.tar.gz", url=url))},
    )

    with pytest.raises(ValueError, match="must be an absolute GitHub URL"):
        IndexRenderer().render(snapshots)


def test_renderer_requires_the_url_filename_to_match() -> None:
    """Keep the link text equal to the URL's final path component."""
    url = f"https://github.com/{REPOSITORY}/releases/download/v1/other-1.0.tar.gz"
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={"v1.0.0": _release(_asset("example-1.0.tar.gz", url=url))},
    )

    with pytest.raises(ValueError, match="URL filename does not match"):
        IndexRenderer().render(snapshots)


@pytest.mark.parametrize(
    "digest",
    [
        123,
        SHA256,
        "sha256:0123",
        f"sha256:{'g' * 64}",
    ],
)
def test_renderer_rejects_invalid_sha256_digests(digest: JSONValue) -> None:
    """Reject malformed GitHub asset digests instead of publishing them."""
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={"v1.0.0": _release(_asset("example-1.0.tar.gz", digest=digest))},
    )

    with pytest.raises(ValueError, match="invalid SHA-256 digest"):
        IndexRenderer().render(snapshots)


@pytest.mark.parametrize(
    ("filename", "error"),
    [
        ("invalid.whl", InvalidWheelFilename),
        ("invalid.tar.gz", InvalidSdistFilename),
    ],
)
def test_renderer_rejects_invalid_distribution_filenames(
    filename: str,
    error: type[ValueError],
) -> None:
    """Reject malformed wheel and source distribution filenames."""
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={"v1.0.0": _release(_asset(filename))},
    )

    with pytest.raises(error):
        IndexRenderer().render(snapshots)


def test_renderer_rejects_invalid_project_names() -> None:
    """Reject project names outside the normalized-name specification."""
    snapshots = ReleaseSnapshots(
        repository=IDENTITY,
        releases={"v1.0.0": _release(_asset("café-1.0.tar.gz"))},
    )

    with pytest.raises(InvalidName):
        IndexRenderer().render(snapshots)


@pytest.mark.parametrize(
    "second_filename",
    [
        "other-1.0.tar.gz",
        "example-2.0.tar.gz",
    ],
)
def test_update_validates_a_release_before_saving_it(
    second_filename: str,
    tmp_path: Path,
) -> None:
    """Keep adapters unchanged when one release mixes distributions."""
    original = ReleaseSnapshots.empty(IDENTITY)
    state = {ARTIFACT_REF: original}
    release = _release(
        _asset("example-1.0.tar.gz"),
        _asset(second_filename),
    )
    output_dir = tmp_path / "simple"
    package_index = _package_index({"v1.0.0": release}, state)

    with pytest.raises(
        ValueError,
        match="same project and version",
    ):
        package_index.update(
            repository=REPOSITORY,
            tag="v1.0.0",
            artifact_ref=ARTIFACT_REF,
            output_dir=output_dir,
        )

    assert state == {ARTIFACT_REF: original}
    assert not output_dir.exists()
