"""
Integration tests for GitHubExporter (src/repo_exporter/github.py).

Mirrors the legacy gh_repo_exporter.py golden tests, but exercises the
class-based GitHubExporter.get_repo_info() and its instance-method helpers
(get_repo_creator, get_top_contributors, is_valid_doi, etc.) so the
refactor into src/repo_exporter/ doesn't silently change the exported data.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest
from github import GithubException

from repo_exporter import base as base_module
from repo_exporter.github import GitHubExporter

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


def make_exporter(**overrides) -> GitHubExporter:
    defaults = dict(
        org_name="imageomics",
        spreadsheet_id="sheet123",
        sheet_name="GH-Repos",
        creds_path="fake.json",
        token=None,
        repo_type=None,
    )
    defaults.update(overrides)
    return GitHubExporter(**defaults)


class FakeContentFile:
    def __init__(self, text: str):
        self.decoded_content = text.encode("utf-8")


class FakeAuthor:
    def __init__(self, name: str, login: str):
        self.name = name
        self.login = login


class FakeWeek:
    def __init__(self, a: int, d: int):
        self.a = a
        self.d = d


class FakeContributorStats:
    def __init__(self, name: str, login: str, additions: int, deletions: int):
        self.author = FakeAuthor(name, login)
        self.weeks = [FakeWeek(additions, deletions)]


def make_mock_repo(
    *,
    name="cool-project",
    description="A cool research project",
    created_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    stars=10,
    branches=3,
    private=False,
    fork=False,
    forks_count=2,
    archived=False,
    homepage="https://example.org/cool-project",
    languages=None,
    readme_content="",
    files=None,
    citation_yaml=None,
    creator=("Jane Doe", "janedoe"),
):
    repo = MagicMock()
    repo.name = name
    repo.description = description
    repo.created_at = created_at
    repo.updated_at = updated_at
    repo.stargazers_count = stars
    repo.private = private
    repo.fork = fork
    repo.forks_count = forks_count
    repo.archived = archived
    repo.homepage = homepage
    repo.html_url = f"https://github.com/Imageomics/{name}"

    branches_mock = MagicMock()
    branches_mock.totalCount = branches
    repo.get_branches.return_value = branches_mock

    repo.get_languages.return_value = (
        languages if languages is not None else {"Python": 1000, "Shell": 10}
    )

    if readme_content is not None:
        repo.get_readme.return_value = FakeContentFile(readme_content)
    else:
        repo.get_readme.side_effect = GithubException(404, "Not Found", None)

    repo.get_license.return_value = MagicMock()

    files = files or {}

    def get_contents(path, *args, **kwargs):
        if path == "CITATION.cff" and citation_yaml is not None:
            return FakeContentFile(citation_yaml)
        if path in files:
            return FakeContentFile(files[path])
        raise GithubException(404, "Not Found", None)

    repo.get_contents.side_effect = get_contents

    name_, login_ = creator
    oldest_commit = MagicMock()
    oldest_commit.author = FakeAuthor(name_, login_)
    commits_mock = MagicMock()
    commits_mock.totalCount = 1
    commits_mock.get_page.return_value = [oldest_commit]
    repo.get_commits.return_value = commits_mock
    repo._requester = MagicMock(per_page=30)

    repo.get_stats_contributors.return_value = [
        FakeContributorStats("Jane Doe", "janedoe", 500, 50),
        FakeContributorStats("John Smith", "jsmith", 200, 20),
    ]

    return repo

def _repo_with_citation(citation_text: str) -> MagicMock:
    """
    Build a minimal mock repo whose get_contents("CITATION.cff") returns
    the given citation text, and raises GithubException for anything else.
    """
    repo = MagicMock()

    def get_contents(path, *args, **kwargs):
        if path == "CITATION.cff":
            return FakeContentFile(citation_text)
        raise GithubException(404, "Not Found", None)

    repo.get_contents.side_effect = get_contents
    return repo

FULL_README = """
# Cool Project

