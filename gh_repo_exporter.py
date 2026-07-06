from github import Github, GithubException, Auth
import pandas as pd
from tqdm import tqdm
from google.oauth2.service_account import Credentials
import gspread
import yaml

from datetime import datetime, timedelta, timezone
import time
import os
import re
import argparse

from dotenv import load_dotenv
load_dotenv()

# Config
GH_ORG_NAME = os.getenv("GH_ORG_NAME")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GH_SHEET_NAME = os.getenv("GH_SHEET_NAME","GH-Repos")
GH_TOKEN = os.getenv("GH_TOKEN")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")

# Package requirement files to check

PACKAGE_REQUIREMENT_FILES = [
    # Python 
    "requirements.txt", "environment.yaml", "environment.yml", "pyproject.toml",
    # R
    "DESCRIPTION", "renv.lock", "packrat/packrat.lock",
    # JavaScript / HTML
    "package.json", "package-lock.json", "yarn.lock", "bower.json",
]

# Helper Functions
def has_file(repo, *paths: str) -> str:
    for path in paths:
        try:
            if repo.get_contents(path):
                return "Yes"
        except GithubException:
            continue
    return "No"

def has_readme(repo) -> str:
    try:
        if repo.get_readme():
            return "Yes"
    except GithubException:
        return "No"

def has_license(repo) -> str:
    try:
        if repo.get_license():
            return "Yes"
    except GithubException:
        return "No"
        
def get_num_branches(repo) -> int | str:
    try:
        return repo.get_branches().totalCount
    except:
        return "N/A"
    
def get_repo_creator(repo, existing_df: pd.DataFrame = None) -> str:
    try:
        
         # Check if repo already exists in sheet. If so, reuse existing value instead of slow search
        if (
            existing_df is not None
            and not existing_df.empty
            and {"Repository Name", "Date Created", "Created By"}.issubset(existing_df.columns)
            ):
            repo_name = repo.name
            date_created = repo.created_at.strftime("%Y-%m-%d")
            match = existing_df.loc[
                (existing_df["Repository Name"] == repo_name) &
                (existing_df["Date Created"] == date_created)
            ].copy()
            if not match.empty:
                existing_creator = match.iloc[0].get("Created By")
                if isinstance(existing_creator, str):
                    existing_creator = existing_creator.strip()
                    if existing_creator and existing_creator != "N/A":
                        return existing_creator
        
        # Repo not found in sheet, fetch creator from commit history
        commits = repo.get_commits()
        total = commits.totalCount
        if not total:
            return "N/A"

        # Avoid loading the entire history into memory: fetch only the last page.
        per_page = getattr(getattr(repo, "_requester", None), "per_page", 30) or 30
        last_page = (total - 1) // per_page
        oldest_page = commits.get_page(last_page)
        oldest_commit = oldest_page[-1] if oldest_page else None
        author = oldest_commit.author if oldest_commit else None
        return f"{author.name} ({author.login})" if author else "N/A"
    
    except Exception as e:
        tqdm.write(f"Warning: Could not determine creator for {repo.name}: {e}")
        return "N/A"

def get_top_contributors(repo, top_n: int = 4) -> str:
    try:
        # Primary approach using get_stats_contributors() for lines of code ranking
        stats = None
        for _ in range(3):
            stats = repo.get_stats_contributors()
            if stats:
                break
            time.sleep(20)

        if not stats:
            # Fallback: use commit-based approach if get_stats_contributors() fails
            tqdm.write(f"  Falling back to commit-based for {repo.name}...")
            return get_top_contributors_commits(repo, top_n)

        contributors = []
        for contributor in stats:
            total_additions = sum(week.a for week in contributor.weeks)
            total_deletions = sum(week.d for week in contributor.weeks)
            total_changes = total_additions + total_deletions
            contributors.append((contributor.author.name, contributor.author.login, total_changes))

        top_n_contributors = sorted(contributors, key=lambda x: x[2], reverse=True)[:top_n]
        return ", ".join([f"{name} ({login})" for name, login, _ in top_n_contributors])

    except Exception:
        # Fallback: use commit-based approach if get_stats_contributors() raises an exception
        tqdm.write(f"  Falling back to commit-based for {repo.name}...")
        return get_top_contributors_commits(repo, top_n)

