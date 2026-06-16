"""
Integration test for hf_repo_exporter.get_repo_info().

Builds mocked Hugging Face repo and API objects (no network calls) and checks
get_repo_info() against a frozen "golden" expected dict, so that
refactoring (splitting modules, moving into src/repo-exporter, etc.)
doesn't silently change the exported data.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, mock_open, patch

import pytest
import hf_repo_exporter as exporter

# Freeze "now" so the exported "Inactive" field is deterministic.
_FIXED_NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)

@pytest.fixture(autouse=True)
def _freeze_exporter_now(monkeypatch):
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return _FIXED_NOW.replace(tzinfo=None)
            return _FIXED_NOW.astimezone(tz)
    monkeypatch.setattr(exporter, "datetime", _FixedDateTime)

class FakeAuthor:
    def __init__(self, user: str):
        self.user = user


class FakeCommit:
    def __init__(self, user: str):
        self.authors = [FakeAuthor(user)]


class FakeDiscussion:
    def __init__(self, *, is_pull_request: bool, status: str):
        self.is_pull_request = is_pull_request
        self.status = status


def make_mock_repo(
    *,
    repo_id="imageomics/cool-dataset",
    description="A cool research dataset",
    created_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
    last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
    private=False,
    likes=42,
    card_data=None,
    tags=None,
    doi_attr=None,
):
    """Build a MagicMock that mimics a huggingface_hub repo info object."""
    if last_modified is None:
        last_modified = datetime.now(timezone.utc) - timedelta(days=3)

    repo = MagicMock()
    repo.id = repo_id
    repo.created_at = created_at
    repo.lastModified = last_modified
    repo.private = private
    repo.likes = likes
    repo.tags = tags if tags is not None else []
    repo.doi = doi_attr
    # Explicitly set to None so get_license() doesn't pick up a truthy MagicMock
    repo.license = None

    _card_data = card_data if card_data is not None else {"license": "mit", "description": description}
    repo.cardData = _card_data
    repo.card_data = _card_data

    return repo


def make_mock_api(
    *,
    commits=None,
    open_pr_count=1,
    associated_spaces=None,
    associated_models=None,
):
    """Build a MagicMock that mimics a HfApi object for the functions under test."""
    api = MagicMock()

    # Newest commit first, oldest last — get_author uses commits[-1] for the creator,
    # so janedoe must be last. get_top_contributors iterates all commits in order, so
    # with equal commit counts Counter preserves insertion order: jsmith comes first.
    api.list_repo_commits.return_value = commits if commits is not None else [
        FakeCommit("jsmith"),
        FakeCommit("janedoe"),
    ]

    fake_prs = [FakeDiscussion(is_pull_request=True, status="open")] * open_pr_count
    api.get_repo_discussions.return_value = fake_prs

    api.list_spaces.return_value = (
        [MagicMock(id=s) for s in associated_spaces] if associated_spaces is not None else []
    )
    api.list_models.return_value = (
        [MagicMock(id=m) for m in associated_models] if associated_models is not None else []
    )

    return api

FULL_README = """\
---
license: mit
---

# Cool Dataset

