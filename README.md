# Repository Exporter [![DOI](https://zenodo.org/badge/1080019710.svg)](https://doi.org/10.5281/zenodo.17835081)

A Python script that gathers metadata for all repositories in a GitHub organization and automatically exports the data into a desired Google Sheet (using a Google Cloud Console Service Account) for easy viewing and analysis.

## Contents
- [Features](#features)  
- [Usage](#usage)  
- [Set up your own GitHub Actions workflow](#set-up-your-own-github-actions-workflow)  
  - [Create a GitHub Personal Access Token](#create-a-github-personal-access-token)
  - [Create a Hugging Face Token](#create-a-hugging-face-token)   
  - [Set up Google Cloud Service Account Access](#set-up-google-cloud-service-account-access)  
- [Run repo exporter locally](#run-repo-exporter-locally)  
- [Important Notes](#important-notes)  
- [Testing](#testing)

---

## Features
- Fetches all repositories in an organization
- Collects key details:
  - Repo visibility, name and description
  - Date created and last updated
  - Creator and top 4 contributors (`N/A` creator means it was either a transferred repository or a forked repository and `None (<GitHub Username>)` means there was no full name attached to their github account)
  - Number of stars and number of branches
  - README, license, `.gitignore`, package requirements (`requirements.txt`, `environment.yaml`, etc.), `CITATION.cff`, `.zenodo.json` and `CONTRIBUTING.md` files presence
  - Primary Programming Language
  - Website Reference, Dataset, Model, Paper Association, DOI for GitHub Repo presence
- Exports everything to a given Google Sheet document that it will require Editor permission to on the sheet's sharing permissions list
- For **Standard Files** highlights **No** data cell values with red cell colors and for **Recommended Files** and **Filters** highlights **No** data cell values with orange cell colors 

## Usage
The workflow runs automatically each week (9am UTC on Mondays); however, you can also run the GitHub Actions workflow manually:

   1. Go to the [Actions tab](https://github.com/Imageomics/repo-exporter/actions)
   2. Click **Update Metadata for GitHub Repository Sheet**
   3. Click **Run workflow**, with branch as **Branch: main**, with selection **all** and finally press **Run workflow**

## Set up your own GitHub Actions workflow

To use this script within your own GitHub organization, first fork this repo, then follow the setup steps below to ensure proper access.

### Create a GitHub Personal Access Token
  
  To create one with permissions for both private and public repositories (public repository read-access only is enabled by default without adminstrator approval):
   
  1. Go to [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
  2. Click **Generate new token -> Fine-grained token**
  3. Under **Resource owner**, select the **organization** you want to access.
  4. Under **Repository access**, choose **All repositories**.
  5. Under **Permissions** select **Repositories** and set:
      - **Metadata** -> Read-only 
      - **Contents** -> Read-only
      - **Adminstration** -> Read-only
  6. Click **Generate token** and **copy it** (make sure to store it somewhere safe for future use).
  7. Navigate to `https://github.com/<gh-org-name>/repo-exporter/settings/secrets/actions` and click **New repository secret** and name it **GH_TOKEN** and copy paste the token into the **Secret** section and click **Add secret**
  **Note:** The token must be approved by the organization administrator before accessing private repositories.

### Create a Hugging Face Token

  To create one with permissions for both private and public repositoriesL

  1. Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
  2. Click on **New Token** and name it **repo-exporter**
  3. For permissions select **Fine-grained**:
      - Specify the desired organization (under **Org permissions**)
      - Under **Repositories**, select "Read access to contents of all repos in selected organizations"
  4. Click **Generate** and **copy it** (make sure to store it somewhere safe for future use)
  5. Navigate to `https://github.com/<gh-org-name>/repo-exporter/settings/secrets/actions` and click **New repository secret** and name it **HF_TOKEN** and copy paste the token into the **Secret** section and click **Add secret** 

### Set up Google Cloud Service Account Access

Instructions to create a Google Cloud Console Service Account and give it permission to use in the repository and in the Google sheet:

 1. Go to https://console.cloud.google.com/
 2. Under "IAM & Admin", create a **new project** and name it **inventory**
 3. Go to https://console.cloud.google.com/iam-admin/serviceaccounts, if you have multiple projects you'll need to **select the project** that you just made if it hasn't already been selected
 4. Create a **service account**, named **Imageomics**, with description: "Repo checklist automation account" and finally press **Done** (You do not need to add any Permissions or Principals with access)
 5. Click on the **service account email** -> **Keys** -> **Add key** -> **Create new key** and select **JSON** then finally click **Create**
 7. Go to `https://github.com/<gh-org-name>/repo-exporter/settings/secrets/actions` and click **New repository secret** and name it **GOOGLE_SERVICE_ACCOUNT_JSON** and copy paste the entire contents of the JSON file into the **Secret** section and click **Add secret**
 8. Go to https://console.cloud.google.com/apis/library/sheets.googleapis.com and enable the **Google Sheets API** for the project you made
 9. Go to your chosen Google Sheet and go to **Share** settings and add the new Service Account email you made and set it as an **Editor**

After forking the repository, configure the environment variables required for the exporter(s) you plan to run.

### GitHub exporter

- `GH_ORG_NAME` — GitHub organization name
- `GH_SPREADSHEET_ID` — Google Sheet ID for GitHub export data
- `GH_SHEET_NAME` — worksheet tab used by the GitHub exporter
- `GH_TOKEN` — GitHub access token

### Hugging Face exporter

- `HF_ORG_NAME` — Hugging Face organization name
- `HF_SPREADSHEET_ID` — Google Sheet ID for Hugging Face export data
- `HF_SHEET_NAME` — worksheet tab used by the Hugging Face exporter
- `HF_TOKEN` — Hugging Face access token

### Shared

- `GOOGLE_CREDENTIALS_PATH` — path to the Google service account JSON file when running locally
- `GOOGLE_SERVICE_ACCOUNT_JSON` — GitHub Actions secret containing the service account JSON

Once configured, the workflow can be run by following the [Usage Instructions](#usage).

## Run repo exporter locally
   
1. Clone this repository:
    ```
    git clone https://github.com/Imageomics/repo-exporter.git
    cd repo-exporter
    ```

2. Create and activate the Conda environment:
   ```
   conda create -n repo-exporter python -y
   conda activate repo-exporter
   ```
    
3. Configure only the variables required for the exporter(s) you plan to run.

```bash
# GitHub exporter variables
conda env config vars set GH_TOKEN="<your-token-here>"
conda env config vars set GH_ORG_NAME="<your-github-org>"
conda env config vars set GH_SPREADSHEET_ID="<your-google-sheet-id>"
conda env config vars set GH_SHEET_NAME="<your-sheet-name>"

# Hugging Face exporter variables
conda env config vars set HF_TOKEN="<your-huggingface-token-here>"
conda env config vars set HF_ORG_NAME="<your-huggingface-org>"
conda env config vars set HF_SPREADSHEET_ID="<your-google-sheet-id>"
conda env config vars set HF_SHEET_NAME="<your-sheet-name>"

# Shared variables
conda env config vars set GOOGLE_CREDENTIALS_PATH="/path/to/service_account.json"

conda deactivate
conda activate repo-exporter
```

4. Install Python dependencies:
    ```
    pip install -r requirements.txt
    ```
    
5. Run the exporters

   You can run **either exporter individually** or **both**, depending on your needs:

    - **Run only the GitHub repository exporter**
      ```
      python gh_repo_exporter.py
      ```

    - **Run only the Hugging Face repository exporter**
      ```
      python hf_repo_exporter.py
      ```

    - **Run both exporters (wait for one to finish before running the other)**
      ```
      python hf_repo_exporter.py
      python gh_repo_exporter.py
      ```

## Important Notes

* `gh_repo_exporter.py` only requires the `GH_*` environment variables.
* `hf_repo_exporter.py` only requires the `HF_*` environment variables.
* Both exporters require Google service account credentials.

### GitHub exporter

* Set `GH_ORG_NAME` to your GitHub organization name (for API calls).
* Set `GH_SPREADSHEET_ID` to the Google Sheet ID used by the GitHub exporter.
* Set `GH_SHEET_NAME` to the worksheet tab used by the GitHub exporter.
* `GH_TOKEN` is required to access GitHub repositories.

### Hugging Face exporter

* Set `HF_ORG_NAME` to your Hugging Face organization name (**case-sensitive**, for API calls).
* Set `HF_SPREADSHEET_ID` to the Google Sheet ID used by the Hugging Face exporter.
* Set `HF_SHEET_NAME` to the worksheet tab used by the Hugging Face exporter.
* `HF_TOKEN` is required to access Hugging Face repositories.

### Shared configuration

* Both exporters require `GOOGLE_CREDENTIALS_PATH`.
* The Google service account must have Editor access to the target spreadsheet.
* If both exporters write to the same spreadsheet or worksheet, you may reuse the same spreadsheet IDs and sheet names.
* Ensure all required values are available as environment variables locally or as GitHub Actions secrets.

For example, if the spreadsheet URL is:

```text id="1i7ltb"
https://docs.google.com/spreadsheets/d/fake-long-alpha-numeric-id-1a2b3c4d/edit
```

then the spreadsheet ID is:

```text id="04f0vl"
fake-long-alpha-numeric-id-1a2b3c4d
```


---

## Testing

Follow the [local install instructions](#run-repo-exporter-locally), then run the following in your `repo-exporter` environment:
   ```console
   python -m pytest -q
   ```