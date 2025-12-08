# Repository Exporter [![DOI](https://zenodo.org/badge/1080019710.svg)](https://doi.org/10.5281/zenodo.17835081)

A Python script that gathers metadata for all repositories in a GitHub organization and automatically exports the data into a desired Google Sheet (using a Google Cloud Console Service Account) for easy viewing and analysis.

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

3. Enter your GitHub Personal Access Token
  
   To create one with permissions for both private and public repositories (public repository read-access only is enabled by default without adminstrator approval):
   
   1. Go to [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
   2. Click **Generate new token → Fine-grained token**
   3. Under **Resource owner**, select the **organization** you want to access.
   4. Under **Repository access**, choose **All repositories**.
   5. Under **Permissions** select **Repositories** and set:
      - **Metadata** -> Read-only 
      - **Contents** -> Read-only
      - **Adminstration** -> Read-only
   6. Click **Generate token** and **copy it** (make sure to store it somewhere safe for future use).
   7. Navigate to `https://github.com/<gh-org-name>/repo-exporter/settings/secrets/actions` and click **New repository secret** and name it **GH_TOKEN** and copy paste the token into the **Secret** section and click **Add secret**
   **Note:** The token must be approved by the organization administrator before accessing private repositories.

### Set up Google Cloud Service Account Access

Instructions to create a Google Cloud Console Service Account and give it permission to use in the repository and in the Google sheet:

   1. Go to https://console.cloud.google.com/
   2. Under "IAM & Admin", create a **new project** and name it **inventory**
   3. Go to https://console.cloud.google.com/iam-admin/serviceaccounts, if you have multiple projects you'll need to **select the project** that you just made if it hasn't already been selected
   4. Create a **service account**, named **Imageomics**, with description: "Repo checklist automation account" and finally press **Done** (You do not need to add any Permissions or Principals with access)
   5. Click on the **service account email** -> **Keys** -> **Add key** -> **Create new key** and select **JSON** then finally click **Create**
   7. Go to https://github.com/Imageomics/repo-exporter/settings/secrets/actions and click **New repository secret** and name it **GOOGLE_SERVICE_ACCOUNT_JSON** and copy paste the entire contents of the JSON file into the **Secret** section and click **Add secret**
   8. Go to https://console.cloud.google.com/apis/library/sheets.googleapis.com and enable the **Google Sheets API** for the project you made
   9. Go to your chosen Google Sheet and go to **Share** settings and add the new Service Account email you made and set it as an **Editor**

Now update the script with [your GitHub Organization name](https://github.com/Imageomics/repo-exporter/blob/d3b5ac782d9a4853abe162267dcddcbd7a0862a9/export_repos.py#L13) and the [desired spreadsheet ID](https://github.com/Imageomics/repo-exporter/blob/d3b5ac782d9a4853abe162267dcddcbd7a0862a9/export_repos.py#L14), then the script can be run through the GitHub Actions workflow by following the [Usage Instructions](#usage) for your repository.

## Run repo exporter locally
   
1. Clone this repository:
    ```
    git clone https://github.com/Imageomics/repo-exporter.git
    cd repo-exporter
    ```

2. Create and activate Conda environment:
   ```
   conda create -n repo-exporter python -y
   conda activate repo-exporter
   ```
    
3. Add required environment variables into your Conda environment and reload environment:
    ```
    conda env config vars set GH_TOKEN="<your-token-here>"
    conda env config vars set GOOGLE_CREDENTIALS_PATH="/path/to/service_account.json"

    conda deactivate
    conda activate repo-exporter
    ```

4. Install Python dependencies:
    ```
    pip install -r requirements.txt
    ```
    
5. Run the program
    ```
    python export_repos.py
    ```

## Important Notes

 Key edits to ensure the script functions properly for _your organization_:
  1. You must enter your specific [GitHub Organization Name](https://github.com/Imageomics/repo-exporter/blob/d3b5ac782d9a4853abe162267dcddcbd7a0862a9/export_repos.py#L13) under Config settings at the top of the Python script file (for example, `Imageomics`)
  2. You must enter your specific Google Sheet ID under Config settings at the top of the Python script file (for example, if the URL is `https://docs.google.com/spreadsheets/d/15BQimTjaOyo-jeaJRcg1Hia-9ORcilj3Jx-ks-uGyoc/edit?gid=0#gid=0`, then `15BQimTjaOyo-jeaJRcg1Hia-9ORcilj3Jx-ks-uGyoc` is the [Google Sheet ID](https://github.com/Imageomics/repo-exporter/blob/d3b5ac782d9a4853abe162267dcddcbd7a0862a9/export_repos.py#L14))
  3. You must enter your specific [Google Sheet Section Name](https://github.com/Imageomics/repo-exporter/blob/d3b5ac782d9a4853abe162267dcddcbd7a0862a9/export_repos.py#L15). This can be found at the bottom of your Google Sheet (for example, `Sheet1`)

---

## Testing

Follow the [local install instructions](#run-repo-exporter-locally), then run the following in your `repo-exporter` environment:
   ```console
   python -m pytest -q
   ```
