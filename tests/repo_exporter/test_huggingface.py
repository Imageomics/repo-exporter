"""
Integration tests for HuggingFaceExporter (src/repo_exporter/huggingface.py).

Mirrors the legacy hf_repo_exporter.py golden tests, but exercises the
class-based HuggingFaceExporter.get_repo_info() and its instance-method
helpers so the refactor into src/repo_exporter/ doesn't silently change
the exported data.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, mock_open, patch

import pytest

from repo_exporter import base as base_module
from repo_exporter.huggingface import HuggingFaceExporter

# Freeze "now" so the exported "Inactive" field is deterministic.
_FIXED_NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_base_now(monkeypatch):
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return _FIXED_NOW.replace(tzinfo=None)
            return _FIXED_NOW.astimezone(tz)
    monkeypatch.setattr(base_module, "datetime", _FixedDateTime)


def make_exporter(**overrides) -> HuggingFaceExporter:
    defaults = dict(
        org_name="imageomics",
        spreadsheet_id="sheet123",
        sheet_name="HF-Repos",
        creds_path="fake.json",
        token=None,
    )
    defaults.update(overrides)
    return HuggingFaceExporter(**defaults)


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
    repo = MagicMock()
    repo.id = repo_id
    repo.created_at = created_at
    repo.lastModified = last_modified
    repo.private = private
    repo.likes = likes
    repo.tags = tags if tags is not None else []
    repo.doi = doi_attr
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
    repo=None,
):
    """Build a MagicMock that stands in for exporter.api."""
    api = MagicMock()

    # Newest commit first, oldest last — get_author uses commits[-1] for the
    # creator, so janedoe must be last. jsmith has strictly more commits than
    # janedoe to avoid tie-order ambiguity in Counter.most_common().
    api.list_repo_commits.return_value = commits if commits is not None else [
        FakeCommit("jsmith"),
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
    
    if repo is not None:
        api.model_info.return_value = repo   
        api.dataset_info.return_value = repo 
        api.space_info.return_value = repo
        
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

# get_repo_info golden tests

def test_get_repo_info_matches_expected_output():
    """Golden test: a fully-populated dataset repo should produce this exact row."""
    exporter = make_exporter()
    repo = make_mock_repo(
        tags=["dataset:imageomics/cool-data-source", "doi:10.57967/hf/1234567"]
    )
    exporter.api = make_mock_api(
        open_pr_count=2,
        associated_spaces=["imageomics/cool-space"],
        repo=repo,
    )

    with patch("repo_exporter.huggingface.hf_hub_download", return_value="/fake/README.md"), \
         patch("builtins.open", mock_open(read_data=FULL_README)):
        result = exporter.get_repo_info(repo, "dataset")

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
        "Associated Datasets": "imageomics/cool-data-source",
        "Associated Models": "No",
        "Associated Spaces": "imageomics/cool-space",
        "DOI": "10.57967/hf/1234567",
    }

    assert result == expected


def test_get_repo_info_minimal_repo_defaults_to_no_or_na():
    """A repo missing optional metadata/links should yield 'No'/'N/A' fallbacks.

    NOTE: License comes out as "N/A" here, not "No" — get_card_field() returns
    the string "N/A" when nothing matches, and "N/A" or "No" short-circuits to
    "N/A" since it's already truthy. This differs from the old script's
    behavior. Flagging this in case it's not intentional.
    """
    exporter = make_exporter()
    repo = make_mock_repo(
        repo_id="imageomics/bare-repo",
        description=None,
        last_modified=datetime(2025, 12, 1, tzinfo=timezone.utc),
        private=True,
        likes=0,
        card_data={},
        tags=[],
        doi_attr=None,
    )
    exporter.api = make_mock_api(commits=[], open_pr_count=0, repo=repo)

    with patch("repo_exporter.huggingface.hf_hub_download", return_value="/fake/README.md"), \
         patch("builtins.open", mock_open(read_data="Just a plain readme with nothing special.")):
        result = exporter.get_repo_info(repo, "model")

    assert result["Repository Name"] == '=HYPERLINK("https://huggingface.co/imageomics/bare-repo", "imageomics/bare-repo")'
    assert result["Repository Type"] == "model"
    assert result["Description"] == "N/A"
    assert result["Date Created"] == "2022-01-01"
    assert result["Last Updated"] == "2025-12-01"
    assert result["Created By"] == "imageomics"
    assert result["Top 4 Contributors/Curators"] == "imageomics"
    assert result["Likes"] == 0
    assert result["# of Open PRs"] == 0
    assert result["README"] == "Yes"
    assert result["License"] == "N/A"
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
    """Intermediate case: a Space repo type that is also inactive (last
    modified over a year ago). Keeps repo_type URL/display logic and
    Inactive isolated from the bare/minimal repo's edge cases."""
    exporter = make_exporter()
    repo = make_mock_repo(
        repo_id="imageomics/cool-space",
        description="A cool research demo",
        last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    exporter.api = make_mock_api(open_pr_count=0, repo=repo)

    with patch("repo_exporter.huggingface.hf_hub_download", return_value="/fake/README.md"), \
         patch("builtins.open", mock_open(read_data=FULL_README)):
        result = exporter.get_repo_info(repo, "space")

    assert result["Repository Name"] == '=HYPERLINK("https://huggingface.co/spaces/imageomics/cool-space", "spaces/imageomics/cool-space")'
    assert result["Repository Type"] == "space"
    assert result["Description"] == "A cool research demo"
    assert result["Date Created"] == "2022-01-01"
    assert result["Last Updated"] == "2024-01-01"
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


def test_get_repo_info_readme_download_failure_gives_no_readme():
    """If hf_hub_download raises, README/Homepage/Repo/Paper should all
    fall back to 'No' rather than crashing get_repo_info()."""
    exporter = make_exporter()
    repo = make_mock_repo(repo_id="imageomics/no-readme-repo")
    exporter.api = make_mock_api(open_pr_count=0, repo=repo)

    with patch("repo_exporter.huggingface.hf_hub_download", side_effect=Exception("404 Not Found")):
        result = exporter.get_repo_info(repo, "model")

    assert result["README"] == "No"
    assert result["Homepage"] == "No"
    assert result["Repo"] == "No"
    assert result["Paper"] == "No"

# get_doi / get_associated_datasets

def test_get_doi_prefers_direct_attribute():
    exporter = make_exporter()
    repo = make_mock_repo(doi_attr="doi:10.1234/abcd")
    assert exporter.get_doi(repo) == "10.1234/abcd"

def test_get_doi_falls_back_to_tags():
    exporter = make_exporter()
    repo = make_mock_repo(doi_attr=None, card_data={}, tags=["doi:10.5555/xyz"])
    assert exporter.get_doi(repo) == "10.5555/xyz"

def test_get_doi_returns_no_when_missing():
    exporter = make_exporter()
    repo = make_mock_repo(doi_attr=None, card_data={}, tags=[])
    assert exporter.get_doi(repo) == "No"

def test_get_associated_datasets_extracts_dataset_tags():
    exporter = make_exporter()
    repo = make_mock_repo(tags=["dataset:imageomics/data-a", "dataset:imageomics/data-b", "other-tag"])
    assert exporter.get_associated_datasets(repo) == "imageomics/data-a, imageomics/data-b"

def test_get_associated_datasets_returns_no_when_missing():
    exporter = make_exporter()
    repo = make_mock_repo(tags=[])
    assert exporter.get_associated_datasets(repo) == "No"