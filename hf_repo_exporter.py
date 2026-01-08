from huggingface_hub import HfApi, hf_hub_download
import pandas as pd
from tqdm import tqdm
from google.oauth2.service_account import Credentials
import gspread

from datetime import datetime, timedelta, timezone
import time
import os
import re
from collections import Counter

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

def get_author(api, repo_id, repo_type) -> str:
    try:
        # Fetch all commits
        commits = api.list_repo_commits(repo_id=repo_id, repo_type=repo_type)
        if not commits:
            return ORG_NAME

        # The last item in the list is the earliest commit (the creation)
        first_commit = commits[-1]
        
        if hasattr(first_commit, 'authors') and first_commit.authors:
            first_author = first_commit.authors[0]
            
            # Use our string vs object logic from before
            if isinstance(first_author, str):
                return first_author
            
            # If it's an object, check for user handle then display name
            return getattr(first_author, 'user', getattr(first_author, 'name', ORG_NAME))
            
        return ORG_NAME
    except Exception:
        return ORG_NAME

def get_top_contributors(api, repo_id, repo_type) -> str:
    try:
        commits = api.list_repo_commits(repo_id=repo_id, repo_type=repo_type)
        
        all_handles = []
        for c in commits:
            authors = getattr(c, 'authors', [])
            for author in authors:
                # If author is a string (as shown in your logs), use it.
                # If it's an object, try to get .user or .name
                if isinstance(author, str):
                    all_handles.append(author)
                else:
                    handle = getattr(author, 'user', getattr(author, 'name', None))
                    if handle:
                        all_handles.append(str(handle))
            
        # Filter out the Org name and the web-flow bot
        bots_and_orgs = {ORG_NAME.lower(), "web-flow"}
        filtered = [n for n in all_handles if str(n).lower() not in bots_and_orgs]

        if not filtered:
            return ORG_NAME

        counts = Counter(filtered)
        # Get top 4 most common contributors
        top_4 = [name for name, count in counts.most_common(4)]
        return ", ".join(top_4)
    except Exception as e:
        # Optional: tqdm.write(f"Error for {repo_id}: {e}")
        return ORG_NAME

def get_open_pr_count(api, repo_id, repo_type) -> int:
    try:
        # Fetch discussions filtered by pull_requests only
        discussions = api.get_repo_discussions(
            repo_id=repo_id, 
            repo_type=repo_type
        )
        # Count how many are pull requests AND are currently open
        open_prs = [d for d in discussions if d.is_pull_request and d.status == "open"]
        return len(open_prs)
    except Exception:
        return 0

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

def get_card_field(repo, keys: list) -> str:
    try:
        for key in keys:
            value = repo.card_data.get(key, "")
            if value:
                # Convert to string if it's a list or other type
                if isinstance(value, list):
                    return ", ".join(str(v) for v in value)
                return str(value) if value else ""
    except Exception:
        pass
    return "N/A"
def get_associated_datasets(repo) -> str:
    try:
        # Looking for tags like 'dataset:user/repo'
        datasets = [tag.replace("dataset:", "") for tag in getattr(repo, "tags", []) if tag.startswith("dataset:")]
        return ", ".join(datasets) if datasets else "No"
    except Exception:
        return "No"

def get_associated_models(api, repo, repo_type) -> str:
    found = []
    repo_id = getattr(repo, 'id', str(repo))

    if repo_type == "dataset":
        tqdm.write(f"--- Searching Models for Dataset: {repo_id} ---")
        try:
            # Again, using 'search' to find any model mentioning this dataset
            related_models = list(api.list_models(search=repo_id))
            if related_models:
                found = [m.id for m in related_models if m.id != repo_id]
                tqdm.write(f"   [Search] Found {len(found)} models")
        except Exception as e:
            tqdm.write(f"   [Search] Error: {e}")

    return ", ".join(found) if found else "No"

def get_associated_spaces(api, repo_id) -> str:
    found = set()
    
    # Ensure we are using the clean string ID
    clean_id = repo_id.id if hasattr(repo_id, 'id') else str(repo_id)
    
    try:
        # 1. Broad Metadata Search
        # We search specifically for the ID in the 'models' metadata field
        # Note: We use list() to ensure the generator is fully exhausted
        spaces_by_model = list(api.list_spaces(filter=f"models:{clean_id}"))
        for s in spaces_by_model:
            found.add(s.id)
            
        # 2. String-based Search (The "Catch-all")
        # This finds spaces that mention it but didn't use the standard YAML format
        spaces_by_search = list(api.list_spaces(search=clean_id))
        for s in spaces_by_search:
            found.add(s.id)

        # 3. Handle specific Org-level associations
        # Sometimes spaces are linked but not indexed under the ID
        # Let's filter out the self-reference
        if clean_id in found:
            found.remove(clean_id)

    except Exception as e:
        tqdm.write(f"Error for {clean_id}: {e}")

    if not found:
        return "No"
    
    # Sort and format
    sorted_found = sorted(list(found))
    return ", ".join(sorted_found)

