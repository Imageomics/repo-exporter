from github import Github, GithubException, Auth
import pandas as pd
from tqdm import tqdm
import yaml
import re
import time
import os

from repo_exporter.base import BaseExporter
from google.oauth2.service_account import Credentials
import gspread


PACKAGE_REQUIREMENT_FILES = [
    # Python
    "requirements.txt", "environment.yaml", "environment.yml", "pyproject.toml",
    # R
    "DESCRIPTION", "renv.lock", "packrat/packrat.lock",
    # JavaScript / HTML
    "package.json", "package-lock.json", "yarn.lock", "bower.json",
]


class GitHubExporter(BaseExporter):
    """
    Exports GitHub org repo metadata to a Google Sheet.
    """

    def __init__(self, token: str, org_name: str, spreadsheet_id: str, sheet_name: str, creds_path: str, repo_type: str | None = None):
        """
        Parameters:
        ------------
        token          - String. GitHub personal access token.
        org_name       - String. GitHub organization name.
        spreadsheet_id - String. Google Sheets spreadsheet ID.
        sheet_name     - String. Sheet tab name.
        creds_path     - String. Path to service_account.json.
        repo_type      - String | None. Repo type filter (all, public, private, forks, sources, member).
        """
        super().__init__()
        self.token = token
        self.org_name = org_name
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.creds_path = creds_path
        self.repo_type = repo_type
        self.gh = Github(auth=Auth.Token(token)) if token else Github()
        self.existing_df = pd.DataFrame()

    # Repo fetching

    def fetch_repos(self) -> list:
        """
        Fetch all repos for the org and pre-load existing sheet data
        to avoid recomputing Created By for repos already tracked.
        """
        try:
            org = self.gh.get_organization(self.org_name)
        except Exception as e:
            raise RuntimeError(f'Could not access org "{self.org_name}": {e}')

        repos = list(org.get_repos(type=self.repo_type))
        print(f"Total repos fetched: {len(repos)}")

        self._load_existing_sheet()
        print(f"Existing sheet data shape: {self.existing_df.shape}")

        return repos

    def _load_existing_sheet(self) -> None:
        """
        Pre-load Repository Name, Date Created, Created By from the existing
        sheet so get_repo_creator can skip re-fetching commit history.
        """
        try:
            creds = Credentials.from_service_account_file(
                self.creds_path,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ],
            )
            client = gspread.authorize(creds)
            sheet = client.open_by_key(self.spreadsheet_id).worksheet(self.sheet_name)
            all_values = sheet.get_all_values()

            if len(all_values) > 2:
                headers = all_values[1]
                rows = all_values[2:]
                full_df = pd.DataFrame(rows, columns=headers)
                self.existing_df = full_df[
                    ["Repository Name", "Date Created", "Created By"]
                ].copy()
                self.existing_df["Repository Name"] = self.existing_df["Repository Name"].apply(
                    lambda v: self.extract_display_name(v) if isinstance(v, str) else ""
                )
        except Exception as e:
            print(f"Warning: Could not load existing sheet data: {e}")

    # Repo metadata helpers

    def has_file(self, repo, *paths: str) -> str:
        """
        Return "Yes" if any of the given paths exist in the repo, else "No".

        Parameters:
        ------------
        repo  - PyGitHub Repository object.
        paths - One or more file paths to check.
        """
        for path in paths:
            try:
                if repo.get_contents(path):
                    return "Yes"
            except GithubException:
                continue
        return "No"

    def has_readme(self, repo) -> str:
        """
        Return "Yes" if the repo has a README, else "No".

        Parameters:
        ------------
        repo - PyGitHub Repository object.
        """
        try:
            if repo.get_readme():
                return "Yes"
            return "No"
        except GithubException:
            return "No"

    def has_license(self, repo) -> str:
        """
        Return "Yes" if the repo has a license file, else "No".

        Parameters:
        ------------
        repo - PyGitHub Repository object.
        """
        try:
            if repo.get_license():
                return "Yes"
            return "No"
        except GithubException:
            return "No"

    def get_num_branches(self, repo) -> int | str:
        """
        Return the total number of branches, or "N/A" on failure.

        Parameters:
        ------------
        repo - PyGitHub Repository object.
        """
        try:
            return repo.get_branches().totalCount
        except Exception:
            return "N/A"

    def get_repo_creator(self, repo) -> str:
        """
        Return the creator of the repo.
        Checks existing sheet data first to avoid re-fetching commit history.

        Parameters:
        ------------
        repo - PyGitHub Repository object.
        """
        try:
            if (
                self.existing_df is not None
                and not self.existing_df.empty
                and {"Repository Name", "Date Created", "Created By"}.issubset(self.existing_df.columns)
            ):
                repo_name = repo.name
                date_created = repo.created_at.strftime("%Y-%m-%d")
                match = self.existing_df.loc[
                    (self.existing_df["Repository Name"] == repo_name) &
                    (self.existing_df["Date Created"] == date_created)
                ].copy()
                if not match.empty:
                    existing_creator = match.iloc[0].get("Created By")
                    if isinstance(existing_creator, str):
                        existing_creator = existing_creator.strip()
                        if existing_creator and existing_creator != "N/A":
                            return existing_creator

            commits = repo.get_commits()
            total = commits.totalCount
            if not total:
                return "N/A"

            per_page = getattr(getattr(repo, "_requester", None), "per_page", 30) or 30
            last_page = (total - 1) // per_page
            oldest_page = commits.get_page(last_page)
            oldest_commit = oldest_page[-1] if oldest_page else None
            author = oldest_commit.author if oldest_commit else None
            return f"{author.name} ({author.login})" if author else "N/A"

        except Exception as e:
            tqdm.write(f"Warning: Could not determine creator for {repo.name}: {e}")
            return "N/A"

    def get_top_contributors(self, repo, top_n: int = 4) -> str:
        """
        Return top N contributors as a comma-separated string, ranked by lines changed.
        Falls back to commit-based ranking if stats are unavailable.

        Parameters:
        ------------
        repo   - PyGitHub Repository object.
        top_n  - Integer. Number of top contributors to return.
        """
        try:
            stats = None
            for _ in range(3):
                stats = repo.get_stats_contributors()
                if stats:
                    break
                time.sleep(20)

            if not stats:
                tqdm.write(f"  Falling back to commit-based for {repo.name}...")
                return self._get_top_contributors_commits(repo, top_n)

            contributors = []
            for contributor in stats:
                total_additions = sum(week.a for week in contributor.weeks)
                total_deletions = sum(week.d for week in contributor.weeks)
                total_changes = total_additions + total_deletions
                contributors.append((contributor.author.name, contributor.author.login, total_changes))

            top_n_contributors = sorted(contributors, key=lambda x: x[2], reverse=True)[:top_n]
            return ", ".join([f"{name} ({login})" for name, login, _ in top_n_contributors])

        except Exception:
            tqdm.write(f"  Falling back to commit-based for {repo.name}...")
            return self._get_top_contributors_commits(repo, top_n)

    def _get_top_contributors_commits(self, repo, top_n: int = 4) -> str:
        """
        Fallback: rank contributors by commit count instead of lines changed.

        Parameters:
        ------------
        repo   - PyGitHub Repository object.
        top_n  - Integer. Number of top contributors to return.
        """
        try:
            contributors = repo.get_contributors()
            top_n_contributors = []
            for i, contributor in enumerate(contributors):
                if i >= top_n:
                    break
                top_n_contributors.append(f"{contributor.name} ({contributor.login})")

            result = ", ".join(top_n_contributors) if top_n_contributors else "N/A"
            return f"{result} (commit-based)" if result != "N/A" else "N/A"
        except Exception:
            return "N/A"

    def get_primary_language(self, repo) -> str:
        """
        Return the primary programming language of the repo, or "N/A".

        Parameters:
        ------------
        repo - PyGitHub Repository object.
        """
        try:
            languages = repo.get_languages()
            if not languages:
                return "N/A"
            return max(languages, key=languages.get)
        except Exception:
            return "N/A"

    def is_valid_doi(self, doi: str | None) -> bool:
        """
        Return True if doi is a valid, Zenodo-issued DOI.

        Parameters:
        ------------
        doi - String | None. DOI string to validate.
        """
        if not doi or not isinstance(doi, str):
            return False
        doi = doi.strip()
        if not re.match(r"^10\.\d{4,}/\S+$", doi, re.IGNORECASE):
            return False
        if "zenodo" not in doi.lower():
            return False
        return True

    def has_doi(self, repo) -> str:
        """
        Check CITATION.cff for a valid Zenodo DOI.
        Returns a full https://doi.org/ URL or "No".

        Parameters:
        ------------
        repo - PyGitHub Repository object.
        """
        try:
            content_file = repo.get_contents("CITATION.cff")
            citation = content_file.decoded_content.decode("utf-8")
            data = yaml.safe_load(citation)
            if not isinstance(data, dict):
                return "No"

            doi = data.get("doi")
            if self.is_valid_doi(doi):
                return "https://doi.org/" + doi

            identifiers = data.get("identifiers", [])
            if isinstance(identifiers, list):
                for identifier in identifiers:
                    if not isinstance(identifier, dict):
                        continue
                    if identifier.get("type", "").lower() == "doi":
                        val = identifier.get("value")
                    elif "doi" in identifier:
                        val = identifier.get("doi")
                    else:
                        continue
                    if self.is_valid_doi(val):
                        return "https://doi.org/" + val

            return "No"
        except Exception:
            return "No"

    def get_dataset(self, readme: str, repo_name: str) -> str:
        """
        Search README for a linked HuggingFace dataset/collection or GitHub data folder.
        Returns a HYPERLINK formula or "No".

        Parameters:
        ------------
        readme    - String. README content (lowercased).
        repo_name - String. Name of the repo (lowercased).
        """
        try:
            patterns = [
                r"https?://huggingface\.co/datasets/[^\s]+",
                rf"https?://github\.com/imageomics/{repo_name}/tree/main/data[^\s]*",
                r"https?://huggingface\.co/collections/[^\s]+",
            ]
            for pattern in patterns:
                match = re.search(pattern, readme, flags=re.IGNORECASE)
                if match:
                    url = match.group(0).rstrip(").],};:>\"'")
                    return f'=HYPERLINK("{url}", "Yes")'
            return "No"
        except Exception:
            return "No"

    def get_model(self, readme: str) -> str:
        """
        Search README for a linked HuggingFace model under the imageomics org.
        Returns a HYPERLINK formula or "No".

        Parameters:
        ------------
        readme - String. README content.
        """
        try:
            hf_pattern = r"https?://huggingface\.co/imageomics/[A-Za-z0-9_\-./]+"
            hf_match = re.search(hf_pattern, readme)
            if hf_match:
                url = hf_match.group(0).rstrip(").],};:>\"'")
                return f'=HYPERLINK("{url}", "Yes")'
            return "No"
        except Exception:
            return "No"

    def get_associated_paper(self, readme: str, homepage: str | None = None) -> str:
        """
        Search README for a markdown link labeled "paper" or "arxiv" pointing to
        a known publisher URL. Falls back to homepage. Returns a HYPERLINK formula or "No".

        Parameters:
        ------------
        readme   - String. README content.
        homepage - String | None. Repo homepage URL as a fallback.
        """
        try:
            url_patterns = [
                r"https?://arxiv\.org/[A-Za-z0-9_\-./]+",
                r"https?://doi\.org/[A-Za-z0-9_\-./]+",
                r"https?://link\.springer\.com/[A-Za-z0-9_\-./]+",
                r"https?://www\.nature\.com/[A-Za-z0-9_\-./]+",
                r"https?://dl\.acm\.org/[A-Za-z0-9_\-./]+",
                r"https?://ieeexplore\.ieee\.org/[A-Za-z0-9_\-./]+",
                r"https?://www\.researchgate\.net/[A-Za-z0-9_\-./]+",
            ]
            markdown_link_pattern = r"\[([^\]]+)\]\((.*?)\)"

            for label, url in re.findall(markdown_link_pattern, readme):
                if label.strip().lower() not in {"paper", "arxiv"}:
                    continue
                for pattern in url_patterns:
                    if re.search(pattern, url, re.IGNORECASE):
                        cleaned = url.rstrip(").],};:>\"'")
                        return f'=HYPERLINK("{cleaned}", "Yes")'

            if homepage:
                for pattern in url_patterns:
                    if re.search(pattern, homepage, re.IGNORECASE):
                        cleaned = homepage.rstrip(").],};:>\"'")
                        return f'=HYPERLINK("{cleaned}", "Yes")'

            return "No"
        except Exception:
            return "No"

    def get_website_reference(self, homepage: str | None) -> str:
        """
        Return a HYPERLINK formula for the repo homepage if it is an actual website
        (not arxiv, huggingface, or doi). Returns "No" otherwise.

        Parameters:
        ------------
        homepage - String | None. The repo homepage URL.
        """
        try:
            if not homepage:
                return "No"
            external_patterns = ["arxiv.org", "huggingface.co", "hf.co", "doi.org"]
            if any(pattern in homepage.lower() for pattern in external_patterns):
                return "No"
            cleaned = homepage.rstrip(").],};:>\"'")
            return f'=HYPERLINK("{cleaned}", "Yes")'
        except Exception:
            return "No"

    # get_repo_info

    def get_repo_info(self, repo) -> dict[str, str | int]:
        """
        Return a metadata dict for a single GitHub repo.

        Parameters:
        ------------
        repo - PyGitHub Repository object.
        """
        try:
            readme_content_lower = repo.get_readme().decoded_content.decode("utf-8", errors="ignore").lower()
        except Exception:
            readme_content_lower = ""

        return {
            "Repository Name": f'=HYPERLINK("{repo.html_url}", "{repo.name}")',
            "Description": repo.description or "N/A",
            "Date Created": repo.created_at.strftime("%Y-%m-%d"),
            "Last Updated": repo.updated_at.strftime("%Y-%m-%d"),
            "Created By": self.get_repo_creator(repo),
            "Top 4 Contributors (lines of code changes)": self.get_top_contributors(repo, 4),
            "Stars": repo.stargazers_count,
            "# of Branches": self.get_num_branches(repo),
            "README": self.has_readme(repo),
            "License": self.has_license(repo),
            ".gitignore": self.has_file(repo, ".gitignore"),
            "Package Requirements": self.has_file(repo, *PACKAGE_REQUIREMENT_FILES),
            "CITATION": self.has_file(repo, "CITATION.cff"),
            ".zenodo.json": self.has_file(repo, ".zenodo.json"),
            "CONTRIBUTING": self.has_file(repo, "CONTRIBUTING.md"),
            "AGENTS": self.has_file(repo, "AGENTS.md"),
            "Language": self.get_primary_language(repo),
            "Visibility": "Private" if repo.private else "Public",
            "Is Fork": "Yes" if repo.fork else "No",
            "Has Forks": repo.forks_count if repo.forks_count > 0 else "No",
            "Archived": "Yes" if repo.archived else "No",
            "Inactive": self.is_inactive(repo.updated_at),
            "Website Reference": self.get_website_reference(repo.homepage),
            "Dataset": self.get_dataset(readme_content_lower, repo.name.lower()),
            "Model": self.get_model(readme_content_lower),
            "Paper Association": self.get_associated_paper(readme_content_lower, repo.homepage),
            "DOI for GitHub Repo": self.has_doi(repo),
        }

    # Google Sheets update

    def update_google_sheet(self, df: pd.DataFrame) -> None:
        """
        Write df to the GitHub sheet tab with GH-specific column/color config.

        Parameters:
        ------------
        df - pd.DataFrame. Data to write, with columns matching sheet headers.
        """
        sheet = self._get_sheet()
        header = sheet.row_values(2)
        batch_body, _ = self._build_batch_body(sheet, df, header)
        self._write_batch(sheet, batch_body)

        red_columns = {
            "README",
            "License",
            ".gitignore",
            "Package Requirements",
            "CITATION",
        }
        orange_columns = {
            ".zenodo.json",
            "CONTRIBUTING",
            "AGENTS",
            "Website Reference",
            "Dataset",
            "Model",
            "Paper Association",
            "DOI for GitHub Repo",
        }

        self._apply_conditional_formatting(
            sheet,
            header,
            df,
            red_columns=red_columns,
            secondary_columns=orange_columns,
            secondary_color={"red": 1, "green": 0.8, "blue": 0.4},
        )