def get_top_contributors_commits(repo, top_n: int = 4) -> str:
    # Fallback method using commit count when get_stats_contributors() fails
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
    
def is_inactive(repo) -> str:
    try:
        updated = repo.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)

        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

        return "Yes" if updated < one_year_ago else "No"
    except Exception:
        return "No"
    
def is_valid_doi(doi: str | None) -> bool:
    """
    Validates whether a string is a properly formatted repo DOI and from the expected issuer (Zenodo).
    
    Returns True if DOI is valid, False otherwise.
    """
    
    # Make sure input is a string
    if not doi or not isinstance(doi, str):
        return False
    
    doi = doi.strip()
    doi_lower = doi.lower() 

    # Expected DOI format: 10.<4+ digits>/<suffix>
    if not re.match(r"^10\.\d{4,}/\S+$", doi, re.IGNORECASE):
        return False
    
    # Must be a known repo DOI; Zenodo is used for Github repos.
    if "zenodo" not in doi_lower:
        return False
    
    return True


def has_doi(repo) -> str:
    """
    Checks whether a repo contains a valid DOI in its CITATION.cff file. 
    
    Returns "Yes" if a valid DOI is found, otherwise "No"
    """
    
    # Retrieving CITATION.cff file from repo
    try:
        content_file = repo.get_contents("CITATION.cff")
        citation = content_file.decoded_content.decode("utf-8")

        data = yaml.safe_load(citation)
        if not isinstance(data, dict):
            return "No"

        # Case 1: top-level doi
        # e.g.
        # doi: 10.xxxx/xxxx
        
        doi = data.get("doi")
        if is_valid_doi(doi):
            return "https://doi.org/" + doi
        
        identifiers = data.get("identifiers", [])
        
        if isinstance(identifiers, list):
            for identifier in identifiers:
                
                if not isinstance(identifier, dict):
                    continue
                
                # Case 2: "type:: doi" with "value" # in identifiers field, e.g.
                # identifiers:
                #   - type: doi
                #     value: 10.xxxx/xxxx
                
                if identifier.get("type", "").lower() == "doi":
                    val = identifier.get("value")
       
                # Case 3: direct "doi" field inside identifier, e.g.
                # identifiers:
                #   - doi: 10.xxxx/xxxx
                
                elif "doi" in identifier:
                    val = identifier.get("doi")

                else:
                    continue
                
                if is_valid_doi(val):
                    return "https://doi.org/" + val
                
        # If no valid DOI found
        return "No"
    
    except Exception:
        # if CITATION.cff file doesn't exist or any parsing error occurs, return "No" 
        return "No"
        
def get_dataset(readme: str, repo_name: str) -> str:
    try:
        patterns = [
            r"https?://huggingface\.co/datasets/[^\s]+",
            rf"https?://github\.com/imageomics/{repo_name}/tree/main/data[^\s]*",
            r"https?://huggingface\.co/collections/[^\s]+",
        ]

        for pattern in patterns:
            match = re.search(pattern, readme, flags=re.IGNORECASE)
            if match:
                url = match.group(0)

                url = url.rstrip(").],};:>\"'")  # remove common trailing characters

                return f'=HYPERLINK("{url}", "Yes")'
        return "No"
    except Exception:
        return "No"

def get_model(readme: str) -> str:
    try:
        # Check for Hugging Face model link in README
        hf_pattern = r"https?://huggingface\.co/imageomics/[A-Za-z0-9_\-./]+"
        hf_match = re.search(hf_pattern, readme)

        if hf_match:
            url = hf_match.group(0).rstrip(").],};:>\"'")
            return f'=HYPERLINK("{url}", "Yes")'

        return "No"
    except Exception:
        return "No"
    
