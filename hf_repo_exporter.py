from huggingface_hub import HfApi
import pandas as pd
import tqdm
from google.oauth2.service_account import Credentials
import gspread

from datetime import datetime, timedelta, timezone
import time
import os
import re

# Config
ORG_NAME = "imageomics"
SPREADSHEET_ID = "1NOVB9IfBvkAh4YDbozhi5q0iwBfyp3enD6UxmO6wHIA"
SHEET_NAME = "Sheet1"

# Helper Functions
def get_repo_url(repo) -> str:
    if repo._hf_repo_type == "dataset":
        return f"https://huggingface.co/datasets/{repo.id}"
    elif repo._hf_repo_type == "space":
        return f"https://huggingface.co/spaces/{repo.id}"
    else: # model
        return f"https://huggingface.co/{repo.id}"
    
def is_inactive(repo):
    try:
        last_modified = getattr(repo, "lastModified", None)
        if not last_modified:
            return "N/A"

        # Parse ISO 8601 string
        updated = datetime.fromisoformat(last_modified.replace("Z", ""))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)

        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
        return "Yes" if updated < one_year_ago else "No"
    except Exception:
        return "N/A"

def get_model_card_field(repo, key: str) -> str:
    try:
        return repo.cardData.get(key, "")
    except Exception:
        return "N/A"
    
def get_associated_assets(repo) -> str:
    try:
        related = [tag for tag in repo.tags if tag.startswith(("dataset:", "model:", "space:"))]
        return ", ".join(related)
    except Exception:
        return "N/A"

def get_repo_info(repo) -> dict[str, str | int]:
    return {
        "Repository Name": f'=HYPERLINK("{get_repo_url(repo)}", "{repo.id}")',
        "Repository Type": repo._hf_repo_type, 
        "Description": getattr(repo, "description", "N/A"),
        "Date Created": repo.created_at.strftime("%Y-%m-%d") if getattr(repo, "created_at", False) else "N/A",
        "Last Updated": datetime.fromisoformat(repo.lastModified.replace("Z", "")).strftime("%Y-%m-%d") if getattr(repo, "lastModified", False) else "N/A",
        "Created By": repo.author,
        "Top 4 Contributors/Curators": ...,
        "Likes": getattr(repo, "likes", "N/A"),
        "# of Open PRs": ...,
        "README": "Yes" if getattr(repo, "cardData", False) else "No",
        "License": "Yes" if getattr(repo, "license", False) else "No",
        "Visibility": "Private" if getattr(repo, "private", False) else "Public",
        "Inactive": is_inactive(repo),
        "Homepage": get_model_card_field(repo, "homepage"), 
        "Repo": f'=HYPERLINK("{get_model_card_field(repo, "github_repo")}", "{repo.id}")',
        "Paper": f'=HYPERLINK("{get_model_card_field(repo, "paper")}", "Paper")',
        "Associated data, models, or spaces": get_associated_assets(repo),
        "DOI": get_model_card_field(repo, "doi"), 
    }

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

# -------

def main():

    TOKEN = os.getenv("HF_TOKEN") or input("Enter your Hugging Face token: ").strip()

    start_time = time.time()

    api = HfApi(token=TOKEN)

    try:
        models = list(api.list_models(author=ORG_NAME, full=True))
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

    for model in tqdm(models, desc=f"Fetching HF repos from {ORG_NAME}...", unit="repo", colour="green", ncols=100, **tqdm_kwargs):
        try:
            info = get_repo_info(model)
            data.append(info)
            tqdm.write(f"Fetched info for /{model.id}")
        except Exception as e:
            tqdm.write(f"ERROR: Cannot fetch /{model.id} info, due to {type(e).__name__}: {e}. Skipping...")
    
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