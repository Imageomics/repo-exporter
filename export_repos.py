import os
import pandas as pd
from github import Github, GithubException, Auth
from tqdm import tqdm
from datetime import datetime, timedelta, timezone
import time
import re
import gspread
from google.oauth2.service_account import Credentials

# Config
ORG_NAME = "Imageomics"
SPREADSHEET_ID = "15BQimTjaOyo-jeaJRcg1Hia-9ORcilj3Jx-ks-uGyoc"
SHEET_NAME = "Sheet1"

# Helper Functions
def has_file(repo, *paths: str):
    for path in paths:
        try:
            if repo.get_contents(path):
                return "Yes"
        except GithubException:
            continue
    return "No"
    
def has_readme(repo):
    try:
        if repo.get_readme():
            return "Yes"
    except GithubException:
        return "No"

def has_license(repo):
    try:
        if repo.get_license():
            return "Yes"
    except GithubException:
        return "No"
        
def get_num_branches(repo):
    try:
        return repo.get_branches().totalCount
    except:
        return "N/A"
    
def get_repo_creator(repo):
    try:
        commits = repo.get_commits()
        first_commit = commits.reversed[0]
        author = first_commit.author
        return f"{author.name} ({author.login})" if author else "N/A"
    except Exception:
        return "N/A"
    
def get_top_contributors(repo, top_n: int = 4) -> str:
    try:
        # Keep repeatedly fetching stats since it may take time for GitHub to fetch that data
        stats = None
        for _ in range(5):
            stats = repo.get_stats_contributors()
            if stats:
                break
            time.sleep(2)

        if not stats:
            return "N/A"
        
        contributors = []
        for contributor in stats:
            
            total_additions = sum(week.a for week in contributor.weeks)
            total_deletions = sum(week.d for week in contributor.weeks)
            total_changes = total_additions + total_deletions

            contributors.append((contributor.author.name, contributor.author.login, total_changes))

        top_n_contributors = sorted(contributors, key=lambda x: x[2], reverse=True)[:top_n] # sort and take the top N results
        return ", ".join([f"{name} ({login})" for name, login, _ in top_n_contributors])
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

def has_doi(readme: str) -> str:
    try:
        if "zenodo.org/badge" in readme or "doi.org" in readme:
            return "Yes"
        return "No"
    except Exception:
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

def get_model(readme, homepage) -> str:
    try:
        # Check for Hugging Face model link in README
        hf_pattern = r"https?://huggingface\.co/imageomics/[A-Za-z0-9_\-./]+"
        hf_match = re.search(hf_pattern, readme)

        if hf_match:
            url = hf_match.group(0).rstrip(").],};:>\"'")
            return f'=HYPERLINK("{url}", "Yes")'

        # Check for arXiv link in About section on GitHub (repo.homepage)
        if homepage:
            homepage = homepage.strip().lower()

            arxiv_pattern = r"https?://arxiv\.org/[A-Za-z0-9_\-./]+"
            arxiv_match = re.search(arxiv_pattern, homepage)

            if arxiv_match:
                url = arxiv_match.group(0).rstrip(").],};:>\"'")
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

def get_associated_paper(readme) -> str:
    try:
        patterns = [
            r"https?://arxiv\.org/[A-Za-z0-9_\-./]+",
            r"https?://doi\.org/[A-Za-z0-9_\-./]+",
            r"https?://link\.springer\.com/[A-Za-z0-9_\-./]+",
            r"https?://www\.nature\.com/[A-Za-z0-9_\-./]+",
            r"https?://dl\.acm\.org/[A-Za-z0-9_\-./]+",
            r"https?://ieeexplore\.ieee\.org/[A-Za-z0-9_\-./]+",
            r"https?://www\.researchgate\.net/[A-Za-z0-9_\-./]+",
        ]

        for pattern in patterns:
            match = re.search(pattern, readme)
            if match:
                url = match.group(0)

                url = url.rstrip(").],};:>\"'")
                return f'=HYPERLINK("{url}", "Yes")'
        return "No"
    except Exception:
        return "No"
    
    