def get_primary_language(repo) -> str:
    try:
        languages = repo.get_languages()
        if not languages:
            return "N/A"
        
        return max(languages, key=languages.get)
    except Exception:
        return "N/A"

def get_associated_paper(readme: str, homepage: str | None = None) -> str:
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

        # checks for [<name>](<url>)
        markdown_link_pattern = r"\[([^\]]+)\]\((.*?)\)"

        # Check README for paper-associated links
        for label, url in re.findall(markdown_link_pattern, readme):
            # Only accept label == "paper" or "arXiv" (case-insensitive)
            if label.strip().lower() not in {"paper", "arxiv"}:
                continue

            # Check if URL matches a paper source
            for pattern in url_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    cleaned = url.rstrip(").],};:>\"'")
                    return f'=HYPERLINK("{cleaned}", "Yes")'
                
        # Check About section URL as fallback  
        if homepage:
            for pattern in url_patterns:
                if re.search(pattern, homepage, re.IGNORECASE):
                    cleaned = homepage.rstrip(").],};:>\"'")
                    return f'=HYPERLINK("{cleaned}", "Yes")'
        return "No"
    except Exception:
        return "No"
    
def get_website_reference(homepage: str | None) -> str:
    try:
        if not homepage:
            return "No"
        
        # Return "No" if homepage is a paper, dataset, or model link instead of an actual website
        external_patterns = [
            "arxiv.org",
            "huggingface.co",
            "hf.co",
            "doi.org",
        ]
        
        if any(pattern in homepage.lower() for pattern in external_patterns):
            return "No"
        
        cleaned = homepage.rstrip(").],};:>\"'")
        return f'=HYPERLINK("{cleaned}", "Yes")'
    except Exception:
        return "No"
     
def get_repo_info(repo, existing_df: pd.DataFrame = None) -> dict[str, str | int]:
    try:
        readme_content_lower = repo.get_readme().decoded_content.decode("utf-8", errors="ignore").lower()
    except Exception:
        readme_content_lower = ""

    return {
        "Repository Name": f'=HYPERLINK("{repo.html_url}", "{repo.name}")',
        "Description": repo.description or "N/A",
        "Date Created": repo.created_at.strftime("%Y-%m-%d"),
        "Last Updated": repo.updated_at.strftime("%Y-%m-%d"),
        "Created By": get_repo_creator(repo, existing_df),
        "Top 4 Contributors (lines of code changes)": get_top_contributors(repo, 4),
        "Stars": repo.stargazers_count,
        "# of Branches": get_num_branches(repo),
        "README": has_readme(repo),
        "License": has_license(repo),
        ".gitignore": has_file(repo, ".gitignore"),
        "Package Requirements": has_file(repo, *PACKAGE_REQUIREMENT_FILES),
        "CITATION": has_file(repo, "CITATION.cff"),
        ".zenodo.json": has_file(repo, ".zenodo.json"),
        "CONTRIBUTING": has_file(repo, "CONTRIBUTING.md"),
        "AGENTS": has_file(repo, "AGENTS.md"),
        "Language": get_primary_language(repo),
        "Visibility": "Private" if repo.private else "Public",
        "Is Fork": "Yes" if repo.fork else "No",
        "Has Forks": repo.forks_count if repo.forks_count > 0 else "No",
        "Archived": "Yes" if repo.archived else "No",
        "Inactive": is_inactive(repo),
        "Website Reference": get_website_reference(repo.homepage),
        "Dataset": get_dataset(readme_content_lower, repo.name.lower()),
        "Model": get_model(readme_content_lower),
        "Paper Association": get_associated_paper(readme_content_lower, repo.homepage),
        "DOI for GitHub Repo": has_doi(repo),
    }

