from huggingface_hub import HfApi, hf_hub_download
import pandas as pd
from tqdm import tqdm
from google.oauth2.service_account import Credentials
import gspread

from datetime import datetime, timedelta, timezone
import time
import os
import re
import yaml

# Config
ORG_NAME = "imageomics"
SPREADSHEET_ID = "1NOVB9IfBvkAh4YDbozhi5q0iwBfyp3enD6UxmO6wHIA"
SHEET_NAME = "Sheet1"

# Helper Functions
def get_repo_url(repo, repo_type: str) -> str:
    if repo_type == "dataset":
        return f"https://huggingface.co/datasets/{repo.id}"
    elif repo_type == "space":
        return f"https://huggingface.co/spaces/{repo.id}"
    else: # model
        return f"https://huggingface.co/{repo.id}"

def get_license(repo) -> str:
    # 1. cardData
    try:
        license_from_card = getattr(repo, "cardData", {}).get("license")
        if license_from_card:
            return license_from_card
    except Exception:
        pass

    # 2. repo.license attribute
    try:
        license_attr = getattr(repo, "license", None)
        if license_attr:
            return license_attr
    except Exception:
        pass

    # 3. YAML content in README
    try:
        readme_text = getattr(repo, "readme", None)
        if readme_text:
            import re, yaml
            match = re.search(r'^---\s*(.*?)\s*---', readme_text, re.DOTALL | re.MULTILINE)
            if match:
                yaml_content = match.group(1)
                data = yaml.safe_load(yaml_content)
                if isinstance(data, dict):
                    return data.get("license", "No")
    except Exception:
        pass

    return "No"

def is_inactive(repo) -> str:
    try:
        last_modified = getattr(repo, "lastModified", None)
        if not last_modified:
            return "N/A"

        # Ensure last_modified is aware (has tzinfo)
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)

        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
        return "Yes" if last_modified < one_year_ago else "No"
    except Exception:
        return "N/A"
    
def get_homepage_link(repo, repo_type: str) -> str:
    try:
        card_data = getattr(repo, "cardData", None)
        if isinstance(card_data, dict) and card_data.get("homepage"):
            return f'=HYPERLINK("{card_data.get("homepage")}", "Homepage")'
    except Exception:
        pass
    
    # Check README for homepage URLs
    try:
        readme_path = hf_hub_download(
            repo_id=repo.id,
            filename="README.md",
            repo_type=repo_type,
            token=os.getenv("HF_TOKEN")
        )
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_text = f.read()
        match = re.search(r'Homepage:\s*(https?://[^\s\n)]+)', readme_text, re.IGNORECASE)
        if match:
            return f'=HYPERLINK("{match.group(1)}", "Homepage")'
    except Exception:
        pass
    
    return "No"

def get_repo_link(repo, repo_type: str) -> str:
    try:
        card_data = getattr(repo, "cardData", None)
        if isinstance(card_data, dict):
            for key in ("repository", "repo", "github_repo"):
                url = card_data.get(key)
                if url and url.startswith("http"):
                    return f'=HYPERLINK("{url}", "Repository")'
    except Exception:
        pass
    
    # Check README for github/repo URLs
    try:
        from huggingface_hub import hf_hub_download
        readme_path = hf_hub_download(
            repo_id=repo.id,
            filename="README.md",
            repo_type=repo_type,
            token=os.getenv("HF_TOKEN")
        )
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_text = f.read()
        match = re.search(r'(https?://(?:github\.com|gitlab\.com)[^\s\n)}\]]+)', readme_text, re.IGNORECASE)
        if match:
            url = match.group(1).rstrip('*`[]()]}')
            return f'=HYPERLINK("{url}", "Repository")'
    except Exception:
        pass
    
    return "No"

def get_paper_link(repo, repo_type: str) -> str:
    try:
        card_data = getattr(repo, "cardData", None)
        if isinstance(card_data, dict) and card_data.get("paper"):
            return f'=HYPERLINK("{card_data.get("paper")}", "Paper")'
    except Exception:
        pass
    
    # Check README for arxiv/paper URLs
    try:
        from huggingface_hub import hf_hub_download
        readme_path = hf_hub_download(
            repo_id=repo.id,
            filename="README.md",
            repo_type=repo_type,
            token=os.getenv("HF_TOKEN")
        )
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_text = f.read()
        match = re.search(r'(https?://(?:arxiv\.org|doi\.org)[^\s\n)}\]]+)', readme_text, re.IGNORECASE)
        if match:
            url = match.group(1).rstrip('*`[]()]}')
            return f'=HYPERLINK("{url}", "Paper")'
    except Exception:
        pass
    
    return "No"

