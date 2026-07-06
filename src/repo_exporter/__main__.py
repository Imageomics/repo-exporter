import argparse
import os

from dotenv import load_dotenv
load_dotenv()

from repo_exporter.github import GitHubExporter
from repo_exporter.huggingface import HuggingFaceExporter
from .__about__ import version



def export_repos(
    platform: str,
    token: str | None = None,
    org_name: str | None = None,
    spreadsheet_id: str | None = None,
    sheet_name: str | None = None,
    creds_path: str | None = None,
    repo_type: str | None = None,
) -> None:
    """
    Build the appropriate exporter for the given platform and run it.

    Parameters:
    ------------
    platform       - String. One of "github", "huggingface".
    token          - String | None. API token for the platform.
    org_name       - String | None. Org name; falls back to GH_ORG_NAME / HF_ORG_NAME env var.
    spreadsheet_id - String | None. Google Sheets spreadsheet ID; falls back to SPREADSHEET_ID env var.
    sheet_name     - String | None. Sheet tab name; falls back to platform default.
    creds_path     - String | None. Path to service_account.json; falls back to GOOGLE_CREDENTIALS_PATH env var.
    repo_type      - String | None. GitHub-only repo type filter.
    """
    platform = platform.strip().lower()
    spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
    creds_path = creds_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")

    if platform == "github":
        token = token or os.getenv("GH_TOKEN") or input("Enter your GitHub token: ").strip()
        org_name = org_name or os.getenv("GH_ORG_NAME")
        sheet_name = sheet_name or os.getenv("GH_SHEET_NAME", "GH-Repos")
        repo_type = repo_type or os.getenv("REPO_TYPE")

        _validate_required({"GH_ORG_NAME": org_name, "SPREADSHEET_ID": spreadsheet_id})

        exporter = GitHubExporter(
            token=token,
            org_name=org_name,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            creds_path=creds_path,
            repo_type=repo_type,
        )

    elif platform == "huggingface":
        token = token or os.getenv("HF_TOKEN") or input("Enter your Hugging Face token: ").strip() or None
        org_name = org_name or os.getenv("HF_ORG_NAME")
        sheet_name = sheet_name or os.getenv("HF_SHEET_NAME", "HF-Repos")

        _validate_required({"HF_ORG_NAME": org_name, "SPREADSHEET_ID": spreadsheet_id})

        exporter = HuggingFaceExporter(
            token=token,
            org_name=org_name,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            creds_path=creds_path,
        )

    else:
        raise ValueError(f"Unknown platform: {platform}")

    exporter.run()


def _validate_required(required_vars: dict) -> None:
    """
    Raise ValueError listing any missing required variables.

    Parameters:
    ------------
    required_vars - Dict mapping variable name to its current value.
    """
    missing = [name for name, value in required_vars.items() if not value]
    if missing:
        raise ValueError(
            "Missing required environment variables: "
            f"{', '.join(missing)}. Set them in your shell/.env or in the GitHub Actions workflow env."
        )

def create_parser():
    parser = argparse.ArgumentParser(description='Export GitHub or Hugging Face repository metadata to Google Sheets.')
    
    parser.add_argument('--version', action='version', version=f'repo-exporter {version}')
    
    subparsers = parser.add_subparsers(title='platform', dest='platform', required=True)

    # Github command
    gh_parser = subparsers.add_parser("github", help="Export Github repositories.")
    gh_parser.add_argument("--org", default=None, help="GitHub organization name (overrides GH_ORG_NAME).")
    gh_parser.add_argument("--token", default=None, help="GitHub API token (overrides GH_TOKEN).")
    gh_parser.add_argument("--spreadsheet-id", default=None, help="Google Sheets spreadsheet ID.")
    gh_parser.add_argument("--sheet-name", default=None, help="Sheet tab name.")
    gh_parser.add_argument("--credentials-path", default=None, help="Path to service_account.json.")
    gh_parser.add_argument("--repo-type", default=None,
    choices=["all", "public", "private", "forks", "sources", "member"], help="GitHub repository type filter.")
    
    # Hugging Face command
    hf_parser = subparsers.add_parser("huggingface", help="Export Hugging Face repositories.")
    hf_parser.add_argument("--org", default=None, help="Hugging Face organization name (overrides HF_ORG_NAME).")
    hf_parser.add_argument("--token", default=None, help="Hugging Face API token (overrides HF_TOKEN).")
    hf_parser.add_argument("--spreadsheet-id", default=None, help="Google Sheets spreadsheet ID.")
    hf_parser.add_argument("--sheet-name", default=None, help="Sheet tab name.")
    hf_parser.add_argument("--credentials-path", default=None, help="Path to service_account.json.")
    
    return parser 

def parse_args(input_args=None):
    args = create_parser().parse_args(input_args)
    return args

def main():
    args = parse_args()
    
    try:
        export_repos(
            platform=args.platform,
            token=args.token,
            org_name=args.org,
            spreadsheet_id=args.spreadsheet_id,
            sheet_name=args.sheet_name,
            creds_path=args.credentials_path,
            repo_type=getattr(args, "repo_type", None)
        )
    except ValueError as e:
        raise SystemExit(str(e))

if __name__ == "__main__":
    main()