def extract_display_name(val: str) -> str:
    match = re.search(r'"([^"]+)"\)$', val) # regex to extract the repo-name from "=HYPERLINK(..., "repo-name")"
    return match.group(1) if match else val

def update_google_sheet(df: pd.DataFrame, spreadsheet_id: str, sheet_name: str, creds_path: str) -> None:
    # Authenticate Google API
    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)

    # Pull current header
    HEADER_ROW_INDEX = 2
    header = sheet.row_values(HEADER_ROW_INDEX)

    # Find 
    try: 
        repo_col_index = header.index("Repository Name")
    except ValueError:
        raise ValueError('Sheet is missing "Repository Name" column')

    # Build a dict of repo name -> index
    existing = sheet.get_all_values()
    data_rows = existing[HEADER_ROW_INDEX:]
    name_to_row = {}
    for offset, row in enumerate(data_rows, start=HEADER_ROW_INDEX + 1):
        if len(row) <= repo_col_index: # if row of data fetched is missing repo name column, ignore the row
            continue

        sheet_repo_name = extract_display_name(row[repo_col_index]) # hardcoded to check for "Repository Name" column in row 0
        name_to_row[sheet_repo_name] = offset

    batch_body = []
    for _, row in df.iterrows():
        repo_name = extract_display_name(row["Repository Name"])

        # Determine row index
        if repo_name in name_to_row:
            row_idx = name_to_row[repo_name]
        else:
            row_idx = len(existing) + 1
            existing.append([""] * len(header))

        # Create (range, value) for each column individually
        for col_idx, col_name in enumerate(header, start=1):
            if col_name not in df.columns:
                continue  # skip untouched columns

            value = row.get(col_name, "")
            cell = f"'{sheet.title}'!{gspread.utils.rowcol_to_a1(row_idx, col_idx)}"

            batch_body.append({
                "range": cell,
                "majorDimension": "ROWS",
                "values": [[value]]  # single cell update
            })

    sheet.spreadsheet.values_batch_update(
        body={
            "value_input_option": "USER_ENTERED",
            "data": batch_body
        }
    )

    def get_column_index(col_name: str):
        try:
            return header.index(col_name)
        except ValueError:
            return None  # column not found

    red_columns = {
        "README",
        "License",
        ".gitignore",
        "Package Requirements",
        "CITATION"
    }

    orange_columns = {
        ".zenodo.json",
        "CONTRIBUTING",
        "AGENTS",
        "Website Reference",
        "Dataset",
        "Model",
        "Paper Association",
        "DOI for GitHub Repo"
    }

    rules = []

    # Only loop over columns that need formatting
    for col_set, color in [(red_columns, {"red": 1, "green": 0.5, "blue": 0.5}),
                        (orange_columns, {"red": 1, "green": 0.8, "blue": 0.4})]:

        for col_name in col_set:
            col_index = get_column_index(col_name)
            if col_index is None:
                continue  # skip missing columns

            rules.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet.id,
                            "startRowIndex": HEADER_ROW_INDEX,           # start after header
                            "endRowIndex": HEADER_ROW_INDEX + len(df),   # only data rows
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "No"}]
                            },
                            "format": {
                                "backgroundColor": color
                            }
                        }
                    },
                    "index": 0
                }
            })

    sheet.spreadsheet.batch_update({"requests": rules})
# --------