def get_doi(repo) -> str:
    try:
        # 1. Check if the DOI is a direct attribute
        if hasattr(repo, 'doi') and repo.doi:
            return str(repo.doi).replace("doi:", "")

        # 2. Check the metadata dictionary if it exists
        if hasattr(repo, 'card_data') and repo.card_data:
            doi = repo.card_data.get('doi')
            if doi:
                return str(doi).replace("doi:", "")

        # 3. Fallback to the tags loop (for manually tagged DOIs)
        if hasattr(repo, 'tags') and repo.tags:
            for tag in repo.tags:
                if isinstance(tag, str) and tag.lower().startswith("doi:"):
                    return tag.replace("doi:", "").replace("DOI:", "")
                    
    except Exception as e:
        pass

    return "No"

def extract_link_from_text(text, label):
    if not text:
        return "No"

    # Pattern to find 'Label: ...' anywhere in the text
    # Added \b to ensure we match the exact word
    pattern = rf"\b{label}\b:\s*([^\r\n]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        content = match.group(1).strip()
        # Remove common markdown junk: *, _, `, [, ]
        content = re.sub(r'[*_`\[\]]', '', content).strip()
        
        # Filter out placeholders
        if content.upper() in ["N/A", "NONE", "", "NULL", "TBA", "COMING SOON", "IN PROGRESS", "TBD", "-->"]:
            return "No"

        # If it contains an http link, create a clean HYPERLINK formula
        if "http" in content.lower():
            url_match = re.search(r'(https?://[^\s)]+)', content)
            if url_match:
                url = url_match.group(1).rstrip('.,)]')
                # Use the text before the '(' as the label, or the default label
                display_text = content.split('(')[0].strip() or label
                # Double up quotes for Google Sheets formula safety
                display_text = display_text.replace('"', '""')
                return f'=HYPERLINK("{url}", "{display_text}")'
        
        return content
    return "No"

def get_repo_info(api, repo, repo_type: str) -> dict[str, str | int]:

    # 1. Download README once
    readme_text = ""
    try:
        path = hf_hub_download(
            repo_id=repo.id, 
            filename="README.md", 
            repo_type=repo_type,
            token=os.getenv("HF_TOKEN")
        )
        with open(path, 'r', encoding='utf-8') as f:
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
        "Repository Name": f'=HYPERLINK("{get_repo_url(repo, repo_type)}", "{display_id}")',
        "Repository Type": repo_type,
        "Description": get_card_field(repo, ["model_description", "description"]) or "N/A",
        "Date Created": repo.created_at.strftime("%Y-%m-%d") if getattr(repo, "created_at", False) else "N/A",
        "Last Updated": repo.lastModified.strftime("%Y-%m-%d") if getattr(repo, "lastModified", False) else "N/A",
        "Created By": get_author(api, repo.id, repo_type),
        "Top 4 Contributors/Curators": get_top_contributors(api, repo.id, repo_type),
        "Likes": getattr(repo, "likes", "N/A"),
        "# of Open PRs": get_open_pr_count(api, repo.id, repo_type),
        "README": "Yes" if getattr(repo, "cardData", False) else "No",
        "License": get_license(repo),
        "Visibility": "Private" if getattr(repo, "private", False) else "Public",
        "Inactive": is_inactive(repo),
        "Homepage": extract_link_from_text(readme_text, "Homepage"), 
        "Repo": extract_link_from_text(readme_text, "Repository"),
        "Paper": extract_link_from_text(readme_text, "Paper"),
        "Associated Datasets": get_associated_datasets(repo),
        "Associated Models": get_associated_models(api, repo, repo_type),
        "Associated Spaces": get_associated_spaces(api, repo),
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
        "Repo",
        "Paper"
    }

    yellow_columns = {
        "Associated Datasets",
        "Associated Models",
        "Associated Spaces",
        "DOI"
    }

    rules = []

    # Only loop over columns that need formatting
    for col_set, color in [(red_columns, {"red": 1, "green": 0.5, "blue": 0.5}),
                        (yellow_columns, {"red": 1, "green": 0.8, "blue": 0.4})]:

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
            info = get_repo_info(api, repo, repo_type)
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