def get_model_card_field(repo, key: str) -> str:
    try:
        value = repo.cardData.get(key, "")
        # Convert to string if it's a list or other type
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value) if value else ""
    except Exception:
        return "N/A"
    
def get_associated_assets(repo) -> str:
    try:
        related = [tag for tag in repo.tags if tag.startswith(("dataset:", "model:", "space:"))]
        return ", ".join(related)
    except Exception:
        return "N/A"
    
def clean_description(desc: str) -> str:
    if not desc:
        return "N/A"
    
    # remove HTML tags
    desc = re.sub(r"<[^>]+>", "", desc)

    # collapse multiple newlines/tabs/spaces into a single space
    desc = re.sub(r"\s+", " ", desc)

    return desc.strip()

def get_doi(repo) -> str:
    try:
        for tag in repo.tags:
            if tag.startswith("doi:"):
                return tag.replace("doi:", "")
    except Exception:
        pass

    return "No"

def get_repo_info(repo, repo_type: str) -> dict[str, str | int]:
    if repo_type == "dataset":
        display_id = f"datasets/{repo.id}"
    elif repo_type == "space":
        display_id = f"spaces/{repo.id}"
    else:
        display_id = repo.id

    return {
        "Repository Name": f'=HYPERLINK("{get_repo_url(repo, repo_type)}", "{display_id}")',
        "Repository Type": repo_type,
        "Description": clean_description(getattr(repo, "description", "")),
        "Date Created": repo.created_at.strftime("%Y-%m-%d") if getattr(repo, "created_at", False) else "N/A",
        "Last Updated": repo.lastModified.strftime("%Y-%m-%d") if getattr(repo, "lastModified", False) else "N/A",
        "Created By": repo.author,
        "Top 4 Contributors/Curators": "test",
        "Likes": getattr(repo, "likes", "N/A"),
        "# of Open PRs": "test",
        "README": "Yes" if getattr(repo, "cardData", False) else "No",
        "License": get_license(repo),
        "Visibility": "Private" if getattr(repo, "private", False) else "Public",
        "Inactive": is_inactive(repo),
        "Homepage": get_homepage_link(repo, repo_type), 
        "Repo": get_repo_link(repo, repo_type),
        "Paper": get_paper_link(repo, repo_type),
        "Associated data, models, or spaces": get_associated_assets(repo),
        "DOI": get_doi(repo), 
    }

# Convert all data types to string representation
def ensure_string_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return str(value)
    return str(value)

def extract_display_name(val: str) -> str:
    match = re.search(r'"([^"]+)"\)$', val) # regex to extract the repo-name from "=HYPERLINK(..., "repo-name")"
    return match.group(1) if match else val

def update_google_sheet(df: pd.DataFrame) -> None:
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
            value = ensure_string_value(value)
            cell = gspread.utils.rowcol_to_a1(row_idx, col_idx)

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
        "Visibility",
        "Inactive",
        "Homepage", 
        "Repo",
        "Paper",
        "Associated data, models, or spaces",
    }

    orange_columns = {
        "DOI"
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

# -------

def main():

    TOKEN = os.getenv("HF_TOKEN") or input("Enter your Hugging Face token: ").strip()

    start_time = time.time()

    api = HfApi(token=TOKEN)

    try:
        repos = []

        for m in api.list_models(author=ORG_NAME, full=True):
            repos.append((api.model_info(m.id), "model"))

        for d in api.list_datasets(author=ORG_NAME, full=True):
            repos.append((api.dataset_info(d.id), "dataset"))

        for s in api.list_spaces(author=ORG_NAME, full=True):
            repos.append((api.space_info(s.id), "space"))

    except Exception as e:
        print(f'ERROR: Could not fetch models for "{ORG_NAME}"')
        print(e)
        return

    print("")
    print(f"Fetching Hugging Face repositories for: {ORG_NAME}")
    print("")
    print("----------------")

    data = []

    tqdm_kwargs = {}
    if os.environ.get("CI") == "true":
        tqdm_kwargs = {"mininterval": 1, "dynamic_ncols": False, "leave": False}

    for repo, repo_type in tqdm(repos, desc=f"Fetching HF repos from {ORG_NAME}...", unit="repo", colour="green", ncols=100, **tqdm_kwargs):
        try:
            info = get_repo_info(repo, repo_type)
            data.append(info)
            tqdm.write(f"Fetched info for /{repo.id}")
        except Exception as e:
            tqdm.write(f"ERROR: Cannot fetch /{repo.id} info, due to {type(e).__name__}: {e}. Skipping...")
    
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