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
    Subclasses must implement fetch_repos() and get_repo_info(),
    and should set self.org_name, self.spreadsheet_id, self.sheet_name,
    self.creds_path in their __init__.
    """

    def __init__(self, org_name: str, spreadsheet_id: str, sheet_name: str, creds_path: str):
        self.org_name = org_name
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.creds_path = creds_path
        
    @staticmethod
    def is_inactive(dt: datetime | None) -> str:
        """
        Return "Yes" if dt is more than one year ago, "No" if recent, "N/A" if missing.

        Parameters:
        ------------
        dt - datetime | None. Timezone-aware or naive datetime of last activity.
        """
        
        if dt is None:
            return "N/A"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
        return "Yes" if dt < one_year_ago else "No"
        
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
            s = ", ".join(str(v) for v in value)
        else:
            s = str(value)

        # Prevent formula injection when using value_input_option="USER_ENTERED".
        if s.startswith("=") and not s.upper().startswith('=HYPERLINK('):
            s = "'" + s

        return s
  
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
    
    @property
    @abstractmethod
    def red_columns(self) -> set[str]:
        """Columns to color red when value is 'No'."""
        pass
    
    @property
    @abstractmethod
    def secondary_columns(self) -> set[str]:
        """Columns to color with the secondary color when value is 'No'."""
        pass
    
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
    
    def _sync_new_columns(self, sheet, df: pd.DataFrame, header: list) -> list:
        """
        Add any DataFrame columns missing from the sheet header as new columns,
        expanding the sheet if needed. Returns the updated header list.

        Parameters:
        ------------
        sheet  - gspread Worksheet object.
        df     - pd.DataFrame. Data to write.
        header - List of column header strings already fetched from the sheet.
        """
        HEADER_ROW_INDEX = 2

        new_columns = [col for col in df.columns if col not in header]
        if not new_columns:
            return header

        required_cols = len(header) + len(new_columns)
        if required_cols > sheet.col_count:
            sheet.add_cols(required_cols - sheet.col_count)

        start_col = len(header) + 1  # next empty column, 1-indexed
        end_col = required_cols
        header_range = (
            f"{gspread.utils.rowcol_to_a1(HEADER_ROW_INDEX, start_col)}:"
            f"{gspread.utils.rowcol_to_a1(HEADER_ROW_INDEX, end_col)}"
        )
        sheet.update(range_name=header_range, values=[new_columns])

        return header + new_columns
    
    def get_column_index(self, header:list[str], col_name: str) -> int | None:
        try:
            return header.index(col_name)
        except ValueError:
            return None
        
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
    
    @staticmethod
    def _normalize_color(color: dict) -> dict:
        """
        Fill in missing red/green/blue keys as 0, so colors from the API
        (which can omit zero-valued channels) compare equal to literal
        color dicts that always include all three keys.

        Parameters:
        ------------
        color - Dict with zero or more of "red", "green", "blue" keys (0-1 floats).
        """
        return {
            "red": color.get("red", 0),
            "green": color.get("green", 0),
            "blue": color.get("blue", 0),
        }
        
    @staticmethod
    def _build_conditional_rule(sheet_id: int, col_index: int, end_row: int, color: dict) -> dict:
        """
        Build a "No" conditional format rule dict for a single column.

        Parameters:
        ------------
        sheet_id  - Integer. Google Sheets sheetId.
        col_index - Integer. 0-indexed column the rule applies to.
        end_row   - Integer. Exclusive end row index for the rule's range.
        color     - Dict with "red", "green", "blue" keys (0-1 floats).
        """
        HEADER_ROW_INDEX = 2
        return {
            "ranges": [{
                "sheetId": sheet_id,
                "startRowIndex": HEADER_ROW_INDEX,
                "endRowIndex": end_row,
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
        }
        
    @staticmethod
    def _is_managed_rule(rule: dict) -> bool:
        """
        Return True only for conditional format rules that match the
        exporter's own signature (TEXT_EQ == "No", starting at the header
        row). Rules that don't match -- e.g. manually added in the Sheets UI,
        or using a different condition -- are left untouched by the diff.

        Parameters:
        ------------
        rule - Dict. A single conditionalFormats entry from fetch_sheet_metadata().
        """
        HEADER_ROW_INDEX = 2

        ranges = rule.get("ranges", [{}])
        if not ranges:
            return False
        if ranges[0].get("startRowIndex") != HEADER_ROW_INDEX:
            return False

        condition = rule.get("booleanRule", {}).get("condition", {})
        if condition.get("type") != "TEXT_EQ":
            return False

        values = condition.get("values", [])
        if not values or values[0].get("userEnteredValue") != "No":
            return False

        return True
          
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
        Sync "No" conditional formatting rules to specified columns, diffing
        against the sheet's existing rules instead of always appending new
        ones, so repeated runs don't accumulate duplicate rules.

        Parameters:
        ------------
        sheet            - gspread Worksheet object.
        header           - List of column header strings from the sheet.
        df               - pd.DataFrame. Used to determine row count.
        red_columns      - Set of column names to highlight red when "No".
        secondary_columns - Set of column names to highlight with secondary_color when "No".
        secondary_color  - Dict with keys "red", "green", "blue" (0-1 floats).
        """
        HEADER_ROW_INDEX = 2
        sheet_id = sheet.id
        end_row = HEADER_ROW_INDEX + len(df)

        desired = {}  # col_index -> color
        for col_set, color in [
            (red_columns, {"red": 1, "green": 0.5, "blue": 0.5}),
            (secondary_columns, secondary_color),
        ]:
            for col_name in col_set:
                col_index = self.get_column_index(header, col_name)
                if col_index is not None:
                    desired[col_index] = color

        existing_rules = {}  # col_index -> (rule_index, rule_dict)
        metadata = sheet.spreadsheet.fetch_sheet_metadata()
        for sheet_meta in metadata.get("sheets", []):
            if sheet_meta["properties"]["sheetId"] != sheet_id:
                continue
            for i, rule in enumerate(sheet_meta.get("conditionalFormats", [])):
                if not self._is_managed_rule(rule):
                    continue
                ranges = rule.get("ranges", [{}])
                existing_rules[ranges[0].get("startColumnIndex")] = (i, rule)
            break

        requests = []

        # 1. Updates first; index safe since nothing has shifted yet.
        for col_index, color in desired.items():
            if col_index not in existing_rules:
                continue
            rule_index, existing_rule = existing_rules[col_index]
            existing_range = existing_rule.get("ranges", [{}])[0]
            existing_color = (
                existing_rule.get("booleanRule", {}).get("format", {}).get("backgroundColor", {})
            )
            if existing_range.get("endRowIndex") != end_row or self._normalize_color(existing_color) != self._normalize_color(color):
                requests.append({
                    "updateConditionalFormatRule": {
                        "index": rule_index,
                        "sheetId": sheet_id,
                        "rule": self._build_conditional_rule(sheet_id, col_index, end_row, color),
                    }
                })

        # 2. Deletes next, highest index first; deleting descending never
        # shifts the index of a rule we still need to delete
        stale_indices = sorted(
            (rule_index for col_index, (rule_index, _) in existing_rules.items() if col_index not in desired),
            reverse=True,
        )
        for rule_index in stale_indices:
            requests.append({"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": rule_index}})

        # 3. Adds last, always at index 0. Order doesn't matter once nothing
        #    else references an existing index.
        for col_index, color in desired.items():
            if col_index not in existing_rules:
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": self._build_conditional_rule(sheet_id, col_index, end_row, color),
                        "index": 0,
                    }
                })

        if not requests:
            return

        sheet.spreadsheet.batch_update({"requests": requests})
        
    def update_google_sheet(self, df: pd.DataFrame) -> None:
        """
        Write df to the configured Google sheet tab using subclass column/color config.

        Parameters:
        ------------
        df - pd.DataFrame. Data to write, with columns matching sheet headers.
        """
        sheet = self._get_sheet()
        header = sheet.row_values(2)
        header = self._sync_new_columns(sheet, df, header)
        batch_body, _ = self._build_batch_body(sheet, df, header)
        self._write_batch(sheet, batch_body)
        
        self._apply_conditional_formatting(
            sheet,
            header,
            df,
            red_columns=self.red_columns,
            secondary_columns=self.secondary_columns,
            secondary_color={"red": 1, "green": 0.8, "blue": 0.4},
        )

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