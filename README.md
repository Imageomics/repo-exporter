# Repository Exporter

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
- Exports everything to a given Google Sheet document that it will require Editor permission to on the sheet's sharing permissions list.
- Highlights “No” fields for Standard files with red cell colors and highlights 

## Usage

1. Clone this repository:
    ```
    git clone https://github.com/Imageomics/repo-exporter.git
    cd repo-exporter
    ```

2. Install Python dependencies:
    ```
    pip install -r requirements.txt
    ```

3. Run the script:
    ```
    python export_repos.py
    ```

4. Enter your GitHub Personal Access Token
  
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
   **Note:** The token must be approved by the organization administrator before accessing private repositories.

5. Create a Google Cloud Console Service Account and give it permission to use in the repository and in the Google sheet

   1. Go to https://console.cloud.google.com/
   2. Create a **new project** and name it **inventory**
   3. Go to https://console.cloud.google.com/iam-admin/serviceaccounts, if you have multiple projects you'll need to **select the project** that you just made if it hasn't already been selected
   4. Create a **service account**, for the name enter **Imageomics**, for the service account ID enter **repo-exporter**, enter a description: "Repo checklist automatation account"
   5. Click on the **service account email** -> **Keys** -> **Add key** -> **Create new key** and select **JSON** then finally click **Create**
   7. Go to https://github.com/Imageomics/repo-exporter/settings/secrets/actions and click **New repository secret** and name it **GOOGLE_SERVICE_ACCOUNT_JSON** and copy paste the entire contents of the JSON file into the **Secret** section and click **Add secret**
   8. Go to https://console.cloud.google.com/apis/library/sheets.googleapis.com and enable the **Google Sheets API** for the project you made
   9. Go to your chosen Google Spreadsheet and go to **Share** settings and add the new Service Account email you made and set it as an **Editor**
