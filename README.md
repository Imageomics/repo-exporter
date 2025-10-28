# Repository Exporter

A Python script that automatically gathers metadata for all repositories in a GitHub organization and exports it to a color-coded Excel spreadsheet for easy viewing and analysis.

## Features
- Fetches all repositories in an organization  
- Collects key details:
  - Name and description  
  - Date created and last updated  
  - Creator and top 4 contributors (`Unknown` creator means it was either a transferreed repository or a forked repository and `None (<GitHub Username>)` means there was no full name attached to their github account)
  - Number of stars 
  - README, license, `.gitignore`, `CITATION.cff`, and Package requirements (`requirements.txt`, `environment.yaml`, etc.) presence   
  - Website Reference, Dataset, Paper Associated, DOI for GitHub Repo presence
  - Number of branches
- Exports everything to an Excel file (`<org>_repo_info.xlsx`)  
- Highlights “No” fields with red cell colors  

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
   6. Click **Generate token** and copy it (make sure to store it somewhere safe for future use).

   **Note:** The token must be approved by the organization administrator before accessing private repositories.