This is a research repo.

[Paper](https://arxiv.org/abs/1234.5678)

Dataset: https://huggingface.co/datasets/imageomics/cool-data
Model: https://huggingface.co/imageomics/cool-model
"""

FULL_CITATION = """
cff-version: 1.2.0
title: Cool Project
doi: 10.5281/zenodo.1234567
"""

# get_repo_info golden tests

def test_get_repo_info_matches_expected_output():
    """Golden test: a fully-populated repo should produce this exact row."""
    exporter = make_exporter()
    repo = make_mock_repo(
        readme_content=FULL_README,
        files={
            ".gitignore": "*.pyc",
            "requirements.txt": "pandas\n",
            ".zenodo.json": "{}",
            "CONTRIBUTING.md": "How to contribute",
            "AGENTS.md": "Agent instructions",
        },
        citation_yaml=FULL_CITATION,
    )

    result = exporter.get_repo_info(repo)

    expected = {
        "Repository Name": '=HYPERLINK("https://github.com/Imageomics/cool-project", "cool-project")',
        "Description": "A cool research project",
        "Date Created": "2022-01-01",
        "Last Updated": "2026-01-01",
        "Created By": "Jane Doe (janedoe)",
        "Top 4 Contributors (lines of code changes)": "Jane Doe (janedoe), John Smith (jsmith)",
        "Stars": 10,
        "# of Branches": 3,
        "README": "Yes",
        "License": "Yes",
        ".gitignore": "Yes",
        "Package Requirements": "Yes",
        "CITATION": "Yes",
        ".zenodo.json": "Yes",
        "CONTRIBUTING": "Yes",
        "AGENTS": "Yes",
        "Language": "Python",
        "Visibility": "Public",
        "Is Fork": "No",
        "Has Forks": 2,
        "Archived": "No",
        "Inactive": "No",
        "Website Reference": '=HYPERLINK("https://example.org/cool-project", "Yes")',
        "Dataset": '=HYPERLINK("https://huggingface.co/datasets/imageomics/cool-data", "Yes")',
        "Model": '=HYPERLINK("https://huggingface.co/imageomics/cool-model", "Yes")',
        "Paper Association": '=HYPERLINK("https://arxiv.org/abs/1234.5678", "Yes")',
        "DOI for GitHub Repo": "https://doi.org/10.5281/zenodo.1234567",
    }

    assert result == expected


def test_get_repo_info_minimal_repo_defaults_to_no_or_na():
    """A repo missing optional files/links should yield 'No'/'N/A' fallbacks."""
    exporter = make_exporter()
    repo = make_mock_repo(
        name="bare-repo",
        description=None,
        homepage=None,
        readme_content="Just a plain readme with nothing special.",
        files={},
        citation_yaml=None,
        languages={},
        forks_count=0,
        private=True,
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    repo.get_license.side_effect = GithubException(404, "Not Found", None)

    result = exporter.get_repo_info(repo)

    assert result["Repository Name"] == '=HYPERLINK("https://github.com/Imageomics/bare-repo", "bare-repo")'
    assert result["Date Created"] == "2022-01-01"
    assert result["Last Updated"] == "2024-01-01"
    assert result["Created By"] == "Jane Doe (janedoe)"
    assert result["Stars"] == 10
    assert result["# of Branches"] == 3
    assert result["Description"] == "N/A"
    assert result["Top 4 Contributors (lines of code changes)"] == "Jane Doe (janedoe), John Smith (jsmith)"
    assert result["README"] == "Yes"
    assert result["License"] == "No"
    assert result[".gitignore"] == "No"
    assert result["Package Requirements"] == "No"
    assert result["CITATION"] == "No"
    assert result[".zenodo.json"] == "No"
    assert result["CONTRIBUTING"] == "No"
    assert result["AGENTS"] == "No"
    assert result["Language"] == "N/A"
    assert result["Visibility"] == "Private"
    assert result["Is Fork"] == "No"
    assert result["Has Forks"] == "No"
    assert result["Archived"] == "No"
    assert result["Inactive"] == "Yes"
    assert result["Website Reference"] == "No"
    assert result["Dataset"] == "No"
    assert result["Model"] == "No"
    assert result["Paper Association"] == "No"
    assert result["DOI for GitHub Repo"] == "No"


def test_get_repo_info_forked_and_archived_repo():
    """Intermediate case: a public, non-bare repo that is also a fork and
    archived. Keeps 'Is Fork' / 'Archived' isolated from the bare/private
    repo's edge cases."""
    exporter = make_exporter()
    repo = make_mock_repo(
        name="forked-archived-project",
        readme_content=FULL_README,
        files={
            ".gitignore": "*.pyc",
            "requirements.txt": "pandas\n",
        },
        fork=True,
        archived=True,
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    repo.get_license.side_effect = GithubException(404, "Not Found", None)

    result = exporter.get_repo_info(repo)

    assert result["Repository Name"] == '=HYPERLINK("https://github.com/Imageomics/forked-archived-project", "forked-archived-project")'
    assert result["Date Created"] == "2022-01-01"
    assert result["Last Updated"] == "2024-01-01"
    assert result["Created By"] == "Jane Doe (janedoe)"
    assert result["Stars"] == 10
    assert result["# of Branches"] == 3
    assert result["Description"] == "A cool research project"
    assert result["Top 4 Contributors (lines of code changes)"] == "Jane Doe (janedoe), John Smith (jsmith)"
    assert result["README"] == "Yes"
    assert result["License"] == "No"
    assert result[".gitignore"] == "Yes"
    assert result["Package Requirements"] == "Yes"
    assert result["CITATION"] == "No"
    assert result[".zenodo.json"] == "No"
    assert result["CONTRIBUTING"] == "No"
    assert result["AGENTS"] == "No"
    assert result["Visibility"] == "Public"
    assert result["Is Fork"] == "Yes"
    assert result["Has Forks"] == 2
    assert result["Archived"] == "Yes"
    assert result["Inactive"] == "Yes"
    assert result["Website Reference"] == '=HYPERLINK("https://example.org/cool-project", "Yes")'
    assert result["Dataset"] == '=HYPERLINK("https://huggingface.co/datasets/imageomics/cool-data", "Yes")'
    assert result["Model"] == '=HYPERLINK("https://huggingface.co/imageomics/cool-model", "Yes")'
    assert result["Paper Association"] == '=HYPERLINK("https://arxiv.org/abs/1234.5678", "Yes")'
    assert result["DOI for GitHub Repo"] == "No"


# get_repo_creator (cache hit / fallback paths)

def _make_repo_for_creator(name: str, created_at_str: str) -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.created_at = datetime.strptime(created_at_str, "%Y-%m-%d")
    return repo


def _make_commits_mock(author_name: str, author_login: str, total: int = 1) -> MagicMock:
    commits = MagicMock()
    commits.totalCount = total
    author = MagicMock()
    author.name = author_name
    author.login = author_login
    commit = MagicMock()
    commit.author = author
    commits.get_page.return_value = [commit]
    return commits


def test_get_repo_creator_returns_cached_value_when_repo_in_sheet():
    exporter = make_exporter()
    exporter.existing_df = pd.DataFrame([
        {"Repository Name": "my-repo", "Date Created": "2024-03-01", "Created By": "Alice (alice)"},
    ])
    repo = _make_repo_for_creator("my-repo", "2024-03-01")

    result = exporter.get_repo_creator(repo)

    assert result == "Alice (alice)"
    repo.get_commits.assert_not_called()


def test_get_repo_creator_skips_cache_when_creator_is_na_string():
    exporter = make_exporter()
    exporter.existing_df = pd.DataFrame([
        {"Repository Name": "my-repo", "Date Created": "2024-03-01", "Created By": "N/A"},
    ])
    repo = _make_repo_for_creator("my-repo", "2024-03-01")
    commits = _make_commits_mock("Carol", "carol99")
    repo.get_commits.return_value = commits
    repo._requester = MagicMock(per_page=30)

    result = exporter.get_repo_creator(repo)

    assert result == "Carol (carol99)"
    
def test_get_repo_creator_skips_cache_when_creator_is_nan():
    exporter = make_exporter()
    exporter.existing_df = pd.DataFrame([
        {"Repository Name": "my-repo", "Date Created": "2024-03-01", "Created By": float("nan")},
    ])
    repo = _make_repo_for_creator("my-repo", "2024-03-01")
    commits = _make_commits_mock("Dave", "dave42")
    repo.get_commits.return_value = commits
    repo._requester = MagicMock(per_page=30)

    result = exporter.get_repo_creator(repo)

    assert result == "Dave (dave42)"


def test_get_repo_creator_falls_back_to_commits_when_not_in_sheet():
    exporter = make_exporter()
    exporter.existing_df = pd.DataFrame([
        {"Repository Name": "other-repo", "Date Created": "2024-03-01", "Created By": "Eve (eve)"},
    ])
    repo = _make_repo_for_creator("my-repo", "2024-03-01")
    commits = _make_commits_mock("Frank", "frankdev")
    repo.get_commits.return_value = commits
    repo._requester = MagicMock(per_page=30)

    result = exporter.get_repo_creator(repo)

    assert result == "Frank (frankdev)"
    repo.get_commits.assert_called()

def test_get_repo_creator_falls_back_when_existing_df_missing_columns():
    exporter = make_exporter()
    exporter.existing_df = pd.DataFrame([{"Repo": "my-repo", "Created": "2024-03-01"}])
    repo = _make_repo_for_creator("my-repo", "2024-03-01")
    commits = _make_commits_mock("Henry", "henry99")
    repo.get_commits.return_value = commits
    repo._requester = MagicMock(per_page=30)

    result = exporter.get_repo_creator(repo)

    assert result == "Henry (henry99)"
    repo.get_commits.assert_called()
    
def test_get_repo_creator_falls_back_when_existing_df_empty():
    exporter = make_exporter()
    exporter.existing_df = pd.DataFrame(columns=["Repository Name", "Date Created", "Created By"])
    repo = _make_repo_for_creator("brand-new-repo", "2024-06-01")
    commits = _make_commits_mock("Grace", "grace")
    repo.get_commits.return_value = commits
    repo._requester = MagicMock(per_page=30)

    result = exporter.get_repo_creator(repo)

    assert result == "Grace (grace)"


def test_get_repo_creator_returns_na_when_no_commits():
    exporter = make_exporter()
    repo = _make_repo_for_creator("empty-repo", "2024-01-01")
    commits = MagicMock()
    commits.totalCount = 0
    repo.get_commits.return_value = commits

    result = exporter.get_repo_creator(repo)

    assert result == "N/A"


def test_get_repo_creator_returns_na_when_commit_author_is_none():
    exporter = make_exporter()
    repo = _make_repo_for_creator("ghost-repo", "2024-01-01")
    commits = MagicMock()
    commits.totalCount = 1
    commit = MagicMock()
    commit.author = None
    commits.get_page.return_value = [commit]
    repo.get_commits.return_value = commits
    repo._requester = MagicMock(per_page=30)

    result = exporter.get_repo_creator(repo)

    assert result == "N/A"


def test_get_repo_creator_correct_last_page_index_is_requested():
    exporter = make_exporter()
    total, per_page = 95, 30
    repo = _make_repo_for_creator("my-repo", "2024-03-01")
    commits = _make_commits_mock("Dave", "dave", total=total)
    repo.get_commits.return_value = commits
    repo._requester = MagicMock(per_page=per_page)

    result = exporter.get_repo_creator(repo)

    assert result == "Dave (dave)"
    expected_page = (total - 1) // per_page  # = 3
    commits.get_page.assert_called_once_with(expected_page)


# is_valid_doi / has_doi

def test_is_valid_doi_accepts_zenodo_doi():
    exporter = make_exporter()
    assert exporter.is_valid_doi("10.5281/zenodo.1234567") is True


def test_is_valid_doi_rejects_non_zenodo_doi():
    exporter = make_exporter()
    assert exporter.is_valid_doi("10.1000/abc123") is False


def test_is_valid_doi_rejects_malformed_doi():
    exporter = make_exporter()
    assert exporter.is_valid_doi("not-a-doi") is False


def test_is_valid_doi_rejects_none_and_non_string():
    exporter = make_exporter()
    assert exporter.is_valid_doi(None) is False
    assert exporter.is_valid_doi(12345) is False


# get_website_reference / get_dataset / get_model / get_associated_paper

def test_get_website_reference_returns_hyperlink_for_real_site():
    exporter = make_exporter()
    result = exporter.get_website_reference("https://example.org/my-project")
    assert result == '=HYPERLINK("https://example.org/my-project", "Yes")'


def test_get_website_reference_rejects_external_platform_links():
    exporter = make_exporter()
    assert exporter.get_website_reference("https://arxiv.org/abs/1234") == "No"
    assert exporter.get_website_reference("https://huggingface.co/imageomics/model") == "No"
    assert exporter.get_website_reference(None) == "No"


def test_get_dataset_finds_huggingface_dataset_link():
    exporter = make_exporter()
    readme = "dataset: https://huggingface.co/datasets/imageomics/cool-data"
    result = exporter.get_dataset(readme, "cool-project")
    assert result == '=HYPERLINK("https://huggingface.co/datasets/imageomics/cool-data", "Yes")'


def test_get_dataset_returns_no_when_missing():
    exporter = make_exporter()
    assert exporter.get_dataset("no links here", "cool-project") == "No"


def test_get_model_finds_huggingface_model_link():
    exporter = make_exporter()
    readme = "model: https://huggingface.co/imageomics/cool-model"
    result = exporter.get_model(readme)
    assert result == '=HYPERLINK("https://huggingface.co/imageomics/cool-model", "Yes")'


def test_get_associated_paper_finds_arxiv_link():
    exporter = make_exporter()
    readme = "[Paper](https://arxiv.org/abs/1234.5678)"
    result = exporter.get_associated_paper(readme)
    assert result == '=HYPERLINK("https://arxiv.org/abs/1234.5678", "Yes")'


def test_get_associated_paper_falls_back_to_homepage():
    exporter = make_exporter()
    result = exporter.get_associated_paper("no paper link here", homepage="https://arxiv.org/abs/9999")
    assert result == '=HYPERLINK("https://arxiv.org/abs/9999", "Yes")'
    
def test_has_doi_falls_back_to_readme_badge_when_no_citation_doi():
    exporter = make_exporter()
    repo = _repo_with_citation("title: Test\nversion: 1.0.0\n")
    readme = (
        "[![DOI](https://zenodo.org/badge/647846144.svg)]"
        "(https://doi.org/10.5281/zenodo.16755893)"
    )
    assert exporter.has_doi(repo, readme) == "https://doi.org/10.5281/zenodo.16755893"


def test_has_doi_prefers_citation_doi_over_badge():
    exporter = make_exporter()
    citation = 'title: Test\ndoi: "10.5281/zenodo.11288083"\n'
    repo = _repo_with_citation(citation)
    readme = (
        "[![DOI](https://zenodo.org/badge/999.svg)]"
        "(https://doi.org/10.5281/zenodo.99999999)"
    )
    assert exporter.has_doi(repo, readme) == "https://doi.org/10.5281/zenodo.11288083"


def test_has_doi_no_citation_and_no_badge_returns_no():
    exporter = make_exporter()
    repo = MagicMock()
    repo.get_contents.side_effect = GithubException(404, "Not Found", None)
    assert exporter.has_doi(repo, "no badge here") == "No"