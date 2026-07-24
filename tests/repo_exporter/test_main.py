"""
Unit tests for src/repo_exporter/__main__.py.

Covers export_repos() platform dispatch and env-var fallback logic,
_validate_required(), the argparse parser (create_parser/parse_args),
and main()'s error handling -- all with GitHubExporter/HuggingFaceExporter
mocked out so no real API/Sheets calls happen.
"""

from unittest.mock import MagicMock, patch

import pytest

from repo_exporter import __main__ as main_module


# export_repos() - platform dispatch and fallbacks

@patch.object(main_module, "GitHubExporter")
def test_export_repos_github_builds_exporter_with_explicit_args(mock_gh_cls):
    mock_exporter = MagicMock()
    mock_gh_cls.return_value = mock_exporter

    main_module.export_repos(
        platform="github",
        token="tok123",
        org_name="imageomics",
        spreadsheet_id="sheet123",
        sheet_name="GH-Repos",
        creds_path="creds.json",
        repo_type="public",
    )

    mock_gh_cls.assert_called_once_with(
        token="tok123",
        org_name="imageomics",
        spreadsheet_id="sheet123",
        sheet_name="GH-Repos",
        creds_path="creds.json",
        repo_type="public",
    )
    mock_exporter.run.assert_called_once()


def test_export_repos_github_defaults_repo_type_to_all(monkeypatch):
    monkeypatch.setattr(main_module, "GH_REPO_TYPE", None)
    with patch.object(main_module, "GitHubExporter") as mock_gh_cls:
        mock_gh_cls.return_value = MagicMock()

        main_module.export_repos(
            platform="github",
            org_name="imageomics",
            spreadsheet_id="sheet123",
        )

        _, kwargs = mock_gh_cls.call_args
        assert kwargs["repo_type"] == "all"


@patch.object(main_module, "GitHubExporter")
def test_export_repos_github_strips_whitespace_only_token_to_none(mock_gh_cls):
    mock_gh_cls.return_value = MagicMock()

    main_module.export_repos(
        platform="github",
        token="   ",
        org_name="imageomics",
        spreadsheet_id="sheet123",
    )

    _, kwargs = mock_gh_cls.call_args
    assert kwargs["token"] is None


@patch.object(main_module, "HuggingFaceExporter")
def test_export_repos_huggingface_builds_exporter_with_explicit_args(mock_hf_cls):
    mock_exporter = MagicMock()
    mock_hf_cls.return_value = mock_exporter

    main_module.export_repos(
        platform="huggingface",
        token="hf_tok",
        org_name="imageomics",
        spreadsheet_id="sheet123",
        sheet_name="HF-Repos",
        creds_path="creds.json",
    )

    mock_hf_cls.assert_called_once_with(
        token="hf_tok",
        org_name="imageomics",
        spreadsheet_id="sheet123",
        sheet_name="HF-Repos",
        creds_path="creds.json",
    )
    mock_exporter.run.assert_called_once()


def test_export_repos_platform_is_case_and_whitespace_insensitive():
    with patch.object(main_module, "GitHubExporter") as mock_gh_cls:
        mock_gh_cls.return_value = MagicMock()
        main_module.export_repos(
            platform="  GitHub  ",
            org_name="imageomics",
            spreadsheet_id="sheet123",
        )
        mock_gh_cls.assert_called_once()


def test_export_repos_unknown_platform_raises_value_error():
    with pytest.raises(ValueError, match="Unknown platform"):
        main_module.export_repos(
            platform="gitlab",
            org_name="imageomics",
            spreadsheet_id="sheet123",
        )


def test_export_repos_github_missing_org_name_raises_value_error(monkeypatch):
    monkeypatch.setattr(main_module, "GH_ORG_NAME", None)
    with pytest.raises(ValueError, match="GH_ORG_NAME"):
        main_module.export_repos(platform="github", spreadsheet_id="sheet123")


def test_export_repos_missing_spreadsheet_id_raises_value_error(monkeypatch):
    monkeypatch.setattr(main_module, "SPREADSHEET_ID", None)
    with pytest.raises(ValueError, match="SPREADSHEET_ID"):
        main_module.export_repos(platform="github", org_name="imageomics")


