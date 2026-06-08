import unittest
from unittest.mock import MagicMock
import pandas as pd

from gh_repo_exporter import get_repo_creator


class TestGetRepoCreator(unittest.TestCase):
    """
    Tests get_repo_creator() end-to-end with a mocked GitHub repo object
    and an existing_df built from a dummy CSV-style DataFrame.

    Two paths through the function are tested:
      1. Repo IS in existing_df with a valid creator  → return cached value, no API call.
      2. Repo is NOT in existing_df (or has bad data) → fall back to commit history.
    """

    def _make_mock_repo(self, name: str, created_at_str: str) -> MagicMock:
        """
        Build a minimal mock GitHub repo object.
        created_at must be a real datetime because get_repo_creator calls
        repo.created_at.strftime("%Y-%m-%d") to match against the sheet.
        """
        from datetime import datetime
        repo = MagicMock()
        repo.name = name
        repo.created_at = datetime.strptime(created_at_str, "%Y-%m-%d")
        return repo

    def _make_commits_mock(self, author_name: str, author_login: str,
                           total: int = 1, per_page: int = 30) -> MagicMock:
        """
        Build a mock commits object whose get_page() returns a single commit
        with the given author. Used to wire up the API fallback path.
        """
        commits = MagicMock()
        commits.totalCount = total

        author = MagicMock()
        author.name = author_name
        author.login = author_login
        commit = MagicMock()
        commit.author = author
        commits.get_page.return_value = [commit]
        return commits

    def _dummy_existing_df(self, rows: list[dict]) -> pd.DataFrame:
        """
        Build a DataFrame that looks like the three columns loaded from the
        Google Sheet in main() — the same shape get_repo_creator receives.
        Mimics what you'd get from reading a CSV with these columns.
        """
        return pd.DataFrame(rows, columns=["Repository Name", "Date Created", "Created By"])
    
    # Cache-hit path: repo already exists in the sheet

    def test_returns_cached_creator_when_repo_in_sheet(self):
        # If the repo name + date match a sheet row with a valid creator,
        # the cached value should be returned without any API call.
        existing_df = self._dummy_existing_df([
            {"Repository Name": "my-repo", "Date Created": "2024-03-01", "Created By": "Alice (alice)"},
        ])
        repo = self._make_mock_repo("my-repo", "2024-03-01")

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Alice (alice)")
        repo.get_commits.assert_not_called()

    def test_skips_cache_when_creator_is_na_string(self):
        # "N/A" in the sheet means creator was unknown — should re-fetch from commits.
        existing_df = self._dummy_existing_df([
            {"Repository Name": "my-repo", "Date Created": "2024-03-01", "Created By": "N/A"},
        ])
        repo = self._make_mock_repo("my-repo", "2024-03-01")
        commits = self._make_commits_mock("Carol", "carol99")
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Carol (carol99)")

    def test_skips_cache_when_creator_is_nan(self):
        # NaN in the "Created By" cell (empty sheet cell) must not be returned.
        # The function should fall back to commit history instead.
        existing_df = self._dummy_existing_df([
            {"Repository Name": "my-repo", "Date Created": "2024-03-01", "Created By": float("nan")},
        ])
        repo = self._make_mock_repo("my-repo", "2024-03-01")
        commits = self._make_commits_mock("Dave", "dave42")
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Dave (dave42)")

    # Fallback path: repo not in the sheet at all

    def test_fetches_from_commits_when_repo_not_in_sheet(self):
        # Repo is absent from existing_df entirely — must hit commit history.
        existing_df = self._dummy_existing_df([
            {"Repository Name": "other-repo", "Date Created": "2024-03-01", "Created By": "Eve (eve)"},
        ])
        repo = self._make_mock_repo("my-repo", "2024-03-01")
        commits = self._make_commits_mock("Frank", "frankdev")
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Frank (frankdev)")
        repo.get_commits.assert_called()

    def test_fetches_from_commits_when_existing_df_is_empty(self):
        # Empty DataFrame (e.g. first-ever run, sheet has no data yet).
        existing_df = pd.DataFrame(columns=["Repository Name", "Date Created", "Created By"])
        repo = self._make_mock_repo("brand-new-repo", "2024-06-01")
        commits = self._make_commits_mock("Grace", "grace")
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Grace (grace)")
        
    def test_falls_back_to_commits_when_existing_df_missing_columns(self):
        # DataFrame exists but has wrong column names (e.g. bad sheet export).
        # Should fall through to commit history, not raise or return "N/A" silently.
        existing_df = pd.DataFrame([{"Repo": "my-repo", "Created": "2024-03-01"}])
        repo = self._make_mock_repo("my-repo", "2024-03-01")
        commits = self._make_commits_mock("Henry", "henry99")
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Henry (henry99)")
        repo.get_commits.assert_called()

    def test_correct_last_page_index_is_requested(self):
        # Critical math check: with 95 commits and 30 per page,
        # last_page = (95-1)//30 = 3. Verify get_page(3) is called.
        total, per_page = 95, 30
        repo = self._make_mock_repo("my-repo", "2024-03-01")
        commits = self._make_commits_mock("Dave", "dave", total=total, per_page=per_page)
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = per_page

        get_repo_creator(repo, None)

        expected_page = (total - 1) // per_page  # = 3
        commits.get_page.assert_called_once_with(expected_page)

    def test_returns_na_when_commit_author_is_none(self):
        # Oldest commit has no author (e.g. deleted GitHub account).
        existing_df = self._dummy_existing_df([])
        repo = self._make_mock_repo("ghost-repo", "2024-01-01")

        commits = MagicMock()
        commits.totalCount = 1
        commit = MagicMock()
        commit.author = None
        commits.get_page.return_value = [commit]
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "N/A")

    def test_returns_na_when_repo_has_no_commits(self):
        # Brand-new empty repo with zero commits should return "N/A" cleanly.
        existing_df = self._dummy_existing_df([])
        repo = self._make_mock_repo("empty-repo", "2024-01-01")

        commits = MagicMock()
        commits.totalCount = 0
        repo.get_commits.return_value = commits

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "N/A")


if __name__ == "__main__":
    unittest.main()