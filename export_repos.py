import os
import pandas as pd
from github import Github, GithubException

# Config
TOKEN = input("Enter your GitHub token: ").strip()
ORG_NAME = "Imageomics"
OUTPUT_FILE = f"{ORG_NAME}_repo_info.xlsx"


# helper functions
def get_file(repo, path):
    try:
        return repo.get_contents(path)
    except GithubException:
        return "N/A"
    
def get_readme(repo):
    try:
        return repo.get_readme()
    except GithubException:
        return "N/A"


def get_license(repo):
    try:
        return repo.get_license()
    except GithubException:
        return "N/A"
        
def get_num_branches(repo):
    try:
        return repo.get_branches().totalCount
    except:
        return "N/A"
    
def get_repo_info(repo):
    return {
        "Name": repo.name,
        "Description": repo.description or "N/A",
        "Has README": "Yes" if get_readme(repo) != "N/A" else "No",
        "Has License": "Yes" if get_license(repo) != "N/A" else "No",
        "Has .gitignore": "Yes" if get_file(repo, ".gitignore") != "N/A" else "No",
        "Branches": get_num_branches(repo),
    }



def main():
    gh = Github(TOKEN)
    try:
        org = gh.get_organization(ORG_NAME)
    except Exception as e:
        print(f"ERROR: Could not access org: \"{ORG_NAME}\"")
        return
    
    print(f"Fetching repositories from organization {ORG_NAME}")

    repos = org.get_repos()
    data = []

    for repo in repos:
        print(f"Fetching info for /{repo.name} repo")
        try:
            info = get_repo_info(repo)
            data.append(info)
        except Exception as e:
            print(f"ERROR: Cannot fetch /{repo} info, skipping...")

    if not data:
        print("ERROR: No data collected")
        return
    
    df = pd.DataFrame(data)
    df.sort_values(by="Name", inplace=True)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Finished fetching info for {len(df)} repositories from {ORG_NAME} to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()