def main():
    parser = argparse.ArgumentParser(description="Export GitHub org repo metadata to Google Sheets.")
    parser.add_argument("--org", default=None, help="GitHub org name (overrides GH_ORG_NAME in .env)")
    parser.add_argument("--token", default=None, help="GitHub personal access token (overrides GH_TOKEN in .env)")
    parser.add_argument("--repo-type", default="all", help="Repo type filter: all, public, private, forks, sources, member; default: all")
    parser.add_argument("--spreadsheet-id", default=None, help="Google Sheets spreadsheet ID (overrides SPREADSHEET_ID in .env)")
    parser.add_argument("--sheet-name", default=None, help=f"Sheet tab name (overrides GH_SHEET_NAME in .env; default: {GH_SHEET_NAME})")
    parser.add_argument("--credentials-path", default=None, help=f"Path to service_account.json (overrides GOOGLE_CREDENTIALS_PATH in .env; default: {GOOGLE_CREDENTIALS_PATH})")
    args = parser.parse_args()

    org_name = args.org or GH_ORG_NAME
    TOKEN = (args.token or GH_TOKEN or "").strip() or None 
    repo_type = args.repo_type
    spreadsheet_id = args.spreadsheet_id or SPREADSHEET_ID
    sheet_name = args.sheet_name or GH_SHEET_NAME
    creds_path = args.credentials_path or GOOGLE_CREDENTIALS_PATH

    required_vars = {
        "GH_ORG_NAME": org_name,
        "SPREADSHEET_ID": spreadsheet_id,
    }

    missing = [name for name, value in required_vars.items() if not value]

    if missing:
        raise ValueError(
            "Missing required environment variables: "
            f"{', '.join(missing)}. Set them in your shell/.env or in the GitHub Actions workflow env."
        )
        
    start_time = time.time()

    gh = Github(auth=Auth.Token(TOKEN)) if TOKEN else Github()
    
    try:
        org = gh.get_organization(org_name)
    except Exception as e:
        print(f"ERROR: Could not access org: \"{org_name}\"")
        return
    
    print("")
    print(f"Fetching repositories from organization: {org_name}")
    print("")
    print("----------------")

    repos = list(org.get_repos(type=repo_type))
    print(f"Total repos fetched: {len(repos)}")
    data = []
    
    # Load repo name, date created, and created by columns from existing sheet before fetching repo 
    # to avoid recomputing "Created By" for repos already in the sheet
    
    existing_df = pd.DataFrame()

    try:
        creds = Credentials.from_service_account_file(
            creds_path,
            scopes=[
               "https://www.googleapis.com/auth/spreadsheets",
               "https://www.googleapis.com/auth/drive"
            ]
        )

        client = gspread.authorize(creds)
        sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)

        all_values = sheet.get_all_values()

        if len(all_values) > 2:
            headers = all_values[1]
            rows = all_values[2:]

            full_df = pd.DataFrame(rows, columns=headers)
            existing_df = full_df[
                    ["Repository Name", "Date Created", "Created By"]
            ].copy()
            existing_df["Repository Name"] = existing_df["Repository Name"].apply(
                lambda v: extract_display_name(v) if isinstance(v, str) else ""
            )

    except Exception as e:
        print(f"Warning: Could not load existing sheet data: {e}")

    tqdm_kwargs = {}
    if os.environ.get("CI") == "true":
        tqdm_kwargs = {"mininterval": 1, "dynamic_ncols": False, "leave": False}

    print(f"Existing sheet data shape: {existing_df.shape}")
    
    for repo in tqdm(repos, desc=f"Fetching repositories from {org_name}...", unit="repo", colour="green", ncols=100, **tqdm_kwargs):
        try:
            info = get_repo_info(repo, existing_df)
            data.append(info)
            tqdm.write(f"Fetched info for /{repo.name} repo")
        except Exception as e:
            tqdm.write(f"ERROR: Cannot fetch /{repo.name} info, due to {type(e).__name__}: {e}. Skipping...")

    if not data:
        print("ERROR: No data collected")
        return
    
    print("----------------")
    print("")

    df = pd.DataFrame(data)
    df.sort_values(by="Repository Name", inplace=True)

    update_google_sheet(df, spreadsheet_id, sheet_name, creds_path)
    print(f"Finished fetching info for {len(df)} repositories from {org_name} organization")

    elapsed = time.time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)

    print(f"Total time taken: {minutes}m {seconds}s")

if __name__ == "__main__":
    main()