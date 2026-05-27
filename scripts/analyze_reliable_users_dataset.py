"""Dataset quality analysis for the reliable_users pipeline output.

Reads the CSVs produced by the reliable_users pipeline and reports:
  * basic user/game/edge counts
  * per-user collection size and overlap distributions
  * per-game user coverage distribution
  * selected-game coverage thresholds
  * discovery source concentration (source-rank bias)
  * edge-type breakdown
  * bipartite density on the selected-game subgraph

Pure stdlib — no pandas/numpy required. Outputs a plaintext report to stdout
and writes a copy to <run-dir>/dataset_quality_report.txt.

Usage:
  python scripts/analyze_reliable_users_dataset.py
  python scripts/analyze_reliable_users_dataset.py --run-label reliable_users_batch1
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.config import load_settings


# Columns in reliable_user_collection_edges.csv that are 0/1 status flags.
STATUS_FLAG_COLS = [
    "own",
    "prevowned",
    "fortrade",
    "want",
    "wanttoplay",
    "wanttobuy",
    "wishlist",
    "preordered",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze reliable_users pipeline dataset quality.")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--run-label", default="reliable_users_batch1")
    return parser.parse_args()


def pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.2f}%" if total else "n/a"


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if q <= 0:
        return sorted_values[0]
    if q >= 100:
        return sorted_values[-1]
    k = (len(sorted_values) - 1) * (q / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def summarize_numeric(label: str, values: list[float]) -> list[str]:
    if not values:
        return [f"{label}: (no data)"]
    s = sorted(values)
    return [
        f"{label}:",
        f"  count  = {len(s)}",
        f"  min    = {s[0]:.0f}",
        f"  p10    = {percentile(s, 10):.0f}",
        f"  p25    = {percentile(s, 25):.0f}",
        f"  median = {percentile(s, 50):.0f}",
        f"  mean   = {mean(s):.2f}",
        f"  p75    = {percentile(s, 75):.0f}",
        f"  p90    = {percentile(s, 90):.0f}",
        f"  p99    = {percentile(s, 99):.0f}",
        f"  max    = {s[-1]:.0f}",
    ]


def bucket_counts(values: list[int], thresholds: list[int]) -> list[tuple[int, int]]:
    """For each threshold t, return count of values >= t."""
    sorted_desc = sorted(values, reverse=True)
    out = []
    for t in thresholds:
        c = sum(1 for v in sorted_desc if v >= t)
        out.append((t, c))
    return out


def read_users(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def read_selected_games(path: Path) -> dict[int, dict]:
    games: dict[int, dict] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                bgg_id = int(row["bgg_id"])
            except (KeyError, ValueError):
                continue
            games[bgg_id] = row
    return games


def iter_edges(path: Path):
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


def safe_int(s: str | None) -> int:
    if s is None or s == "":
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0


def build_report(run_dir: Path) -> list[str]:
    users_csv = run_dir / "reliable_users.csv"
    edges_csv = run_dir / "reliable_user_collection_edges.csv"
    selected_csv = run_dir / "selected_games.csv"

    for p in (users_csv, edges_csv, selected_csv):
        if not p.exists():
            raise FileNotFoundError(f"Missing expected file: {p}")

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"RELIABLE USERS DATASET QUALITY REPORT")
    lines.append(f"Run directory: {run_dir}")
    lines.append("=" * 70)

    # -----------------------------
    # 1) Users
    # -----------------------------
    users = read_users(users_csv)
    selected_games = read_selected_games(selected_csv)
    n_users = len(users)
    n_selected = len(selected_games)

    lines.append("")
    lines.append("[1] BASIC COUNTS")
    lines.append(f"  reliable users      = {n_users}")
    lines.append(f"  selected games      = {n_selected}")

    # per-user numeric distributions
    coll_sizes = [safe_int(u.get("collection_item_count")) for u in users]
    owned = [safe_int(u.get("owned_count")) for u in users]
    rated = [safe_int(u.get("rated_count")) for u in users]
    overlap = [safe_int(u.get("selected_game_overlap_count")) for u in users]
    sel_owned = [safe_int(u.get("selected_owned_count")) for u in users]
    sel_rated = [safe_int(u.get("selected_rated_count")) for u in users]
    plays_sum = [safe_int(u.get("numplays_sum")) for u in users]

    lines.append("")
    lines.append("[2] PER-USER DISTRIBUTIONS")
    lines.extend(summarize_numeric("  collection_item_count", coll_sizes))
    lines.extend(summarize_numeric("  owned_count", owned))
    lines.extend(summarize_numeric("  rated_count", rated))
    lines.extend(summarize_numeric("  numplays_sum", plays_sum))
    lines.extend(summarize_numeric("  selected_game_overlap_count", overlap))
    lines.extend(summarize_numeric("  selected_owned_count", sel_owned))
    lines.extend(summarize_numeric("  selected_rated_count", sel_rated))

    # overlap buckets
    lines.append("")
    lines.append("[3] OVERLAP WITH SELECTED GAMES (users with >= N overlap)")
    for t, c in bucket_counts(overlap, [10, 25, 50, 100, 200, 500, 1000]):
        lines.append(f"  >= {t:>5}: {c:>6} users ({pct(c, n_users)})")

    # -----------------------------
    # 4) Discovery source bias
    # -----------------------------
    # source_game_ranks is pipe-delimited string of ranks
    rank_counter: Counter[int] = Counter()
    min_ranks: list[int] = []
    for u in users:
        raw = u.get("source_game_ranks") or ""
        ranks = []
        for piece in raw.split("|"):
            piece = piece.strip()
            if not piece:
                continue
            try:
                ranks.append(int(piece))
            except ValueError:
                continue
        if ranks:
            min_ranks.append(min(ranks))
            for r in ranks:
                rank_counter[r] += 1

    lines.append("")
    lines.append("[4] DISCOVERY SOURCE CONCENTRATION (rank of games that surfaced users)")
    lines.append(f"  distinct source-ranks observed = {len(rank_counter)}")
    if rank_counter:
        lines.append(f"  source-rank range              = {min(rank_counter)} .. {max(rank_counter)}")
        top_ranks = rank_counter.most_common(15)
        lines.append("  top 15 source-ranks by user-appearances:")
        for r, c in top_ranks:
            lines.append(f"    rank {r:>4}: {c:>5} user-appearances")
    if min_ranks:
        lines.extend(summarize_numeric("  min source-rank per user", min_ranks))

    # -----------------------------
    # 5) Edges — stream once, aggregate
    # -----------------------------
    lines.append("")
    lines.append("[5] EDGE-LEVEL STATS (streaming reliable_user_collection_edges.csv)")

    total_edges = 0
    per_game_user_set: dict[int, set[str]] = {}
    flag_counts: Counter[str] = Counter()
    user_edge_counts: Counter[str] = Counter()
    rated_edges = 0
    edges_on_selected = 0
    per_selected_game_users: dict[int, set[str]] = {gid: set() for gid in selected_games}

    for row in iter_edges(edges_csv):
        total_edges += 1
        user = row.get("username") or ""
        try:
            gid = int(row.get("bgg_id") or 0)
        except ValueError:
            gid = 0
        if not user or not gid:
            continue
        user_edge_counts[user] += 1
        s = per_game_user_set.setdefault(gid, set())
        s.add(user)
        if gid in per_selected_game_users:
            per_selected_game_users[gid].add(user)
            edges_on_selected += 1
        # flags
        for flag in STATUS_FLAG_COLS:
            if row.get(flag) == "1":
                flag_counts[flag] += 1
        if row.get("user_rating"):
            rated_edges += 1

    distinct_games = len(per_game_user_set)

    lines.append(f"  total edges                      = {total_edges}")
    lines.append(f"  edges on selected games          = {edges_on_selected} ({pct(edges_on_selected, total_edges)})")
    lines.append(f"  distinct games touched           = {distinct_games}")
    lines.append(f"  distinct selected games touched  = {sum(1 for s in per_selected_game_users.values() if s)}")
    lines.append(f"  edges with a user_rating         = {rated_edges} ({pct(rated_edges, total_edges)})")

    lines.append("")
    lines.append("  edge status-flag counts:")
    for flag in STATUS_FLAG_COLS:
        c = flag_counts.get(flag, 0)
        lines.append(f"    {flag:<12} = {c:>9} ({pct(c, total_edges)})")

    # per-user edge counts (cross-check vs collection_item_count)
    lines.append("")
    edge_per_user = list(user_edge_counts.values())
    lines.extend(summarize_numeric("  edges per user (from streamed edges file)", edge_per_user))

    # per-game user counts (all games)
    lines.append("")
    per_game_users = [len(s) for s in per_game_user_set.values()]
    lines.extend(summarize_numeric("  users per game (all games in edges)", per_game_users))

    # -----------------------------
    # 6) Selected game coverage
    # -----------------------------
    lines.append("")
    lines.append("[6] SELECTED-GAME COVERAGE")
    per_selected_users_count = [len(s) for s in per_selected_game_users.values()]
    touched_selected = sum(1 for c in per_selected_users_count if c > 0)
    lines.append(f"  selected games with >=1 user  : {touched_selected} / {n_selected} ({pct(touched_selected, n_selected)})")
    for t in [5, 10, 25, 50, 100, 250, 500, 1000]:
        c = sum(1 for x in per_selected_users_count if x >= t)
        lines.append(f"  selected games with >= {t:>5}  : {c} / {n_selected} ({pct(c, n_selected)})")

    lines.extend(summarize_numeric("  users-per-selected-game distribution", per_selected_users_count))

    # -----------------------------
    # 7) Bipartite density on selected subgraph
    # -----------------------------
    lines.append("")
    lines.append("[7] BIPARTITE DENSITY (users x selected games)")
    max_possible = n_users * n_selected
    density = (edges_on_selected / max_possible) if max_possible else 0.0
    lines.append(f"  max possible edges     = {max_possible}")
    lines.append(f"  observed edges         = {edges_on_selected}")
    lines.append(f"  density                = {density:.6f}  ({density*100:.4f}%)")
    lines.append(f"  avg edges per user     = {edges_on_selected / n_users:.2f}")
    lines.append(f"  avg edges per sel-game = {edges_on_selected / n_selected:.2f}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("END REPORT")
    lines.append("=" * 70)
    return lines


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    processed_root = Path(settings["paths"]["processed_data_dir"])
    if not processed_root.is_absolute():
        processed_root = settings["_meta"]["project_root"] / processed_root
    run_dir = processed_root / "reliable_users" / args.run_label

    report_lines = build_report(run_dir)
    text = "\n".join(report_lines)
    print(text)

    out_path = run_dir / "dataset_quality_report.txt"
    out_path.write_text(text, encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
