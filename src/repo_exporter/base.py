from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import os
import re
import time

import pandas as pd
from tqdm import tqdm
from google.oauth2.service_account import Credentials
import gspread


class BaseExporter(ABC):
    """
    Base class for platform-specific repo exporters.
    Subclasses must implement get_repo_info() and update_google_sheet(),
    and should set self.org_name, self.spreadsheet_id, self.sheet_name,
    self.creds_path in their __init__.
    """

    def __init__(self):
        self.org_name = None
        self.spreadsheet_id = None
        self.sheet_name = None
        self.creds_path = None

    # Shared utilities

    @staticmethod
    def is_inactive(dt: datetime | None) -> str:
        """
        Return "Yes" if dt is more than one year ago, "No" if recent, "N/A" if missing.

        Parameters:
        ------------
        dt - datetime | None. Timezone-aware or naive datetime of last activity.
        """
        try:
            if dt is None:
                return "N/A"
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
            return "Yes" if dt < one_year_ago else "No"
        except Exception:
            return "N/A"

    @staticmethod
    def extract_display_name(val: str) -> str:
        """
        Extract the repo name from a HYPERLINK formula.
        e.g. '=HYPERLINK("https://...", "my-repo")' -> 'my-repo'

        Parameters:
        ------------
        val - String. Cell value, either a HYPERLINK formula or a plain string.
        """
        match = re.search(r'"([^"]+)"\)$', val)
        return match.group(1) if match else val

    @staticmethod
    def ensure_string_value(value) -> str:
        """
        Convert any value to a string safe for writing to Google Sheets.

        Parameters:
        ------------
        value - Any. The cell value to convert.
        """
        if value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        if isinstance(value, dict):
            return str(value)
        return str(value)

    # Abstract methods — subclasses must implement
  
    @abstractmethod
    def fetch_repos(self) -> list:
        """
        Fetch all repos for the org from the platform API.
        Returns a list of (repo, repo_type) tuples or equivalent.
        """
        ...

    @abstractmethod
    def get_repo_info(self, repo, *args, **kwargs) -> dict[str, str | int]:
        """
        Return a dict of metadata for a single repo.
        Keys must match the column headers in the target Google Sheet.
        """
        ...

    @abstractmethod
    def update_google_sheet(self, df: pd.DataFrame) -> None:
        """
        Write df to the platform-specific Google Sheet tab.
        Each subclass defines its own column set and color config.
        """
        ...

    # Shared Google Sheets helpers for subclasses

    def _get_sheet(self):
        """
        Authenticate and return the gspread worksheet.
        """
        creds = Credentials.from_service_account_file(
            self.creds_path,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        client = gspread.authorize(creds)
        return client.open_by_key(self.spreadsheet_id).worksheet(self.sheet_name)

    def _build_batch_body(self, sheet, df: pd.DataFrame, header: list) -> tuple[list, list]:
        """
        Build the batch update body for writing df to the sheet.
        Returns (batch_body, existing) so subclasses can pass to _write_batch.

        Parameters:
        ------------
        sheet  - gspread Worksheet object.
        df     - pd.DataFrame. Data to write.
        header - List of column header strings already fetched from the sheet.
        """
        HEADER_ROW_INDEX = 2

        try:
            repo_col_index = header.index("Repository Name")
        except ValueError:
            raise ValueError('Sheet is missing "Repository Name" column')

        existing = sheet.get_all_values()
        data_rows = existing[HEADER_ROW_INDEX:]

        name_to_row = {}
        for offset, row in enumerate(data_rows, start=HEADER_ROW_INDEX + 1):
            if len(row) <= repo_col_index:
                continue
            sheet_repo_name = self.extract_display_name(row[repo_col_index])
            name_to_row[sheet_repo_name] = offset

        batch_body = []
        for _, row in df.iterrows():
            repo_name = self.extract_display_name(row["Repository Name"])

            if repo_name in name_to_row:
                row_idx = name_to_row[repo_name]
            else:
                row_idx = len(existing) + 1
                existing.append([""] * len(header))

            for col_idx, col_name in enumerate(header, start=1):
                if col_name not in df.columns:
                    continue
                value = self.ensure_string_value(row.get(col_name, ""))
                cell = f"'{sheet.title}'!{gspread.utils.rowcol_to_a1(row_idx, col_idx)}"
                batch_body.append({
                    "range": cell,
                    "majorDimension": "ROWS",
                    "values": [[value]],
                })

        return batch_body, existing

    def _write_batch(self, sheet, batch_body: list) -> None:
        """
        Execute a batch value update on the sheet.

        Parameters:
        ------------
        sheet      - gspread Worksheet object.
        batch_body - List of range/value dicts from _build_batch_body.
        """
        sheet.spreadsheet.values_batch_update(
            body={
                "value_input_option": "USER_ENTERED",
                "data": batch_body,
            }
        )

    def _apply_conditional_formatting(
        self,
        sheet,
        header: list,
        df: pd.DataFrame,
        red_columns: set,
        secondary_columns: set,
        secondary_color: dict,
    ) -> None:
        """
        Apply "No" conditional formatting rules to specified columns.

        Parameters:
        ------------
        sheet            - gspread Worksheet object.
        header           - List of column header strings from the sheet.
        df               - pd.DataFrame. Used to determine row count.
        red_columns      - Set of column names to highlight red when "No".
        secondary_columns - Set of column names to highlight with secondary_color when "No".
        secondary_color  - Dict with keys "red", "green", "blue" (0–1 floats).
        """
        HEADER_ROW_INDEX = 2

        def get_column_index(col_name: str):
            try:
                return header.index(col_name)
            except ValueError:
                return None

        rules = []
        for col_set, color in [
            (red_columns, {"red": 1, "green": 0.5, "blue": 0.5}),
            (secondary_columns, secondary_color),
        ]:
            for col_name in col_set:
                col_index = get_column_index(col_name)
                if col_index is None:
                    continue
                rules.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet.id,
                                "startRowIndex": HEADER_ROW_INDEX,
                                "endRowIndex": HEADER_ROW_INDEX + len(df),
                                "startColumnIndex": col_index,
                                "endColumnIndex": col_index + 1,
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "No"}],
                                },
                                "format": {"backgroundColor": color},
                            },
                        },
                        "index": 0,
                    }
                })

        sheet.spreadsheet.batch_update({"requests": rules})

    # Shared run() orchestration

    def run(self) -> None:
        """
        Main orchestration: fetch repos, collect metadata, write to sheet.
        Subclasses set self.org_name, self.spreadsheet_id, self.sheet_name,
        self.creds_path before calling run().
        """
        start_time = time.time()

        print(f"\nFetching repositories for: {self.org_name}")
        print("\n----------------")

        try:
            repos = self.fetch_repos()
        except Exception as e:
            print(f'ERROR: Could not fetch repos for "{self.org_name}": {e}')
            return

        data = []
        tqdm_kwargs = {}
        if os.environ.get("CI") == "true":
            tqdm_kwargs = {"mininterval": 1, "dynamic_ncols": False, "leave": False}

        for repo_args in tqdm(
            repos,
            desc=f"Fetching repos from {self.org_name}...",
            unit="repo",
            colour="green",
            ncols=100,
            **tqdm_kwargs,
        ):
            try:
                # repo_args is either a single repo or a tuple — subclass handles it
                info = self._fetch_one(repo_args)
                data.append(info)
                tqdm.write(f"Fetched info for {self._repo_label(repo_args)}")
            except Exception as e:
                tqdm.write(
                    f"ERROR: Cannot fetch {self._repo_label(repo_args)} info, "
                    f"due to {type(e).__name__}: {e}. Skipping..."
                )

        if not data:
            print("ERROR: No data collected")
            return

        print("----------------\n")

        df = pd.DataFrame(data)
        df.sort_values(by="Repository Name", inplace=True)

        self.update_google_sheet(df)
        print(f"Finished fetching info for {len(df)} repositories from {self.org_name}")

        elapsed = time.time() - start_time
        minutes, seconds = divmod(int(elapsed), 60)
        print(f"Total time taken: {minutes}m {seconds}s")

    def _fetch_one(self, repo_args) -> dict:
        """
        Unpack repo_args and call get_repo_info.
        Subclasses can override if they need to pass extra args.

        Parameters:
        ------------
        repo_args - A single repo object or a tuple of args for get_repo_info.
        """
        if isinstance(repo_args, tuple):
            return self.get_repo_info(*repo_args)
        return self.get_repo_info(repo_args)

    def _repo_label(self, repo_args) -> str:
        """
        Return a display label for a repo for tqdm.write messages.

        Parameters:
        ------------
        repo_args - A single repo object or a tuple whose first element is the repo.
        """
        repo = repo_args[0] if isinstance(repo_args, tuple) else repo_args
        return f"/{getattr(repo, 'name', getattr(repo, 'id', str(repo)))}"