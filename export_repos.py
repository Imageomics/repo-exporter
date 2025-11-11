import os
import pandas as pd
from github import Github, GithubException, Auth
from tqdm import tqdm
import time
import re
import gspread
from google.oauth2.service_account import Credentials

# Config
ORG_NAME = "Imageomics"
OUTPUT_FILE = f"{ORG_NAME}_repo_info.xlsx"
SPREADSHEET_ID = "1SHTSa3NV3HSAR6lqurQ4IPZbWDcdjU4GwPFHaQpGxEc"
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

            contributors.append((contributor.author.login if contributor.author else "N/A", total_changes))

        top_n_contributors = sorted(contributors, key=lambda x: x[1], reverse=True)[:top_n] # sort and take the top N results
        return ", ".join([f"{name} ({login})" for name, login in top_n_contributors])
    except Exception:
        return "N/A"
    
def has_doi(repo) -> str:
    try:
        file = repo.get_contents("CITATION.cff")
        content = file.decoded_content.decode("utf-8", errors="ignore")
        if re.search(r"doi\s*:\s*10\.\d{4,9}/[-._;()/:A-Z0-9]+", content, re.IGNORECASE):
            return "Yes"
        return "No"
    except GithubException:
        # Check for Zenodo DOI badge in README as fallback
        try:
            readme = repo.get_readme().decoded_content.decode("utf-8", errors="ignore").lower()
            if "zenodo.org/badge" in readme or "doi.org" in readme:
                return "Yes"
            return "No"
        except Exception:
            return "No"
        
def has_dataset(repo) -> str:
    try:
        readme = repo.get_readme().decoded_content.decode("utf-8", errors="ignore").lower()
        keywords = ["zenodo", "figshare", "kaggle", "data", "dataset"]
        if any(k in readme for k in keywords):
            return "Yes"
        return "No"
    except Exception:
        return "No"
    
def has_associated_paper(repo) -> str:
    try:
        readme = repo.get_readme().decoded_content.decode("utf-8", errors="ignore").lower()
        keywords = ["arxiv", "doi.org", "springer", "nature.com", "acm.org", "ieee.org", "researchgate"]
        if any(k in readme for k in keywords):
            return "Yes"
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
    
def get_repo_info(repo):
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
        "Language": get_primary_language(repo),
        "Visibility": "Private" if repo.private else "Public",
        "Website Reference": "Yes" if repo.homepage else "No",
        "Dataset": has_dataset(repo),
        "Paper Association": has_associated_paper(repo),
        "DOI for GitHub Repo": has_doi(repo),
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

    # Red color coding for No
    rule = {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [
                    { "sheetId": sheet.id }  # Apply to entire sheet
                ],
                "booleanRule": {
                    "condition": {
                        "type": "TEXT_EQ",
                        "values": [{"userEnteredValue": "No"}]
                    },
                    "format": {
                        "backgroundColor": {
                            "red": 1,
                            "green": 0.5,
                            "blue": 0.5
                        }
                    }
                },
            },
            "index": 0
        }
    }

    sheet.spreadsheet.batch_update({"requests": [rule]})
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

    repos = list(org.get_repos(type="private"))
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
    print(f"Finished fetching info for {len(df)} repositories from {ORG_NAME} organization to {OUTPUT_FILE}")

    elapsed = time.time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)

    print(f"Total time taken: {minutes}m {seconds}s")

if __name__ == "__main__":
    main()