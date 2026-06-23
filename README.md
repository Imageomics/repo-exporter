# Repository Exporter [![DOI](https://zenodo.org/badge/1080019710.svg)](https://doi.org/10.5281/zenodo.17835081)

Python scripts that gather metadata for all repositories in a provided GitHub or Hugging Face organization and automatically exports the data into a desired Google Sheet (using a Google Cloud Console Service Account) for easy viewing and analysis.

## Contents
- [Features](#features)  
- [Usage](#usage)  
- [Set up your own GitHub Actions workflow](#set-up-your-own-github-actions-workflow)  
  - [Create a GitHub Personal Access Token](#create-a-github-personal-access-token)
  - [Create a Hugging Face Token](#create-a-hugging-face-token)   
  - [Set up Google Cloud Service Account Access](#set-up-google-cloud-service-account-access)  
- [Run repo exporter locally](#run-repo-exporter-locally)  
- [Environment Variables](#environment-variables)  
- [Testing](#testing)

---

## Features
- Fetches all repositories in the indicated GitHub or Hugging Face organization(s)
- Collects key details:
  - Repo visibility, name (hyperlinked to repo), and description
  - Date created and last updated, with a flag for inactivity (set after a year of no commits)
  - Creator and top 4 contributors (`N/A` creator means it was either a transferred repository or a forked repository and `None (<GitHub Username>)` means there was no full name attached to their GitHub account)
  - Number of stars and number of branches for GitHub repositories, for Hugging Face repos, the analogous number of likes and open Discussions/PRs are collected
  - Standard file/metadata checks:
      - **For GitHub:** `README.md`, license, `.gitignore`, package requirements (`requirements.txt`, `environment.yaml`, etc.), `CITATION.cff`, `.zenodo.json`, and `CONTRIBUTING.md` files
      - **For Hugging Face:** `README.md` ([dataset or model card](https://imageomics.github.io/Collaborative-distributed-science-guide/wiki-guide/About-Templates/)/Space README) and license (read from `yaml`)
      - DOI for the repository (HF generated or from Zenodo for GitHub repos)
  - Primary Programming Language (**GitHub only**)
  - Website Reference/Homepage, Associated Dataset(s), Model(s), or Paper(s), and associated [GitHub] repo for Hugging Face repositories
  - Supports configurable worksheet names with defaults:
    - Github: `GH_SHEET_NAME` defaults to `GH-Repos`
    - Hugging Face: `HF_SHEET_NAME` defaults to `HF-Repos`
- Exports everything to a given Google Sheet document that it will require Editor permission to on the sheet's sharing permissions list
- For [**Standard Files**](https://imageomics.github.io/Collaborative-distributed-science-guide/wiki-guide/GitHub-Repo-Guide/#standard-files) highlights **No** data cell values with red cell colors and for [**Recommended Files**](https://imageomics.github.io/Collaborative-distributed-science-guide/wiki-guide/GitHub-Repo-Guide/#recommended-files) and **Filters** highlights **No** data cell values with orange cell colors

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
      - **Administration** -> Read-only
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

After cloning the repository, configure the [environment variables](#environment-variables) required for the exporter(s) you plan to run.

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
    
3. Configure environment variables using a `.env` file

Create a `.env` file in the root of the project:

```bash
GH_TOKEN=your-token-here
GH_ORG_NAME=your-github-org
SPREADSHEET_ID=your-google-sheet-id
GH_SHEET_NAME=GH-Repos

HF_TOKEN=your-huggingface-token
HF_ORG_NAME=your-huggingface-org
HF_SHEET_NAME=HF-Repos

GOOGLE_CREDENTIALS_PATH=/path/to/service_account.json
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

## Environment Variables

> [!NOTE]
> * `gh_repo_exporter.py` requires the `GH_*` and `SPREADSHEET_ID`. 
> * `hf_repo_exporter.py` requires the `HF_*` and `SPREADSHEET_ID`. 
> * Both exporters support optional sheet name variables (`GH_SHEET_NAME` and `HF_SHEET_NAME`) and require Google service account credentials.

### GitHub exporter

* Set `GH_ORG_NAME` to your GitHub organization name (for API calls).
* Set `SPREADSHEET_ID` to the Google Sheet ID used by the exporter.
* `GH_SHEET_NAME` is optional. If not provided, the exporter uses "GH-Repos".
* `GH_TOKEN` is required to access GitHub repositories.

### Hugging Face exporter

* Set `HF_ORG_NAME` to your Hugging Face organization name (**case-sensitive**, for API calls).
* Set `SPREADSHEET_ID` to the Google Sheet ID used by the exporter.
* `HF_SHEET_NAME` is optional. If not provided, the exporter uses "HF-Repos".
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
