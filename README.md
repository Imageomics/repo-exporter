# Repository Exporter [![DOI](https://zenodo.org/badge/1080019710.svg)](https://doi.org/10.5281/zenodo.17835081)

Python package that gathers metadata for all repositories in a provided GitHub or Hugging Face organization, or for a specific list of repositories, and automatically exports the data into a designated Google Sheet (using a Google Cloud Console Service Account) for easy viewing and analysis.

## Contents
- [Features](#features)  
- [Usage](#usage)  
- [Set up your own GitHub Actions workflows](#set-up-your-own-github-actions-workflows)  
  - [Create a GitHub App for Organization Access](#create-a-github-app-for-organization-access)
  - [Create a Hugging Face Token](#create-a-hugging-face-token)   
  - [Set up Google Cloud Service Account Access](#set-up-google-cloud-service-account-access)  
- [Run repo exporter locally](#run-repo-exporter-locally)   
  - [Export a specific list of repositories](#export-a-specific-list-of-repositories)
  - [Command-line options](#command-line-options)
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
      - **For GitHub:** `README.md`, license, `.gitignore`, package requirements (`requirements.txt`, `environment.yaml`, etc.), `CITATION.cff`, `.zenodo.json`, `CONTRIBUTING.md`, and `AGENTS.md` files
      - **For Hugging Face:** `README.md` ([dataset or model card](https://imageomics.github.io/Collaborative-distributed-science-guide/wiki-guide/About-Templates/)/Space README) and license (read from `yaml`)
      - DOI for the repository (HF generated or from Zenodo for GitHub repos)
      - Repo keywords (**GitHub:** repository topics; **Hugging Face:** tags from the model/dataset/Space card)
  - Primary Programming Language (**GitHub only**)
  - Website Reference/Homepage, Associated Dataset(s), Model(s), or Paper(s), and associated [GitHub] repo for Hugging Face repositories
  - Supports configurable worksheet names with defaults:
    - GitHub: `GH_SHEET_NAME` defaults to `GH-Repos`
    - Hugging Face: `HF_SHEET_NAME` defaults to `HF-Repos`
- Exports everything to a given Google Sheet document that it will require Editor permission to on the sheet's sharing permissions list
- For [**Standard Files**](https://imageomics.github.io/Collaborative-distributed-science-guide/wiki-guide/GitHub-Repo-Guide/#standard-files) highlights **No** data cell values with red cell colors and for [**Recommended Files**](https://imageomics.github.io/Collaborative-distributed-science-guide/wiki-guide/GitHub-Repo-Guide/#recommended-files) and **Filters** highlights **No** data cell values with orange cell colors
-  Supports an opt-in `--error-mode` flag for surfacing repos whose fetch failed entirely (console-only, log file, or a `Status` column in the sheet) so a failure doesn't silently leave a stale row untouched
- Supports exporting a specific list of repositories instead of a whole organization (`--repos` for GitHub; `--models`, `--datasets`, and `--spaces` for Hugging Face)

## Usage
The workflow runs automatically each week (9am UTC on Mondays); however, you can also run the GitHub Actions workflow manually:

   1. Go to the [Actions tab](https://github.com/Imageomics/repo-exporter/actions)
   2. Click **Update Metadata for GitHub Repository Sheet**
   3. Click **Run workflow**, with branch as **Branch: main**, with selection **all** and finally press **Run workflow**

## Set up your own GitHub Actions workflows

To use package within your own GitHub organization, you can either fork this repo or copy the GitHub and Hugging Face workflows into your own tracking repository and update them to `pip install repo-exporter` where we `pip install .`.
For either method, follow the setup steps below to ensure proper access.

### Create a GitHub App for Organization Access

  To create an App with permissions for both private and public repositories **requires Organization Admin access**. Follow the [Catalog App instructions](https://github.com/Imageomics/catalog/blob/main/docs/app-authentication.md), with the following changes:
  - Name it "Repo-exporter Automation App".
  - Description: "App for automated Organization repo-exporter workflows (weekly GitHub Org checks)." (could use your organization name, we use "Imageomics").
  - For permissions, grant ***read-only*** for the same three (contents, pull requests, and metadata (default)).
  - During installation, all repos in the Organization must be allowed (read-only).

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
   
1. Create and activate a Conda environment:
   ```
   conda create -n repo-exporter python -y
   conda activate repo-exporter
   ```
    
2. [RECOMMENDED] Create a `.env` file in the root of the project to configure required [environment variables](#environment-variables). See [`.env.example`](.env.example) for an example; the default sheet names are included and can be removed. Any value in `.env` can also be overridden with a CLI flag. See [Command-line options](#command-line-options) below.


3. Install the package (this installs the `repo-exporter` CLI along with all dependencies, as defined in `pyproject.toml`):
   ```
   pip install repo-exporter
   ```
    
4. Each exporter runs individually with the `repo-exporter` command, specifying the platform as a subcommand:

    - **Run the GitHub repository exporter**
      ```
      repo-exporter github
      ```

    - **Run the Hugging Face repository exporter**
      ```
      repo-exporter huggingface
      ```

    - Check the installed version at any time with:
      ``` 
      repo-exporter --version
      ```

### Export a specific list of repositories

To export only certain repositories instead of an entire organization, provide a list of repositories. Use either an organization **or** a list of repositories, not both.

- **Export specific GitHub repositories** (`owner/repo`, space-separated)
  ```
  repo-exporter github --repos Imageomics/repo-exporter Imageomics/another-repo
  ```

- **Export specific Hugging Face repositories** (`owner/name`, space-separated; the flags can be combined)
  ```
  repo-exporter huggingface --models imageomics/my-model --datasets imageomics/my-dataset imageomics/other-dataset --spaces imageomics/my-space
  ```

When a list is provided:
- `GH_ORG_NAME` and `HF_ORG_NAME` are not required. `SPREADSHEET_ID` and the Google service account credentials are still required.
- `--repo-type` is ignored for GitHub.
- Repositories already in the sheet are updated in place and new ones are added as new rows. Rows for repositories not in the list are left unchanged.
- A repository that cannot be fetched (e.g., a typo or no access) is reported according to the [error handling](#error-handling) mode.

### Command-line options

All options fall back to the corresponding [environment variable](#environment-variables) when omitted, so you can mix and match `.env` values with one-off CLI overrides.

**`repo-exporter github [options]`**

| Flag | Overrides | Description |
|---|---|---|
| `--org` | `GH_ORG_NAME` | GitHub organization name |
| `--repos` | None | Specific repositories to export, as `owner/repo` separated by spaces (use instead of `--org`) |
| `--token` | `GH_TOKEN` | GitHub personal access token |
| `--repo-type` | `GH_REPO_TYPE` | Repo type filter: `all`, `public`, `private`, `forks`, `sources`, `member` (default: `all`; ignored when `--repos` is used) |
| `--spreadsheet-id` | `SPREADSHEET_ID` | Google Sheets spreadsheet ID |
| `--sheet-name` | `GH_SHEET_NAME` | Sheet tab name (default: `GH-Repos`) |
| `--credentials-path` | `GOOGLE_CREDENTIALS_PATH` | Path to `service_account.json` (default: `service_account.json`) |
| `--error-mode` | `ERROR_MODE` | Failure reporting mode: `console`, `log`, or `column` (default: `console`) |
| `--error-log-path` | `ERROR_LOG_PATH` | Path to write errors when `--error-mode=log` (default: `repo_exporter_errors.log`) |

**`repo-exporter huggingface [options]`**

| Flag | Overrides | Description |
|---|---|---|
| `--org` | `HF_ORG_NAME` | Hugging Face organization name (**case-sensitive**) |
| `--models` | None | Specific model repositories to export, as `owner/name` separated by spaces (use instead of `--org`) |
| `--datasets` | None | Specific dataset repositories to export, as `owner/name` separated by spaces (use instead of `--org`) |
| `--spaces` | None | Specific Space repositories to export, as `owner/name` separated by spaces (use instead of `--org`) |
| `--token` | `HF_TOKEN` | Hugging Face token |
| `--spreadsheet-id` | `SPREADSHEET_ID` | Google Sheets spreadsheet ID |
| `--sheet-name` | `HF_SHEET_NAME` | Sheet tab name (default: `HF-Repos`) |
| `--credentials-path` | `GOOGLE_CREDENTIALS_PATH` | Path to `service_account.json` (default: `service_account.json`) |
| `--error-mode` | `ERROR_MODE` | Failure reporting mode: `console`, `log`, or `column` (default: `console`) |
| `--error-log-path` | `ERROR_LOG_PATH` | Path to write errors when `--error-mode=log` (default: `repo_exporter_errors.log`) |

Run `repo-exporter github --help` or `repo-exporter huggingface --help` to see these options from the command line.

## Environment Variables

> [!NOTE]
> `SPREADSHEET_ID` and Google service account credentials are required for both GitHub and Hugging Face exports, as well as an organization name (`GH_ORG_NAME` or `HF_ORG_NAME`), unless you [export a list of repositories](#export-a-specific-list-of-repositories) instead.
> * Both exporters support optional custom sheet name variables (`GH_SHEET_NAME` and `HF_SHEET_NAME`; these must be *distinct*).
> * Any of these values may instead be passed as a CLI flag. See [Command-line options](#command-line-options).

> [!WARNING]  
> Tokens and Google service account credentials must be saved as repository *secrets*. All other values may be saved as environment variables assuming your spreadsheet is appropriately protected.

### GitHub exporter

* Set `GH_ORG_NAME` to your GitHub organization name (for API calls).
* Set `SPREADSHEET_ID` to the Google Sheet ID used by the exporter.
* `GH_SHEET_NAME` is optional. If not provided, the exporter uses "GH-Repos".
* `GH_REPO_TYPE` is optional. If not provided, the exporter uses "all" (also accepts `public`, `private`, `forks`, `sources`, `member`). 
* `GH_TOKEN` is required to access GitHub repositories.

### Hugging Face exporter

* Set `HF_ORG_NAME` to your Hugging Face organization name (**case-sensitive**, for API calls).
* Set `SPREADSHEET_ID` to the Google Sheet ID used by the exporter.
* `HF_SHEET_NAME` is optional. If not provided, the exporter uses "HF-Repos".
* `HF_TOKEN` is required to access Hugging Face repositories.

### Error handling

Applies to both exporters.

* `ERROR_MODE` is optional. Controls how a repo whose fetch fails completely is reported (default: `"console"`):
  - `"console"` prints a message to the console; the repo's existing row in the sheet, if any, is left unchanged.
  - `"log"` prints a message to the console and appends a timestamped entry to `ERROR_LOG_PATH`; the repo's existing row in the sheet, if any, is left unchanged.
  - `"column"` prints a message to the console and writes the error into the repo's `Status` column in the sheet, making failures visible without checking logs. A repo with no existing row gets a new one containing just its name and Status.
* `ERROR_LOG_PATH` is optional. Path to write errors when `ERROR_MODE="log"` (defaults to `repo_exporter_errors.log`).

### Shared configuration

* Both exporters require Google service account credentials created in the [service account setup](#set-up-google-cloud-service-account-access). Set `GOOGLE_CREDENTIALS_PATH` to the JSON key file path (defaults to `service_account.json` if omitted).
* The Google service account must have Editor access to the target spreadsheet.
* Ensure all required values are available as environment variables locally or as GitHub Actions secrets.

For example, if the spreadsheet URL is:

```text
https://docs.google.com/spreadsheets/d/fake-long-alpha-numeric-id-1a2b3c4d/edit
```

then the spreadsheet ID is:

```text
fake-long-alpha-numeric-id-1a2b3c4d
```


---

## Development

To develop the package further:

1. Clone the repository and create a branch.
2. Install the package with dev dependencies in a dedicated environment ([local install instructions](#run-repo-exporter-locally)) at the repo root:
   ```console
    pip install -e ".[dev]"
   ```

### Testing

Run the following in your `repo-exporter` environment to run all tests:
   ```console
   python -m pytest -q
   ```
