import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd
import math

from gh_repo_exporter import extract_display_name, get_repo_creator

# --- Fix 1: safe lambda (main()) ---
# The old code called .apply(extract_display_name) directly.
# If a "Repository Name" cell is empty, pandas fills it with NaN (a float),
# which causes extract_display_name to raise TypeError inside re.search().
# Because that runs inside a broad try/except, one bad row silently empties
# existing_df and disables the whole "skip already-fetched repos" optimization.
# Fix: only call extract_display_name when the value is actually a string.

def apply_extract_display_name_safe(series: pd.Series) -> pd.Series:
    """Mirrors the fixed lambda: extract only if value is a str, else ''."""
    return series.apply(
        lambda v: extract_display_name(v) if isinstance(v, str) else ""
    )

# --- Fix 2: NaN-safe "Created By" lookup (get_repo_creator()) ---
# The old code did match.iloc[0]["Created By"], which is NaN when the cell is
# empty.  `if existing_creator` treats NaN as truthy (NaN != 0 in Python), so
# the function returned a raw float NaN instead of falling back to commit history.
# Fix: use .get() + isinstance guard so only real strings are returned.

def _extract_creator_from_match(match_row) -> str | None:
    """
    Mirrors the fixed lines 70-74 in get_repo_creator.
    Returns the creator string if valid, otherwise None (triggers fallback).
    """
    existing_creator = match_row.get("Created By")
    if isinstance(existing_creator, str):
        existing_creator = existing_creator.strip()
        if existing_creator and existing_creator != "N/A":
            return existing_creator
    return None


# --- Fix 3: paginated commit fallback (get_repo_creator()) ---
# The old fallback used commits.reversed[0], which forces PyGitHub to traverse
# the entire commit history — very slow for large repos (issue #38).
# Fix: use totalCount + get_page(last_page) to jump straight to the oldest
# page of commits with a single extra API call.

def _get_creator_from_commits(repo) -> str:
    """
    Mirrors the fixed fallback block (lines 77-87).
    Separated into its own function for unit-testability.
    """
    commits = repo.get_commits()
    total = commits.totalCount
    if not total:
        return "N/A"

    # Jump directly to the last page instead of reversing the whole history.
    per_page = getattr(getattr(repo, "_requester", None), "per_page", 30) or 30
    last_page = (total - 1) // per_page
    oldest_page = commits.get_page(last_page)
    oldest_commit = oldest_page[-1] if oldest_page else None
    author = oldest_commit.author if oldest_commit else None

    return f"{author.name} ({author.login})" if author else "N/A"

# Tests

class TestApplyExtractDisplayNameSafe(unittest.TestCase):
    """
    Covers the isinstance(v, str) guard added to the .apply() call in main().

    Each test feeds a pandas Series into apply_extract_display_name_safe and
    checks the output — no GitHub or Sheets API calls needed.
    """

    def test_normal_hyperlink_values_are_extracted(self):
        # Happy path: well-formed HYPERLINK formulas should extract the repo name.
        series = pd.Series([
            '=HYPERLINK("https://github.com/org/repo-a", "repo-a")',
            '=HYPERLINK("https://github.com/org/repo-b", "repo-b")',
        ])
        result = apply_extract_display_name_safe(series)
        self.assertEqual(result[0], "repo-a")
        self.assertEqual(result[1], "repo-b")

    def test_nan_values_become_empty_string(self):
        # Core bug: NaN must not raise TypeError; it should silently become ''.
        series = pd.Series([
            '=HYPERLINK("https://github.com/org/repo-a", "repo-a")',
            float("nan"),
        ])
        result = apply_extract_display_name_safe(series)
        self.assertEqual(result[0], "repo-a")
        self.assertEqual(result[1], "")

    def test_none_values_become_empty_string(self):
        # None is also not a str, so it should fall through to "".
        series = pd.Series([None, '=HYPERLINK("https://github.com/org/r", "r")'])
        result = apply_extract_display_name_safe(series)
        self.assertEqual(result[0], "")
        self.assertEqual(result[1], "r")

    def test_all_nan_series_returns_all_empty_strings(self):
        # All-NaN series: every cell should become "" without raising.
        series = pd.Series([float("nan"), float("nan")])
        result = apply_extract_display_name_safe(series)
        self.assertTrue((result == "").all())

    def test_plain_string_without_hyperlink_syntax_returns_itself(self):
        # If a cell holds a plain name (no HYPERLINK formula), the regex in extract_display_name finds no match and returns the original value.
        series = pd.Series(["just-a-name"])
        result = apply_extract_display_name_safe(series)
        self.assertEqual(result[0], "just-a-name")


