"""
Unit tests for BaseExporter shared logic (base.py).

Static helpers are tested directly on the class. Non-abstract instance
methods (_build_batch_body, _apply_conditional_formatting, run) can't be
exercised on BaseExporter itself since it's an ABC, so GitHubExporter is
used as the concrete test vehicle for those -- only base.py behavior is
under test here, not GitHubExporter-specific logic (that's in test_github.py).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from repo_exporter.base import BaseExporter
from repo_exporter.github import GitHubExporter


def make_exporter() -> GitHubExporter:
    return GitHubExporter(
        org_name="imageomics",
        spreadsheet_id="sheet123",
        sheet_name="GH-Repos",
        creds_path="fake.json",
        token=None,
    )

# is_inactive

def test_is_inactive_true_for_old_aware_datetime():
    old = datetime.now(timezone.utc) - timedelta(days=400)
    assert BaseExporter.is_inactive(old) == "Yes"

def test_is_inactive_false_for_recent_aware_datetime():
    recent = datetime.now(timezone.utc) - timedelta(days=10)
    assert BaseExporter.is_inactive(recent) == "No"

def test_is_inactive_handles_naive_datetime():
    naive_old = datetime.now() - timedelta(days=400)
    assert BaseExporter.is_inactive(naive_old) == "Yes"

def test_is_inactive_none_returns_na():
    assert BaseExporter.is_inactive(None) == "N/A"

def test_is_inactive_boundary_exactly_one_year_is_inactive():
    # "< one_year_ago" means exactly 365 days ago should already read as inactive
    # once fractional seconds from test execution are taken into account.
    exactly_one_year_ago = datetime.now(timezone.utc) - timedelta(days=365, seconds=1)
    assert BaseExporter.is_inactive(exactly_one_year_ago) == "Yes"


# extract_display_name

def test_extract_display_name_from_hyperlink_formula():
    val = '=HYPERLINK("https://github.com/Imageomics/my-repo", "my-repo")'
    assert BaseExporter.extract_display_name(val) == "my-repo"

def test_extract_display_name_plain_string_passthrough():
    assert BaseExporter.extract_display_name("just-a-name") == "just-a-name"

def test_extract_display_name_hf_style_hyperlink():
    val = '=HYPERLINK("https://huggingface.co/datasets/imageomics/cool", "datasets/imageomics/cool")'
    assert BaseExporter.extract_display_name(val) == "datasets/imageomics/cool"

# ensure_string_value

def test_ensure_string_value_none_returns_empty_string():
    assert BaseExporter.ensure_string_value(None) == ""

def test_ensure_string_value_list_joins_with_comma():
    assert BaseExporter.ensure_string_value(["a", "b", "c"]) == "a, b, c"

def test_ensure_string_value_dict_stringifies():
    assert BaseExporter.ensure_string_value({"a": 1}) == "{'a': 1}"

def test_ensure_string_value_passes_through_ints_and_strings():
    assert BaseExporter.ensure_string_value(5) == "5"
    assert BaseExporter.ensure_string_value("hello") == "hello"


# get_column_index

def test_get_column_index_found_and_missing():
    exporter = make_exporter()
    header = ["Repository Name", "Stars", "License"]
    assert exporter.get_column_index(header, "Stars") == 1
    assert exporter.get_column_index(header, "Nonexistent") is None


# _build_batch_body

def test_build_batch_body_updates_existing_row():
    exporter = make_exporter()
    sheet = MagicMock()
    sheet.title = "GH-Repos"
    # Row 0 = title row, row 1 = header row -> data starts at index 2 (HEADER_ROW_INDEX)
    sheet.get_all_values.return_value = [
        ["Imageomics GH Repos"],
        ["Repository Name", "Stars"],
        ['=HYPERLINK("u", "existing-repo")', "3"],
    ]
    header = ["Repository Name", "Stars"]
    df = pd.DataFrame([
        {"Repository Name": '=HYPERLINK("u", "existing-repo")', "Stars": 8},
    ])

    batch_body, existing = exporter._build_batch_body(sheet, df, header)

     # one update per column
    assert len(batch_body) == 2 
    # no new row appended
    assert len(existing) == 3  
    ranges = [item["range"] for item in batch_body]
    # Stars column, row 3 (1-indexed)
    assert any("B3" in r for r in ranges)  


def test_build_batch_body_appends_new_row_for_unseen_repo():
    exporter = make_exporter()
    sheet = MagicMock()
    sheet.title = "GH-Repos"
    sheet.get_all_values.return_value = [
        ["Imageomics GH Repos"],
        ["Repository Name", "Stars"],
    ]
    header = ["Repository Name", "Stars"]
    df = pd.DataFrame([
        {"Repository Name": '=HYPERLINK("u", "new-repo")', "Stars": 5},
    ])

    batch_body, existing = exporter._build_batch_body(sheet, df, header)

    assert len(batch_body) == 2
     # blank row appended for the new repo
    assert len(existing) == 3 


def test_build_batch_body_raises_when_repository_name_column_missing():
    exporter = make_exporter()
    sheet = MagicMock()
    sheet.title = "GH-Repos"
    sheet.get_all_values.return_value = [["title"], ["Stars"]]
    header = ["Stars"]
    df = pd.DataFrame([{"Stars": 5}])

    with pytest.raises(ValueError, match="Repository Name"):
        exporter._build_batch_body(sheet, df, header)

def test_build_batch_body_skips_columns_not_in_df():
    exporter = make_exporter()
    sheet = MagicMock()
    sheet.title = "GH-Repos"
    sheet.get_all_values.return_value = [["title"], ["Repository Name", "Stars", "License"]]
    header = ["Repository Name", "Stars", "License"]
    df = pd.DataFrame([{"Repository Name": '=HYPERLINK("u", "r")', "Stars": 5}])

    batch_body, _ = exporter._build_batch_body(sheet, df, header)

    # Only Repository Name + Stars should produce cells, not License (absent from df)
    assert len(batch_body) == 2
    

# _write_batch

def test_write_batch_calls_values_batch_update():
    exporter = make_exporter()
    sheet = MagicMock()
    batch_body = [{"range": "A1", "majorDimension": "ROWS", "values": [["x"]]}]

    exporter._write_batch(sheet, batch_body)

    sheet.spreadsheet.values_batch_update.assert_called_once_with(
        body={"value_input_option": "USER_ENTERED", "data": batch_body}
    )


# _apply_conditional_formatting

def test_apply_conditional_formatting_builds_rules_for_known_columns():
    exporter = make_exporter()
    sheet = MagicMock()
    sheet.id = 42
    header = ["Repository Name", "README", "License", "DOI for GitHub Repo"]
    df = pd.DataFrame([{"Repository Name": "r", "README": "No"}])

    exporter._apply_conditional_formatting(
        sheet,
        header,
        df,
        red_columns={"README", "License"},
        secondary_columns={"DOI for GitHub Repo"},
        secondary_color={"red": 1, "green": 0.8, "blue": 0.4},
    )

    sheet.spreadsheet.batch_update.assert_called_once()
    requests = sheet.spreadsheet.batch_update.call_args[0][0]["requests"]
    assert len(requests) == 3  # README, License, DOI

def test_apply_conditional_formatting_skips_missing_columns():
    exporter = make_exporter()
    sheet = MagicMock()
    sheet.id = 42
    header = ["Repository Name"]
    df = pd.DataFrame([{"Repository Name": "r"}])

    exporter._apply_conditional_formatting(
        sheet, header, df,
        red_columns={"Nonexistent"},
        secondary_columns=set(),
        secondary_color={"red": 1, "green": 0.8, "blue": 0.4},
    )

    sheet.spreadsheet.batch_update.assert_not_called()


# run() orchestration

def test_run_writes_sorted_dataframe_and_reports_success(capsys):
    exporter = make_exporter()
    exporter.fetch_repos = MagicMock(return_value=["repo-b", "repo-a"])
    exporter.get_repo_info = MagicMock(side_effect=[
        {"Repository Name": "zzz-repo"},
        {"Repository Name": "aaa-repo"},
    ])
    exporter.update_google_sheet = MagicMock()

    exporter.run()

    exporter.update_google_sheet.assert_called_once()
    written_df = exporter.update_google_sheet.call_args[0][0]
    assert list(written_df["Repository Name"]) == ["aaa-repo", "zzz-repo"]

    out = capsys.readouterr().out
    assert "Finished fetching info for 2 repositories" in out


def test_run_skips_repo_that_raises_and_continues(capsys):
    exporter = make_exporter()
    exporter.fetch_repos = MagicMock(return_value=["repo-a", "repo-b"])

    def fake_get_repo_info(repo):
        if repo == "repo-b":
            raise RuntimeError("boom")
        return {"Repository Name": "repo-a"}

    exporter.get_repo_info = fake_get_repo_info
    exporter.update_google_sheet = MagicMock()

    exporter.run()

    exporter.update_google_sheet.assert_called_once()
    written_df = exporter.update_google_sheet.call_args[0][0]
    assert len(written_df) == 1
    out = capsys.readouterr().out
    assert "ERROR: Cannot fetch" in out


def test_run_reports_error_and_returns_when_fetch_repos_fails(capsys):
    exporter = make_exporter()
    exporter.fetch_repos = MagicMock(side_effect=RuntimeError("no access"))
    exporter.update_google_sheet = MagicMock()

    exporter.run()

    exporter.update_google_sheet.assert_not_called()
    out = capsys.readouterr().out
    assert "ERROR: Could not fetch repos" in out


def test_run_reports_error_when_no_data_collected(capsys):
    exporter = make_exporter()
    exporter.fetch_repos = MagicMock(return_value=["repo-a"])
    exporter.get_repo_info = MagicMock(side_effect=RuntimeError("boom"))
    exporter.update_google_sheet = MagicMock()

    exporter.run()

    exporter.update_google_sheet.assert_not_called()
    out = capsys.readouterr().out
    assert "ERROR: No data collected" in out