Homepage: https://example.org/cool-dataset
Repository: https://github.com/Imageomics/cool-dataset
Paper: https://arxiv.org/abs/1234.5678
"""


def test_get_repo_info_matches_expected_output():
    """Golden test: a fully-populated dataset repo should produce this exact row."""
    repo = make_mock_repo(
        tags=["dataset:imageomics/cool-data", "doi:10.57967/hf.1234567"],
    )
    api = make_mock_api(
        open_pr_count=2,
        associated_spaces=["imageomics/cool-space"],
    )

    with patch("hf_repo_exporter.hf_hub_download", return_value="/fake/README.md"), \
         patch("builtins.open", mock_open(read_data=FULL_README)):
        result = exporter.get_repo_info(api, repo, "dataset")

    expected = {
        "Repository Name": '=HYPERLINK("https://huggingface.co/datasets/imageomics/cool-dataset", "datasets/imageomics/cool-dataset")',
        "Repository Type": "dataset",
        "Description": "A cool research dataset",
        "Date Created": "2022-01-01",
        "Last Updated": "2026-01-01",
        "Created By": "janedoe",
        "Top 4 Contributors/Curators": "jsmith, janedoe",
        "Likes": 42,
        "# of Open PRs": 2,
        "README": "Yes",
        "License": "mit",
        "Visibility": "Public",
        "Inactive": "No",
        "Homepage": '=HYPERLINK("https://example.org/cool-dataset", "https://example.org/cool-dataset")',
        "Repo": '=HYPERLINK("https://github.com/Imageomics/cool-dataset", "https://github.com/Imageomics/cool-dataset")',
        "Paper": '=HYPERLINK("https://arxiv.org/abs/1234.5678", "https://arxiv.org/abs/1234.5678")',
        "Associated Datasets": "imageomics/cool-data",
        "Associated Models": "No",
        "Associated Spaces": "imageomics/cool-space",
        "DOI": "10.57967/hf.1234567",
    }

    assert result == expected


def test_get_repo_info_minimal_repo_defaults_to_no_or_na():
    """A repo missing optional metadata/links should yield 'No'/'N/A' fallbacks."""
    repo = make_mock_repo(
        repo_id="imageomics/bare-repo",
        description=None,
        # Recent enough that is_inactive() returns "No" (within the last year)
        last_modified=datetime(2025, 12, 1, tzinfo=timezone.utc),
        private=True,
        likes=0,
        card_data={},
        tags=[],
        doi_attr=None,
    )
    api = make_mock_api(
        commits=[],
        open_pr_count=0,
    )

    with patch("hf_repo_exporter.hf_hub_download", return_value="/fake/README.md"), \
         patch("builtins.open", mock_open(read_data="Just a plain readme with nothing special.")):
        result = exporter.get_repo_info(api, repo, "model")

    assert result["Repository Name"] == '=HYPERLINK("https://huggingface.co/imageomics/bare-repo", "imageomics/bare-repo")'
    assert result["Repository Type"] == "model"
    assert result["Description"] == "N/A"
    assert result["Date Created"] == "2022-01-01"
    assert result["Last Updated"] == "2025-12-01"
    assert result["Created By"] == "imageomics"
    assert result["Top 4 Contributors/Curators"] == "imageomics"
    assert result["Likes"] == 0
    assert result["# of Open PRs"] == 0
    assert result["README"] == "No"
    assert result["License"] == "No"
    assert result["Visibility"] == "Private"
    assert result["Inactive"] == "No"
    assert result["Homepage"] == "No"
    assert result["Repo"] == "No"
    assert result["Paper"] == "No"
    assert result["Associated Datasets"] == "No"
    assert result["Associated Models"] == "No"
    assert result["Associated Spaces"] == "No"
    assert result["DOI"] == "No"


def test_get_repo_info_space_type_and_inactive_repo():
    """Intermediate case: a Space repo type that is also inactive (last modified
    over a year ago). Keeps repo_type URL/display logic and Inactive isolated
    from the bare/minimal repo's edge cases."""
    repo = make_mock_repo(
        repo_id="imageomics/cool-space",
        last_modified=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    api = make_mock_api(open_pr_count=0)

    with patch("hf_repo_exporter.hf_hub_download", return_value="/fake/README.md"), \
         patch("builtins.open", mock_open(read_data=FULL_README)):
        result = exporter.get_repo_info(api, repo, "space")

    assert result["Repository Name"] == '=HYPERLINK("https://huggingface.co/spaces/imageomics/cool-space", "spaces/imageomics/cool-space")'
    assert result["Repository Type"] == "space"
    assert result["Description"] == "A cool research dataset"
    assert result["Date Created"] == "2022-01-01"
    assert result["Last Updated"] == "2020-01-01"
    assert result["Created By"] == "janedoe"
    assert result["Top 4 Contributors/Curators"] == "jsmith, janedoe"
    assert result["Likes"] == 42
    assert result["# of Open PRs"] == 0
    assert result["README"] == "Yes"
    assert result["License"] == "mit"
    assert result["Visibility"] == "Public"
    assert result["Inactive"] == "Yes"
    assert result["Homepage"] == '=HYPERLINK("https://example.org/cool-dataset", "https://example.org/cool-dataset")'
    assert result["Repo"] == '=HYPERLINK("https://github.com/Imageomics/cool-dataset", "https://github.com/Imageomics/cool-dataset")'
    assert result["Paper"] == '=HYPERLINK("https://arxiv.org/abs/1234.5678", "https://arxiv.org/abs/1234.5678")'
    assert result["Associated Datasets"] == "No"
    assert result["Associated Models"] == "No"
    assert result["Associated Spaces"] == "No"
    assert result["DOI"] == "No"