class TestExtractCreatorFromMatch(unittest.TestCase):
    """
    Covers the isinstance + .strip() guard added to get_repo_creator() lines 70-74.

    _make_row() builds a minimal pandas Series that mimics match.iloc[0] so
    we can test the extraction logic without touching the GitHub API.
    """

    def _make_row(self, value):
        """Return a pandas Series that mimics match.iloc[0]."""
        return pd.Series({"Repository Name": "repo", "Date Created": "2024-01-01",
                          "Created By": value})

    def test_valid_creator_string_is_returned(self):
        # Happy path: a clean "Name (login)" string comes back unchanged.
        row = self._make_row("Alice (alice)")
        self.assertEqual(_extract_creator_from_match(row), "Alice (alice)")

    def test_creator_with_leading_trailing_whitespace_is_stripped(self):
        # .strip() should remove surrounding whitespace before returning.
        row = self._make_row("  Bob (bob)  ")
        self.assertEqual(_extract_creator_from_match(row), "Bob (bob)")

    def test_nan_creator_returns_none(self):
        # Core bug: NaN is truthy in Python, so the old code returned raw NaN.The fix must return None so the caller falls back to commit history.
        row = self._make_row(float("nan"))
        self.assertIsNone(_extract_creator_from_match(row))

    def test_na_string_returns_none(self):
        # "N/A" means no creator was found previously; trigger fallback.
        row = self._make_row("N/A")
        self.assertIsNone(_extract_creator_from_match(row))

    def test_empty_string_returns_none(self):
        # Empty string is not a useful creator value; trigger fallback.
        row = self._make_row("")
        self.assertIsNone(_extract_creator_from_match(row))

    def test_whitespace_only_string_returns_none(self):
        # After .strip(), "   " becomes "" which is falsy and return None.
        row = self._make_row("   ")
        self.assertIsNone(_extract_creator_from_match(row))

    def test_missing_key_returns_none(self):
        # If the "Created By" column is absent entirely, .get() returns None (a dict/Series key miss), which is not a str — so we return None.
        row = pd.Series({"Repository Name": "repo"})
        self.assertIsNone(_extract_creator_from_match(row))


