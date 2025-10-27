# Repository Exporter

A Python script that automatically gathers metadata for all repositories in a GitHub organization and exports it to a color-coded Excel spreadsheet for easy viewing and analysis.

## Features
- Fetches all repositories in an organization  
- Collects key details:
  - Name and description  
  - Date created and last updated  
  - Creator and top 4 contributors  
  - Number of stars 
  - README, license, `.gitignore`, `CITATION.cff`, and Package requirements (`requirements.txt`, `environment.yaml`, etc.) presence   
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
py export_repos.py
```

4. Enter your GitHub Personal Access Token (Create one by: [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens) -> Generate new token -> Set the organization you want to read for the token).
