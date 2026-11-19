"""
Standalone test: how long does GitHub actually take to compute
contributor stats for a repo with no cached history?

Creates a throwaway private repo under your account, pushes one
commit via the Contents API (so there's real commit history for
GitHub to compute stats from), then polls get_stats_contributors()
in a loop, timestamping each attempt until stats come back ready
(or MAX_WAIT_SECONDS is hit). Deletes the repo at the end either way.

Requires GH_TOKEN in your .env with repo creation + deletion scope
(the "repo" scope on a classic PAT covers this; for a fine-grained
PAT you need Administration: Read and write on the target account).

Run it the same way you run test_concurrency.py:
    python test_stats_cache_timing.py
"""
from dotenv import load_dotenv
load_dotenv()

import os
import time
from github import Github, Auth

TOKEN = os.environ["GH_TOKEN"]
REPO_NAME = f"stats-cache-test-{int(time.time())}"
MAX_WAIT_SECONDS = 300   # give up after 5 minutes
POLL_INTERVAL_SECONDS = 5


def main():
    gh = Github(auth=Auth.Token(TOKEN))
    user = gh.get_user()

    print(f"Creating throwaway repo: {REPO_NAME}")
    repo = user.create_repo(REPO_NAME, private=True, auto_init=False)

    try:
        print("Pushing initial commit via Contents API...")
        repo.create_file(
            path="README.md",
            message="Initial commit for stats-cache timing test",
            content="# stats cache timing test\n",
        )

        print("Polling get_stats_contributors()...\n")
        start = time.time()
        attempt = 0

        while True:
            attempt += 1
            elapsed = time.time() - start

            try:
                stats = repo.get_stats_contributors()
            except Exception as e:
                stats = None
                print(f"  [{elapsed:6.1f}s] attempt {attempt}: error {type(e).__name__}: {e}")
            else:
                if stats:
                    print(f"  [{elapsed:6.1f}s] attempt {attempt}: READY -- {len(stats)} contributor(s)")
                    break
                print(f"  [{elapsed:6.1f}s] attempt {attempt}: not ready yet (202/empty)")

            if elapsed > MAX_WAIT_SECONDS:
                print(f"\nGave up after {MAX_WAIT_SECONDS}s without stats becoming ready.")
                break

            time.sleep(POLL_INTERVAL_SECONDS)

    finally:
        print(f"\nDeleting throwaway repo: {REPO_NAME}")
        repo.delete()


if __name__ == "__main__":
    main()