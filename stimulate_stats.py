"""
Simulation: old blocking contributor-stats retry vs. the PR's prewarm + deferred second pass.

Uses your real GitHubExporter methods (_prewarm_stats_cache, get_top_contributors_fast,
resolve_pending, resolve_contributor_stats, _get_top_contributors_commits) against fake
repos. No network, no Google Sheets. Time is compressed: 1 real second = SCALE simulated
seconds, so a "13 minute" run finishes in a few seconds.

Run from the repo root:  python simulate_stats.py
"""
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

from repo_exporter.github import GitHubExporter, CONTRIBUTORS_COL

real_sleep = time.sleep  # captured before any patching

# ---------------- knobs ----------------
SCALE = 100                    # 1 real second = SCALE simulated seconds
NUM_REPOS = 60
COLD_READY_RANGE = (20, 120)   # simulated seconds GitHub needs after the FIRST stats request
FRACTION_NEVER_READY = 0.2     # of cold repos: stats never finish (forces commit-based fallback)
WORK_RANGE = (1, 4)            # simulated seconds of other per-repo metadata work
REQUEST_LATENCY = 0.5          # simulated seconds per stats API request
MAIN_WORKERS = 4               # matches BaseExporter.run()
OLD_ATTEMPTS = 3               # OLD behavior: 3 attempts, 20s sleep between = up to 40s/repo
OLD_SLEEP = 20                 # (edit these two to match the real old get_top_contributors)
SEED = 42
SCENARIOS = [("all cached (like Imageomics today)", 0.0),
             ("25% cold", 0.25),
             ("50% cold", 0.50)]
# ---------------------------------------


def sim_sleep(sim_seconds):
    real_sleep(sim_seconds / SCALE)


class Clock:
    def __init__(self):
        self.t0 = time.monotonic()

    def now(self):
        return (time.monotonic() - self.t0) * SCALE


class FakeAuthor:
    def __init__(self, name, login):
        self.name, self.login = name, login


class FakeWeek:
    def __init__(self, a, d):
        self.a, self.d = a, d


class FakeStats:
    def __init__(self, name, login):
        self.author = FakeAuthor(name, login)
        self.weeks = [FakeWeek(100, 10)]


class FakeRepo:
    def __init__(self, name, size, ready_after, work, clock):
        self.name, self.size = name, size
        self.ready_after, self.work, self.clock = ready_after, work, clock
        self._first_call = None
        self._lock = threading.Lock()

    def get_stats_contributors(self):
        sim_sleep(REQUEST_LATENCY)
        with self._lock:
            now = self.clock.now()
            if self._first_call is None:
                self._first_call = now  # GitHub starts computing on the first request
            ready = (now - self._first_call) >= self.ready_after
        return [FakeStats("Ada Lovelace", "ada")] if ready else None

    def get_contributors(self):
        return [FakeAuthor("Fallback User", "fallback")]


def make_repos(cold_fraction, clock):
    rng = random.Random(SEED)
    repos = []
    for i in range(NUM_REPOS):
        if rng.random() < cold_fraction:
            ready_after = (float("inf") if rng.random() < FRACTION_NEVER_READY
                           else rng.uniform(*COLD_READY_RANGE))
        else:
            ready_after = 0.0
        repos.append(FakeRepo(f"repo-{i:02d}", rng.randint(1, 100_000), ready_after,
                              rng.uniform(*WORK_RANGE), clock))
    return repos


def make_exporter():
    return GitHubExporter(org_name="sim", spreadsheet_id="x", sheet_name="x",
                          creds_path="x", token=None)


def run_old(repos, clock):
    """Old behavior: block the worker thread, retrying with sleeps, per repo."""
    exporter = make_exporter()

    def one(repo):
        sim_sleep(repo.work)
        for attempt in range(OLD_ATTEMPTS):
            if repo.get_stats_contributors():
                return "stats"
            if attempt < OLD_ATTEMPTS - 1:
                sim_sleep(OLD_SLEEP)
        exporter._get_top_contributors_commits(repo, 4)
        return "fallback"

    with ThreadPoolExecutor(max_workers=MAIN_WORKERS) as ex:
        results = [f.result() for f in as_completed([ex.submit(one, r) for r in repos])]
    return clock.now(), results.count("fallback")


def run_new(repos, clock):
    """New behavior: prewarm all, sort smallest-first, defer unready repos, resolve at end."""
    exporter = make_exporter()
    with patch("repo_exporter.github.time.sleep", sim_sleep):  # resolve_* sleeps use time.sleep
        exporter._prewarm_stats_cache(repos)
        prewarm_done = clock.now()
        repos = sorted(repos, key=lambda r: r.size)

        def one(repo):
            sim_sleep(repo.work)
            value, ready = exporter.get_top_contributors_fast(repo, 4)
            if not ready:
                exporter._pending_contributors.append(repo)
            return {"_repo_key": repo.name, CONTRIBUTORS_COL: value}

        with ThreadPoolExecutor(max_workers=MAIN_WORKERS) as ex:
            data = [f.result() for f in as_completed([ex.submit(one, r) for r in repos])]
        main_done = clock.now()
        pending = len(exporter._pending_contributors)
        if exporter.has_pending_work():
            exporter.resolve_pending(data)
    fallback = sum(1 for row in data if "(commit-based)" in str(row[CONTRIBUTORS_COL]))
    unresolved = sum(1 for row in data if row[CONTRIBUTORS_COL] is None)
    return clock.now(), prewarm_done, main_done, pending, fallback, unresolved


if __name__ == "__main__":
    print(f"{NUM_REPOS} repos, {MAIN_WORKERS} workers, times in SIMULATED seconds\n")
    for label, cold in SCENARIOS:
        c = Clock()
        old_total, old_fb = run_old(make_repos(cold, c), c)
        c = Clock()
        new_total, prewarm, main_done, pending, new_fb, unresolved = run_new(make_repos(cold, c), c)
        print(f"== {label} ==")
        print(f"  OLD total: {old_total:7.0f}s   commit-fallback repos: {old_fb}")
        print(f"  NEW total: {new_total:7.0f}s   (prewarm {prewarm:.0f}s, main pass done {main_done:.0f}s, "
              f"{pending} deferred, {new_fb} commit-fallback, {unresolved} left unresolved)")
        print(f"  difference: {old_total - new_total:+.0f}s ({(old_total - new_total) / old_total:+.0%})\n")