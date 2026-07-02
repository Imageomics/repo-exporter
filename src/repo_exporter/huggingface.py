from huggingface_hub import HfApi, hf_hub_download
from tqdm import tqdm
from collections import Counter
import re

from repo_exporter.base import BaseExporter

class HuggingFaceExporter(BaseExporter):
    """
    Exports Hugging Face org repo metadata to a Google Sheet.
    """

    def __init__(self, org_name: str, spreadsheet_id: str, sheet_name: str, creds_path: str, token: str | None = None):
        """
        Parameters:
        ------------
        org_name       - String. Hugging Face organization name.
        spreadsheet_id - String. Google Sheets spreadsheet ID.
        sheet_name     - String. Sheet tab name.
        creds_path     - String. Path to service_account.json.
        token          - String | None. Hugging Face token.
        """
        super().__init__(org_name, spreadsheet_id, sheet_name, creds_path)
        self.creds_path = creds_path
        self.token = token
        self.api = HfApi(token=token)
        
    @property
    def red_columns(self) -> set[str]:
        return {
            "README",
            "License",
            "Repo",
            "Paper",
        }

    @property
    def secondary_columns(self) -> set[str]:
        return {
            "Associated Datasets",
            "Associated Models",
            "Associated Spaces",
            "DOI",
        }

    def fetch_repos(self) -> list:
        """
        Fetch all models, datasets, and spaces for the org.
        Returns a list of (repo, repo_type) tuples.
        """
        repos = []
        for m in self.api.list_models(author=self.org_name):
            repos.append((m, "model"))
        for d in self.api.list_datasets(author=self.org_name):
            repos.append((d, "dataset"))
        for s in self.api.list_spaces(author=self.org_name):
            repos.append((s, "space"))
        return repos

    # Repo metadata helpers

    def get_repo_url(self, repo, repo_type: str) -> str:
        """
        Build the HF URL for a repo based on its type.

        Parameters:
        ------------
        repo      - HF repo info object.
        repo_type - String. One of "model", "dataset", "space".
        """
        if repo_type == "dataset":
            return f"https://huggingface.co/datasets/{repo.id}"
        elif repo_type == "space":
            return f"https://huggingface.co/spaces/{repo.id}"
        else:
            return f"https://huggingface.co/{repo.id}"

    def get_author(self, repo_id, repo_type) -> str:
        """
        Return the original creator of the repo, based on the earliest commit.

        Parameters:
        ------------
        repo_id   - String. Repo ID.
        repo_type - String. Repo type.
        """
        try:
            commits = self.api.list_repo_commits(repo_id=repo_id, repo_type=repo_type)
            if not commits:
                return self.org_name or "N/A"

            first_commit = commits[-1]
            if hasattr(first_commit, "authors") and first_commit.authors:
                first_author = first_commit.authors[0]
                if isinstance(first_author, str):
                    return first_author
                return getattr(first_author, "user", getattr(first_author, "name", self.org_name or "N/A"))

            return self.org_name or "N/A"
        except Exception:
            return self.org_name or "N/A"

    def get_top_contributors(self, repo_id, repo_type) -> str:
        """
        Return top 4 contributors as a comma-separated string, ranked by commit count.

        Parameters:
        ------------
        repo_id   - String. Repo ID.
        repo_type - String. Repo type.
        """
        try:
            commits = self.api.list_repo_commits(repo_id=repo_id, repo_type=repo_type)

            all_handles = []
            for c in commits:
                authors = getattr(c, "authors", [])
                for author in authors:
                    if isinstance(author, str):
                        all_handles.append(author)
                    else:
                        handle = getattr(author, "user", getattr(author, "name", None))
                        if handle:
                            all_handles.append(str(handle))

            bots_and_orgs = {(self.org_name or "").lower(), "web-flow"}
            filtered = [n for n in all_handles if str(n).lower() not in bots_and_orgs]

            if not filtered:
                return self.org_name or "N/A"

            counts = Counter(filtered)
            top_4 = [name for name, count in counts.most_common(4)]
            return ", ".join(top_4)
        except Exception:
            return self.org_name or "N/A"

    def get_open_pr_count(self, repo_id, repo_type) -> int:
        """
        Return the count of open pull requests for the repo.

        Parameters:
        ------------
        repo_id   - String. Repo ID.
        repo_type - String. Repo type.
        """
        try:
            discussions = self.api.get_repo_discussions(repo_id=repo_id, repo_type=repo_type)
            open_prs = [d for d in discussions if d.is_pull_request and d.status == "open"]
            return len(open_prs)
        except Exception:
            return 0

    def get_card_field(self, repo, keys: list) -> str:
        """
        Return the first non-empty value found in repo.card_data for the given keys.

        Parameters:
        ------------
        repo - HF repo info object.
        keys - List of card_data keys to check, in priority order.
        """
        try:
            for key in keys:
                value = repo.card_data.get(key, "")
                if value:
                    if isinstance(value, list):
                        return ", ".join(str(v) for v in value)
                    return str(value)
        except Exception:
            return "N/A"
        
        return "N/A"

    def get_associated_datasets(self, repo) -> str:
        """
        Return comma-separated dataset IDs tagged on the repo.

        Parameters:
        ------------
        repo - HF repo info object.
        """
        try:
            datasets = [tag.replace("dataset:", "") for tag in getattr(repo, "tags", []) if tag.startswith("dataset:")]
            return ", ".join(datasets) if datasets else "No"
        except Exception:
            return "No"

    def get_associated_models(self, repo, repo_type) -> str:
        """
        For dataset repos, search the HF API for models mentioning the repo ID.

        Parameters:
        ------------
        repo      - HF repo info object.
        repo_type - String. Repo type; only runs for "dataset".
        """
        found = []
        repo_id = getattr(repo, "id", str(repo))

        if repo_type == "dataset":
            try:
                related_models = list(self.api.list_models(search=repo_id))
                if related_models:
                    found = [m.id for m in related_models if m.id != repo_id]
            except Exception as e:
                tqdm.write(f"   [Search] Error: {e}")

        return ", ".join(found) if found else "No"

    def get_associated_spaces(self, repo_id) -> str:
        """
        Find HF spaces linked to a repo via metadata filter and string search.

        Parameters:
        ------------
        repo_id - HF repo info object or string ID.
        """
        found = set()
        clean_id = repo_id.id if hasattr(repo_id, "id") else str(repo_id)

        try:
            spaces_by_model = list(self.api.list_spaces(filter=f"models:{clean_id}"))
            for s in spaces_by_model:
                found.add(s.id)

            spaces_by_search = list(self.api.list_spaces(search=clean_id))
            for s in spaces_by_search:
                found.add(s.id)

            if clean_id in found:
                found.remove(clean_id)
        except Exception as e:
            tqdm.write(f"Error for {clean_id}: {e}")

        if not found:
            return "No"
        return ", ".join(sorted(found))

    def get_doi(self, repo) -> str:
        """
        Check repo.doi, card_data, then tags for a DOI.

        Parameters:
        ------------
        repo - HF repo info object.
        """
        try:
            if hasattr(repo, "doi") and repo.doi:
                return str(repo.doi).replace("doi:", "")

            if hasattr(repo, "card_data") and repo.card_data:
                doi = repo.card_data.get("doi")
                if doi:
                    return str(doi).replace("doi:", "")

            if hasattr(repo, "tags") and repo.tags:
                for tag in repo.tags:
                    if isinstance(tag, str) and tag.lower().startswith("doi:"):
                        return tag.replace("doi:", "").replace("DOI:", "")
        except Exception:
            pass

        return "No"

    def extract_link_from_text(self, text, label) -> str:
        """
        Parse a "Label: url" pattern from README text.

        Parameters:
        ------------
        text  - String. README content to search.
        label - String. Label to look for (e.g. "Homepage", "Paper", "Repository").
        """
        if not text:
            return "No"

        pattern = rf"\b{label}\b:\s*([^\r\n]+)"
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            content = match.group(1).strip()
            content = re.sub(r'[*_`\[\]]', '', content).strip()

            if content.upper() in ["N/A", "NONE", "", "NULL", "TBA", "COMING SOON", "IN PROGRESS", "TBD", "-->"]:
                return "No"

            if "http" in content.lower():
                url_match = re.search(r'(https?://[^\s)]+)', content)
                if url_match:
                    url = url_match.group(1).rstrip('.,)]')
                    display_text = content.split('(')[0].strip() or label
                    display_text = display_text.replace('"', '""')
                    return f'=HYPERLINK("{url}", "{display_text}")'

            return content
        return "No"

    def get_repo_info(self, repo, repo_type: str) -> dict[str, str | int]:
        """
        Return a metadata dict for a single HF repo.

        Parameters:
        ------------
        repo      - HF repo info object.
        repo_type - String. One of "model", "dataset", "space".
        """
        # Fetch full details inside the loop where BaseExporter wraps it in try/except
        repo_summary = repo
        if repo_type == "model":
            repo = self.api.model_info(repo_summary.id)
        elif repo_type == "dataset":
            repo = self.api.dataset_info(repo_summary.id)
        else:
            repo = self.api.space_info(repo_summary.id)
        
        readme_text = ""
        try:
            path = hf_hub_download(
                repo_id=repo.id,
                filename="README.md",
                repo_type=repo_type,
                token=self.token,
            )
            with open(path, "r", encoding="utf-8") as f:
                readme_text = f.read()
        except Exception as e:
            tqdm.write(f"!!! Failed to download README for {repo.id}: {e}")

        if repo_type == "dataset":
            display_id = f"datasets/{repo.id}"
        elif repo_type == "space":
            display_id = f"spaces/{repo.id}"
        else:
            display_id = repo.id

        return {
            "Repository Name": f'=HYPERLINK("{self.get_repo_url(repo, repo_type)}", "{display_id}")',
            "Repository Type": repo_type,
            "Description": self.get_card_field(repo, ["model_description", "description"]) or "N/A",
            "Date Created": repo.created_at.strftime("%Y-%m-%d") if getattr(repo, "created_at", False) else "N/A",
            "Last Updated": repo.lastModified.strftime("%Y-%m-%d") if getattr(repo, "lastModified", False) else "N/A",
            "Created By": self.get_author(repo.id, repo_type),
            "Top 4 Contributors/Curators": self.get_top_contributors(repo.id, repo_type),
            "Likes": getattr(repo, "likes", "N/A"),
            "# of Open PRs": self.get_open_pr_count(repo.id, repo_type),
            "README": "Yes" if readme_text else "No",
            "License": self.get_card_field(repo, ["license"]) or "No",
            "Visibility": "Private" if getattr(repo, "private", False) else "Public",
            "Inactive": self.is_inactive(getattr(repo, "lastModified", None)),
            "Homepage": self.extract_link_from_text(readme_text, "Homepage"),
            "Repo": self.extract_link_from_text(readme_text, "Repository"),
            "Paper": self.extract_link_from_text(readme_text, "Paper"),
            "Associated Datasets": self.get_associated_datasets(repo),
            "Associated Models": self.get_associated_models(repo, repo_type),
            "Associated Spaces": self.get_associated_spaces(repo),
            "DOI": self.get_doi(repo),
        }
    