class TestGetCreatorFromCommits(unittest.TestCase):
    """
    Covers the paginated commit fallback that replaces commits.reversed[0].

    _make_repo() builds a MagicMock repo whose get_commits() return value is
    pre-wired with a totalCount and a get_page() result, so no real API calls
    are made.  We then assert on what _get_creator_from_commits returns AND
    on which page index it actually requested.
    """

    def _make_repo(self, total_commits, per_page, oldest_author_name,
                   oldest_author_login, oldest_page_commits=None):
        """Build a minimal mock repo whose commit pagination is pre-configured."""
        repo = MagicMock()
        commits = MagicMock()
        commits.totalCount = total_commits

        if oldest_page_commits is None:
            author = MagicMock()
            author.name = oldest_author_name
            author.login = oldest_author_login
            last_commit = MagicMock()
            last_commit.author = author
            oldest_page_commits = [last_commit]

        commits.get_page.return_value = oldest_page_commits

        # Wire per_page onto _requester so the helper can read it.
        requester = MagicMock()
        requester.per_page = per_page
        repo._requester = requester

        # Make get_commits() always return the same commits mock so assertion on commits.get_page are consistent across multiple calls.
        repo.get_commits.return_value = commits
        return repo

    def test_returns_formatted_author_name_and_login(self):
        # Happy path: result should be "Name (login)".
        repo = self._make_repo(
            total_commits=5, per_page=30,
            oldest_author_name="Carol", oldest_author_login="carol99"
        )
        result = _get_creator_from_commits(repo)
        self.assertEqual(result, "Carol (carol99)")

    def test_zero_commits_returns_na(self):
        # A repo with no commits should return "N/A" without crashing.
        repo = MagicMock()
        commits = MagicMock()
        commits.totalCount = 0
        repo.get_commits.return_value = commits
        result = _get_creator_from_commits(repo)
        self.assertEqual(result, "N/A")

    def test_correct_last_page_index_is_requested(self):
        # Critical math check: with 95 commits and 30 per page,
        # last_page = (95-1)//30 = 3.  Verify get_page(3) is called.
        total, per_page = 95, 30
        repo = self._make_repo(
            total_commits=total, per_page=per_page,
            oldest_author_name="Dave", oldest_author_login="dave"
        )
        _get_creator_from_commits(repo)
        expected_page = (total - 1) // per_page  # = 3
        # Use repo.get_commits.return_value (the shared commits mock) so the assertion targets the same object the helper called get_page() on.
        repo.get_commits.return_value.get_page.assert_called_once_with(expected_page)

    def test_empty_last_page_returns_na(self):
        # If the last page comes back empty (edge case), return "N/A" gracefully.
        repo = self._make_repo(
            total_commits=10, per_page=30,
            oldest_author_name="", oldest_author_login="",
            oldest_page_commits=[]
        )
        result = _get_creator_from_commits(repo)
        self.assertEqual(result, "N/A")

    def test_commit_with_no_author_returns_na(self):
        # GitHub commits can have author=None (e.g. deleted accounts).
        repo = MagicMock()
        commits = MagicMock()
        commits.totalCount = 3

        last_commit = MagicMock()
        # author can be None on GitHub
        last_commit.author = None  
        commits.get_page.return_value = [last_commit]

        requester = MagicMock()
        requester.per_page = 30
        repo._requester = requester
        repo.get_commits.return_value = commits

        result = _get_creator_from_commits(repo)
        self.assertEqual(result, "N/A")

    def test_falls_back_to_default_per_page_when_requester_missing(self):
        # If _requester doesn't exist, per_page defaults to 30. With 31 commits: last_page = (31-1)//30 = 1.
        total = 31
        # spec=[] means no attributes exist by default
        repo = MagicMock(spec=[])  
        commits = MagicMock()
        commits.totalCount = total

        author = MagicMock()
        author.name = "Eve"
        author.login = "eve"
        last_commit = MagicMock()
        last_commit.author = author
        commits.get_page.return_value = [last_commit]

        repo.get_commits = MagicMock(return_value=commits)

        result = _get_creator_from_commits(repo)
        self.assertEqual(result, "Eve (eve)")
        commits.get_page.assert_called_once_with(1)


class TestGetRepoCreator(unittest.TestCase):
    """
    Tests get_repo_creator() end-to-end with a mocked GitHub repo object
    and an existing_df built from a dummy CSV-style DataFrame — matching
    the boss's ask for "dummy CSV + mocked GH API calls".

    Two paths through the function are tested:
      1. Repo IS in existing_df with a valid creator  → return cached value, no API call.
      2. Repo is NOT in existing_df (or has bad data) → fall back to commit history.
    """
    
    # Shared helpers

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
        with the given author.  Used to wire up the API fallback path.
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
        # If the repo name + date match a sheet row with a valid creator, the cached value should be returned without any API call.
        existing_df = self._dummy_existing_df([
            {"Repository Name": "my-repo", "Date Created": "2024-03-01", "Created By": "Alice (alice)"},
        ])
        repo = self._make_mock_repo("my-repo", "2024-03-01")

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Alice (alice)")
        repo.get_commits.assert_not_called()  # no API call should have been made

    def test_skips_cache_when_name_matches_but_date_differs(self):
        # A name match alone is not enough — the date must also match. Different date → should fall through to commit history.
        existing_df = self._dummy_existing_df([
            {"Repository Name": "my-repo", "Date Created": "2023-01-01", "Created By": "Alice (alice)"},
        ])
        repo = self._make_mock_repo("my-repo", "2024-03-01")
        commits = self._make_commits_mock("Bob", "bob")
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, existing_df)

        self.assertEqual(result, "Bob (bob)")

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
        # NaN in the "Created By" cell (empty sheet cell) must not be returned. The function should fall back to commit history instead.
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

    def test_fetches_from_commits_when_existing_df_is_none(self):
        # existing_df=None is the default — function should handle it gracefully.
        repo = self._make_mock_repo("my-repo", "2024-03-01")
        commits = self._make_commits_mock("Heidi", "heidi")
        repo.get_commits.return_value = commits
        repo._requester = MagicMock()
        repo._requester.per_page = 30

        result = get_repo_creator(repo, None)

        self.assertEqual(result, "Heidi (heidi)")

    def test_returns_na_when_commit_author_is_none(self):
        # Repo not in sheet, and the oldest commit has no author (deleted account).
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