from dotenv import load_dotenv
load_dotenv()
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from repo_exporter.github import GitHubExporter

exporter = GitHubExporter(
    org_name="Imageomics",  # swap for whichever org you want to test against
    spreadsheet_id="unused",
    sheet_name="unused",
    creds_path="unused",
    token=os.environ["GH_TOKEN"],
    repo_type="all",
)

import pandas as pd

CONTRIB_COL = "Top 4 Contributors (lines of code changes)"
org_repos = list(exporter.gh.get_organization("Imageomics").get_repos(type="all"))
exporter.existing_df = pd.DataFrame(
    [{"Repository Name": r.name, CONTRIB_COL: "TEST VALUE (test)"} for r in org_repos]
)
exporter._load_existing_sheet = lambda: None  # don't overwrite the fake data

fetch_start = time.time()
repos = exporter.fetch_repos()
fetch_elapsed = time.time() - fetch_start
print(f"Testing with {len(repos)} repos")
print(f"fetch_repos() (incl. prewarm) took {fetch_elapsed:.1f}s")

start = time.time()
with ThreadPoolExecutor(max_workers=2) as ex:
    futures = {ex.submit(exporter._fetch_one, r): r for r in repos}
    for future in as_completed(futures):
        repo_args = futures[future]
        try:
            info = future.result()
            print(f"Done: {exporter._repo_label(repo_args)}")
        except Exception as e:
            print(f"FAILED: {exporter._repo_label(repo_args)} — {e}")

data = [future.result() for future in futures if not future.exception()]

pending_names = [(r.name, r.size) for r in exporter._pending_contributors]
print(f"Pending after pass 1: {pending_names}")

if exporter.has_pending_work():
    print(f"\n{len(exporter._pending_contributors)} repos pending, resolving...")
    exporter.resolve_pending(data)
    print("Done resolving pending.")

print(f"Total: {time.time() - start:.1f}s")

print(f"Skipped (reused sheet value): {len(exporter._skip_stats)}")
print(f"Rows holding TEST VALUE: {sum(1 for row in data if row[CONTRIB_COL] == 'TEST VALUE (test)')}")