def get_repo_info(repo):
    try:
        readme_content_lower = repo.get_readme().decoded_content.decode("utf-8", errors="ignore").lower()
    except Exception:
        readme_content_lower = ""

    return {
        "Repository Name": f'=HYPERLINK("{repo.html_url}", "{repo.name}")',
        "Description": repo.description or "N/A",
        "Date Created": repo.created_at.strftime("%Y-%m-%d"),
        "Last Updated": repo.updated_at.strftime("%Y-%m-%d"),
        "Created By": get_repo_creator(repo),
        "Top 4 Contributors (lines of code changes)": get_top_contributors(repo, 4),
        "Stars": repo.stargazers_count,
        "# of Branches": get_num_branches(repo),
        "README": has_readme(repo),
        "License": has_license(repo),
        ".gitignore": has_file(repo, ".gitignore"),
        "Package Requirements": has_file(repo, "requirements.txt", "environment.yaml", "environment.yml"),
        "CITATION": has_file(repo, "CITATION.cff"),
        ".zenodo.json": has_file(repo, ".zenodo.json"),
        "CONTRIBUTING.md": has_file(repo, "CONTRIBUTING.md"),
        "Language": get_primary_language(repo),
        "Visibility": "Private" if repo.private else "Public",
        "Forks": "Yes" if repo.fork else "No",
        "Inactive": is_inactive(repo),
        "Website Reference": f'=HYPERLINK("{repo.homepage}", "Yes")' if repo.homepage else "No",
        "Dataset": get_dataset(readme_content_lower, repo.name.lower()),
        "Model": get_model(readme_content_lower, repo.homepage),
        "Paper Association": get_associated_paper(readme_content_lower),
        "DOI for GitHub Repo": has_doi(readme_content_lower),
    }

def extract_display_name(val):
    match = re.search(r'"([^"]+)"\)$', val) # regex to extract the repo-name from "=HYPERLINK(..., "repo-name")"
    return match.group(1) if match else val

def update_google_sheet(df):
    # Authenticate Google API
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")

    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

    # Pull current header
    HEADER_ROW_INDEX = 2
    header = sheet.row_values(HEADER_ROW_INDEX)

    # Build a dict of repo name -> index
    existing = sheet.get_all_values()
    data_rows = existing[HEADER_ROW_INDEX:]
    name_to_row = {}
    for offset, row in enumerate(data_rows, start=HEADER_ROW_INDEX + 1):
        if len(row) > 0:
            sheet_repo_name = extract_display_name(row[0]) # hardcoded to check for "Repository Name" column in row 0
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
            cell = gspread.utils.rowcol_to_a1(row_idx, col_idx)

            batch_body.append({
                "range": cell,
                "values": [[value]]  # single cell update
            })

    sheet.spreadsheet.values_batch_update(
        body={
            "value_input_option": "USER_ENTERED",
            "data": batch_body
        }
    )

    red_columns = {
        "README",
        "License",
        ".gitignore",
        "Package Requirements",
        "CITATION"
    }

    orange_columns = {
        ".zenodo.json",
        "CONTRIBUTING.md",
        "Website Reference",
        "Dataset",
        "Model",
        "Paper Association",
        "DOI for GitHub Repo"
    }

    rules = []

    for idx, col_name in enumerate(header, start=1):
        # Red No’s
        if col_name in red_columns:
            rules.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet.id,
                                "startRowIndex": HEADER_ROW_INDEX,
                                "startColumnIndex": idx - 1,
                                "endColumnIndex": idx
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "No"}]
                            },
                            "format": {
                                "backgroundColor": {"red": 1, "green": 0.5, "blue": 0.5}
                            }
                        }
                    },
                    "index": 0
                }
            })

        # Orange No’s
        if col_name in orange_columns:
            rules.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet.id,
                                "startRowIndex": HEADER_ROW_INDEX,
                                "startColumnIndex": idx - 1,
                                "endColumnIndex": idx
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "No"}]
                            },
                            "format": {
                                "backgroundColor": {"red": 1, "green": 0.8, "blue": 0.4}
                            }
                        }
                    },
                    "index": 0
                }
            })

    sheet.spreadsheet.batch_update({"requests": rules})
# --------

def main():
    TOKEN = os.getenv("GH_TOKEN") or input("Enter your GitHub token: ").strip()

    start_time = time.time()

    gh = Github(auth=Auth.Token(TOKEN))
    
    try:
        org = gh.get_organization(ORG_NAME)
    except Exception as e:
        print(f"ERROR: Could not access org: \"{ORG_NAME}\"")
        return
    
    print("")
    print(f"Fetching repositories from organization: {ORG_NAME}")
    print("")
    print("----------------")

    REPO_TYPE = os.getenv("REPO_TYPE")
    repos = list(org.get_repos(type=REPO_TYPE))
    data = []

    tqdm_kwargs = {}
    if os.environ.get("CI") == "true":
        tqdm_kwargs = {"mininterval": 1, "dynamic_ncols": False, "leave": False}

    for repo in tqdm(repos, desc=f"Fetching repositories from {ORG_NAME}...", unit="repo", colour="green", ncols=100, **tqdm_kwargs):
        try:
            info = get_repo_info(repo)
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

    update_google_sheet(df)
    print(f"Finished fetching info for {len(df)} repositories from {ORG_NAME} organization")

    elapsed = time.time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)

    print(f"Total time taken: {minutes}m {seconds}s")

if __name__ == "__main__":
    main()