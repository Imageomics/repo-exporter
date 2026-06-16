"""
Integration test for hf_repo_exporter.get_repo_info().

Builds mocked HuggingFace repo and API objects (no network calls) and checks
get_repo_info() against a frozen "golden" expected dict, so that
refactoring (splitting modules, moving into src/repo_exporter, etc.)
doesn't silently change the exported data.
"""

<<<<<<< Updated upstream
from datetime import datetime, timezone
from unittest.mock import MagicMock
=======
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, mock_open, patch
>>>>>>> Stashed changes

import hf_repo_exporter as exporter


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
<<<<<<< Updated upstream
    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    stars=10,
    branches=3,
=======
    last_modified=None,
>>>>>>> Stashed changes
    private=False,
    likes=42,
    card_data=None,
    tags=None,
    doi_attr=None,
):
<<<<<<< Updated upstream
    """Build a MagicMock that mimics a PyGithub Repository object."""
=======
    """Build a MagicMock that mimics a huggingface_hub repo info object."""
    if last_modified is None:
        last_modified = datetime.now(timezone.utc) - timedelta(days=3)

>>>>>>> Stashed changes
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


# extract_link_from_text uses content.split('(')[0].strip() or label for the display
# text. With "Label: https://url" format (no parentheses), the URL itself is the
# display text since split('(')[0] returns the full URL which is truthy.
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
        tags=["dataset:imageomics/cool-data", "doi:10.5281/zenodo.1234567"],
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
<<<<<<< Updated upstream
        "Last Updated": "2026-01-01",
        "Created By": "Jane Doe (janedoe)",
        "Top 4 Contributors (lines of code changes)": "Jane Doe (janedoe), John Smith (jsmith)",
        "Stars": 10,
        "# of Branches": 3,
=======
        "Last Updated": repo.lastModified.strftime("%Y-%m-%d"),
        "Created By": "janedoe",
        "Top 4 Contributors/Curators": "jsmith, janedoe",
        "Likes": 42,
        "# of Open PRs": 2,
>>>>>>> Stashed changes
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
        "DOI": "10.5281/zenodo.1234567",
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
<<<<<<< Updated upstream
=======
        likes=0,
        card_data={},
        tags=[],
        doi_attr=None,
    )
    api = make_mock_api(
        commits=[],
        open_pr_count=0,
>>>>>>> Stashed changes
    )

    with patch("hf_repo_exporter.hf_hub_download", return_value="/fake/README.md"), \
         patch("builtins.open", mock_open(read_data="Just a plain readme with nothing special.")):
        result = exporter.get_repo_info(api, repo, "model")

<<<<<<< Updated upstream
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
    assert result["Has Forks"] == "No"
    assert result["Archived"] == "No"
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

    assert result["Description"] == "A cool research project"
    assert result["Top 4 Contributors (lines of code changes)"] == "Jane Doe (janedoe), John Smith (jsmith)"
    assert result["README"] == "Yes"
=======
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
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
    assert result["Is Fork"] == "Yes"
    assert result["Has Forks"] == 2
    assert result["Archived"] == "Yes"
    assert result["Website Reference"] == '=HYPERLINK("https://example.org/cool-project", "Yes")'
    assert result["Dataset"] == '=HYPERLINK("https://huggingface.co/datasets/imageomics/cool-data", "Yes")'
    assert result["Model"] == '=HYPERLINK("https://huggingface.co/imageomics/cool-model", "Yes")'
    assert result["Paper Association"] == '=HYPERLINK("https://arxiv.org/abs/1234.5678", "Yes")'
    assert result["DOI for GitHub Repo"] == "No"
=======
    assert result["Inactive"] == "Yes"
    assert result["Homepage"] == '=HYPERLINK("https://example.org/cool-dataset", "https://example.org/cool-dataset")'
    assert result["Repo"] == '=HYPERLINK("https://github.com/Imageomics/cool-dataset", "https://github.com/Imageomics/cool-dataset")'
    assert result["Paper"] == '=HYPERLINK("https://arxiv.org/abs/1234.5678", "https://arxiv.org/abs/1234.5678")'
    assert result["Associated Datasets"] == "No"
    assert result["Associated Models"] == "No"
    assert result["Associated Spaces"] == "No"
    assert result["DOI"] == "No"
>>>>>>> Stashed changes