def test_export_repos_lists_all_missing_vars_together(monkeypatch):
    monkeypatch.setattr(main_module, "GH_ORG_NAME", None)
    monkeypatch.setattr(main_module, "SPREADSHEET_ID", None)
    with pytest.raises(ValueError) as exc_info:
        main_module.export_repos(platform="github")
    msg = str(exc_info.value)
    assert "GH_ORG_NAME" in msg
    assert "SPREADSHEET_ID" in msg



# _validate_required()

def test_validate_required_passes_when_all_present():
    # Should not raise
    main_module._validate_required({"A": "value", "B": "other"})


def test_validate_required_raises_listing_missing_names():
    with pytest.raises(ValueError) as exc_info:
        main_module._validate_required({"A": None, "B": "", "C": "present"})
    msg = str(exc_info.value)
    assert "A" in msg
    assert "B" in msg
    assert "C" not in msg


# create_parser() / parse_args()

def test_parser_requires_a_platform_subcommand():
    parser = main_module.create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_github_defaults():
    args = main_module.parse_args(["github"])
    assert args.platform == "github"
    assert args.org is None
    assert args.token is None
    assert args.repo_type is None
    assert args.spreadsheet_id is None
    assert args.sheet_name is None
    assert args.credentials_path is None


def test_parser_github_accepts_all_flags():
    args = main_module.parse_args([
        "github",
        "--org", "imageomics",
        "--token", "tok123",
        "--repo-type", "public",
        "--spreadsheet-id", "sheet123",
        "--sheet-name", "GH-Repos",
        "--credentials-path", "creds.json",
    ])
    assert args.org == "imageomics"
    assert args.token == "tok123"
    assert args.repo_type == "public"
    assert args.spreadsheet_id == "sheet123"
    assert args.sheet_name == "GH-Repos"
    assert args.credentials_path == "creds.json"


def test_parser_huggingface_defaults():
    args = main_module.parse_args(["huggingface"])
    assert args.platform == "huggingface"
    assert args.org is None
    assert args.token is None
    assert not hasattr(args, "repo_type")  # HF subparser has no --repo-type


def test_parser_huggingface_accepts_all_flags():
    args = main_module.parse_args([
        "huggingface",
        "--org", "imageomics",
        "--token", "hf_tok",
        "--spreadsheet-id", "sheet123",
        "--sheet-name", "HF-Repos",
        "--credentials-path", "creds.json",
    ])
    assert args.org == "imageomics"
    assert args.token == "hf_tok"
    assert args.spreadsheet_id == "sheet123"
    assert args.sheet_name == "HF-Repos"
    assert args.credentials_path == "creds.json"


def test_parser_rejects_unknown_platform():
    parser = main_module.create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["gitlab"])


def test_parser_version_flag_exits_cleanly(capsys):
    parser = main_module.create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0


# main()

@patch.object(main_module, "export_repos")
def test_main_calls_export_repos_with_parsed_args(mock_export_repos, monkeypatch):
    fake_args = main_module.create_parser().parse_args([
        "github", "--org", "imageomics", "--spreadsheet-id", "sheet123",
    ])
    monkeypatch.setattr(main_module, "parse_args", lambda: fake_args)

    main_module.main()

    mock_export_repos.assert_called_once()
    _, kwargs = mock_export_repos.call_args
    assert kwargs["platform"] == "github"
    assert kwargs["org_name"] == "imageomics"
    assert kwargs["spreadsheet_id"] == "sheet123"


@patch.object(main_module, "export_repos")
def test_main_raises_systemexit_on_value_error(mock_export_repos, monkeypatch):
    mock_export_repos.side_effect = ValueError("missing stuff")
    fake_args = main_module.create_parser().parse_args(["github"])
    monkeypatch.setattr(main_module, "parse_args", lambda: fake_args)

    with pytest.raises(SystemExit, match="missing stuff"):
        main_module.main()


@patch.object(main_module, "export_repos")
def test_main_huggingface_repo_type_is_none_not_missing_attr(mock_export_repos, monkeypatch):
    """huggingface subparser has no --repo-type; main() uses getattr(..., None)
    so it shouldn't raise AttributeError."""
    fake_args = main_module.create_parser().parse_args([
        "huggingface", "--org", "imageomics", "--spreadsheet-id", "sheet123",
    ])
    monkeypatch.setattr(main_module, "parse_args", lambda: fake_args)

    main_module.main()

    _, kwargs = mock_export_repos.call_args
    assert kwargs["repo_type"] is None