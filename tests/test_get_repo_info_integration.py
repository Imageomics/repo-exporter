"""
Integration test for gh_repo_exporter.get_repo_info().

Builds a mocked GitHub Repository object (no network calls) and checks
get_repo_info() against a frozen "golden" expected dict, so that
refactoring (splitting modules, moving into src/repo_exporter, etc.)
doesn't silently change the exported data.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from github import GithubException

import gh_repo_exporter as exporter


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
    """Build a MagicMock that mimics a PyGithub Repository object."""
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


def test_get_repo_info_matches_expected_output():
    """Golden test: a fully-populated repo should produce this exact row."""
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

    result = exporter.get_repo_info(repo, existing_df=None)

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
    """A repo missing optional files/links should yield 'No'/'N/A' fallbacks
    (and have the same set of keys as the full repo)."""
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
    )
    repo.get_license.side_effect = GithubException(404, "Not Found", None)

    result = exporter.get_repo_info(repo, existing_df=None)

    assert result["Description"] == "N/A"
    assert result["License"] == "No"
    assert result[".gitignore"] == "No"
    assert result["Package Requirements"] == "No"
    assert result["CITATION"] == "No"
    assert result["Language"] == "N/A"
    assert result["Visibility"] == "Private"
    assert result["Has Forks"] == "No"
    assert result["Website Reference"] == "No"
    assert result["Dataset"] == "No"
    assert result["Model"] == "No"
    assert result["Paper Association"] == "No"
    assert result["DOI for GitHub Repo"] == "No"


def test_get_repo_info_forked_and_archived_repo():
    """Intermediate case: a public, non-bare repo that is also a fork and
    archived. Keeps 'Is Fork' / 'Archived' isolated from the bare/private
    repo's edge cases."""
    repo = make_mock_repo(
        name="forked-archived-project",
        readme_content=FULL_README,
        files={
            ".gitignore": "*.pyc",
            "requirements.txt": "pandas\n",
        },
        fork=True,
        archived=True,
    )
    repo.get_license.side_effect = GithubException(404, "Not Found", None)

    result = exporter.get_repo_info(repo, existing_df=None)

    assert result["Visibility"] == "Public"
    assert result["Is Fork"] == "Yes"
    assert result["Archived"] == "Yes"
    # Sanity check the rest of the row is still populated normally.
    assert result["README"] == "Yes"
    assert result["Dataset"] == '=HYPERLINK("https://huggingface.co/datasets/imageomics/cool-data", "Yes")'
    assert result["Model"] == '=HYPERLINK("https://huggingface.co/imageomics/cool-model", "Yes")'
    assert result["Paper Association"] == '=HYPERLINK("https://arxiv.org/abs/1234.5678", "Yes")'
    # Files/citation not provided to this repo should report "No".
    assert result["License"] == "No"
    assert result["CITATION"] == "No"
    assert result[".zenodo.json"] == "No"
    assert result["CONTRIBUTING"] == "No"
    assert result["AGENTS"] == "No"
    assert result["DOI for GitHub Repo"] == "No"