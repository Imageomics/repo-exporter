import argparse
import os

from dotenv import load_dotenv
load_dotenv()

from repo_exporter.github import GitHubExporter
from repo_exporter.huggingface import HuggingFaceExporter
from .__about__ import __version__ as version

GH_ORG_NAME = os.getenv("GH_ORG_NAME")
GH_TOKEN = os.getenv("GH_TOKEN")
GH_SHEET_NAME = os.getenv("GH_SHEET_NAME", "GH-Repos")
GH_REPO_TYPE = os.getenv("GH_REPO_TYPE")
HF_ORG_NAME = os.getenv("HF_ORG_NAME")
HF_TOKEN = os.getenv("HF_TOKEN")
HF_SHEET_NAME = os.getenv("HF_SHEET_NAME", "HF-Repos")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account.json")


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
    repo_type      - String | None. GitHub-only repo type filter; falls back to GH_REPO_TYPE env var.
    """
    platform = platform.strip().lower()
    spreadsheet_id = spreadsheet_id or SPREADSHEET_ID
    creds_path = creds_path or GOOGLE_CREDENTIALS_PATH

    if platform == "github":
    
        token = (token or GH_TOKEN or "").strip() or None
        org_name = org_name or GH_ORG_NAME
        sheet_name = sheet_name or GH_SHEET_NAME
        repo_type = repo_type or GH_REPO_TYPE or "all"
        
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
        token = (token or HF_TOKEN or "").strip() or None
        org_name = org_name or HF_ORG_NAME
        sheet_name = sheet_name or HF_SHEET_NAME

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

    # Shared args
    spreadsheet_arg = {'help': 'Google Sheets spreadsheet ID (overrides SPREADSHEET_ID in .env)'}
    credentials_arg = {'help': f"Path to service_account.json (overrides GOOGLE_CREDENTIALS_PATH in .env; default: {GOOGLE_CREDENTIALS_PATH})"}

    # GitHub command
    gh_parser = subparsers.add_parser("github", help="Export GitHub repositories.")
    gh_parser.add_argument("--org", default=None, help="GitHub org name (overrides GH_ORG_NAME in .env)")
    gh_parser.add_argument("--token", default=None, help="GitHub personal access token (overrides GH_TOKEN in .env)")
    gh_parser.add_argument(
        "--repo-type",
        default=None,
        help=f"Repo type filter: all, public, private, forks, sources, member "
             f"(overrides GH_REPO_TYPE in .env; default: {GH_REPO_TYPE})"
    ) 
    gh_parser.add_argument("--spreadsheet-id", **spreadsheet_arg)
    gh_parser.add_argument("--sheet-name", default=None, help=f"Sheet tab name (overrides GH_SHEET_NAME in .env; default: {GH_SHEET_NAME})")
    gh_parser.add_argument("--credentials-path", **credentials_arg)

    # Hugging Face command
    hf_parser = subparsers.add_parser("huggingface", help="Export Hugging Face repositories.")
    hf_parser.add_argument("--org", default=None, help="Hugging Face org name (overrides HF_ORG_NAME in .env)")
    hf_parser.add_argument("--token", default=None, help="Hugging Face token (overrides HF_TOKEN in .env)")
    hf_parser.add_argument("--spreadsheet-id", **spreadsheet_arg)
    hf_parser.add_argument("--sheet-name", default=None, help=f"Sheet tab name (overrides HF_SHEET_NAME in .env; default: {HF_SHEET_NAME})")
    hf_parser.add_argument("--credentials-path", **credentials_arg)

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