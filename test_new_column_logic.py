import pandas as pd
from unittest.mock import MagicMock, patch, call
 
from gh_repo_exporter import update_google_sheet
 
 
def _make_mock_sheet(fake_header, fake_data_rows):
    mock_sheet = MagicMock()
    mock_sheet.title = "GH-Repos"
    mock_sheet.id = 0
    mock_sheet.row_values.return_value = fake_header
    mock_sheet.get_all_values.return_value = [[], fake_header] + fake_data_rows
 
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_sheet
    mock_sheet.spreadsheet = mock_spreadsheet
 
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet
 
    return mock_sheet, mock_spreadsheet, mock_client
 
 
def _run(df, mock_client):
    with patch("gh_repo_exporter.gspread.authorize", return_value=mock_client), \
         patch("gh_repo_exporter.Credentials.from_service_account_file", return_value=MagicMock()):
        update_google_sheet(df, "fake_spreadsheet_id", "GH-Repos", "fake_creds.json")
 
 
def test_new_column_is_appended():
    """Existing behavior: a DataFrame column not in the sheet header gets appended."""
    fake_header = ["Repository Name", "Stars", "README"]
    fake_data_rows = [["=HYPERLINK(\"url\", \"cool-project\")", "10", "Yes"]]
    mock_sheet, mock_spreadsheet, mock_client = _make_mock_sheet(fake_header, fake_data_rows)
 
    df = pd.DataFrame([{
        "Repository Name": '=HYPERLINK("url", "cool-project")',
        "Stars": 10,
        "README": "Yes",
        "TEST_COLUMN": "test123",
    }])
 
    _run(df, mock_client)
 
    assert mock_sheet.update.call_args == call(range_name="D2", values=[["TEST_COLUMN"]])
    print("PASS: test_new_column_is_appended")
 
 
def test_renamed_column_creates_duplicate_not_inplace_update():
    """Documents current behavior: renaming a column (e.g. 'Language' -> 'Primary Language')
    does NOT update the existing 'Language' header in place. Instead the new name is treated
    as a brand-new column and appended, leaving the old header untouched.
    """
    fake_header = ["Repository Name", "Language"]
    fake_data_rows = [["=HYPERLINK(\"url\", \"cool-project\")", "Python"]]
    mock_sheet, mock_spreadsheet, mock_client = _make_mock_sheet(fake_header, fake_data_rows)
 
    df = pd.DataFrame([{
        "Repository Name": '=HYPERLINK("url", "cool-project")',
        "Primary Language": "Python",
    }])
 
    _run(df, mock_client)
 
    # "Primary Language" gets appended as a new column at index 3 (C2), NOT written into
    # the existing "Language" column at index 2 (B2).
    assert mock_sheet.update.call_args == call(range_name="C2", values=[["Primary Language"]])
    print("PASS: test_renamed_column_creates_duplicate_not_inplace_update (documents current behavior)")
 
 
def test_no_new_columns_skips_header_update():
    """When every DataFrame column already exists in the sheet header, sheet.update()
    (the header-writing call) should never be called."""
    fake_header = ["Repository Name", "Stars", "README"]
    fake_data_rows = [["=HYPERLINK(\"url\", \"cool-project\")", "10", "Yes"]]
    mock_sheet, mock_spreadsheet, mock_client = _make_mock_sheet(fake_header, fake_data_rows)
 
    df = pd.DataFrame([{
        "Repository Name": '=HYPERLINK("url", "cool-project")',
        "Stars": 20,
        "README": "No",
    }])
 
    _run(df, mock_client)
 
    mock_sheet.update.assert_not_called()
    print("PASS: test_no_new_columns_skips_header_update")
 
 
def test_multiple_new_columns_appended_together():
    """Two new columns at once should be appended starting at the correct index,
    in the same order they appear in df.columns."""
    fake_header = ["Repository Name", "Stars"]
    fake_data_rows = [["=HYPERLINK(\"url\", \"cool-project\")", "10"]]
    mock_sheet, mock_spreadsheet, mock_client = _make_mock_sheet(fake_header, fake_data_rows)
 
    df = pd.DataFrame([{
        "Repository Name": '=HYPERLINK("url", "cool-project")',
        "Stars": 10,
        "Model": "No",
        "Dataset": "No",
    }])
 
    _run(df, mock_client)
 
    assert mock_sheet.update.call_args == call(range_name="C2", values=[["Model", "Dataset"]])
    print("PASS: test_multiple_new_columns_appended_together")
 
 
if __name__ == "__main__":
    test_new_column_is_appended()
    test_renamed_column_creates_duplicate_not_inplace_update()
    test_no_new_columns_skips_header_update()
    test_multiple_new_columns_appended_together()