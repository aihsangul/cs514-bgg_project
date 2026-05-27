"""Per-mechanic / per-category coverage analysis of the current user-game graph.

Answers: "which mechanics or categories are underrepresented in our current
reliable-user pool?" — i.e. where should the next expansion batch target new
candidate users?

For each tag (mechanic or category):
  * n_games_with_tag_in_universe  — how many of the selected games have this tag
  * n_games_touched               — how many of those games have >=1 user edge
  * n_distinct_users              — unique users with >=1 edge on a tagged game
  * n_edges                       — total edges on tagged games
  * n_own_edges                   — subset of edges where own=1
  * users_per_game                — n_distinct_users / n_games_with_tag_in_universe
  * user_coverage_ratio           — n_distinct_users / total_reliable_users

Outputs sorted ascending by n_distinct_users (most underrepresented first).

Writes:
  data/processed/reliable_users/<run_label>/taxonomy_coverage_mechanics.csv
  data/processed/reliable_users/<run_label>/taxonomy_coverage_categories.csv
  data/processed/reliable_users/<run_label>/taxonomy_coverage_report.txt

Usage:
  python scripts/analyze_taxonomy_coverage.py
  python scripts/analyze_taxonomy_coverage.py --run-label reliable_users_batch1
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.config import load_settings


PIPE_SEP = " | "


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Per-mechanic / per-category coverage analysis.")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--run-label", default="reliable_users_batch1")
    parser.add_argument(
        "--details-csv",
        default="data/processed/top_ranked_games_details/top_ranked_games_details_top5000_ranked_only/top_ranked_games_details.csv",
        help="Path to the game details CSV that contains mechanics/categories.",
    )
    return parser.parse_args()


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split("|") if t.strip()]


def _load_game_tags(details_csv: Path, selected_ids: set[int]) -> tuple[dict[int, list[str]], dict[int, list[str]], dict[int, str]]:
    """Return (mechanics_by_game, categories_by_game, name_by_game) restricted to selected ids."""
    mech_by_game: dict[int, list[str]] = {}
    cat_by_game: dict[int, list[str]] = {}
    name_by_game: dict[int, str] = {}
    with details_csv.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                gid = int(row["bgg_id"])
            except (KeyError, ValueError):
                continue
            if gid not in selected_ids:
                continue
            mech_by_game[gid] = _split_tags(row.get("mechanics"))
            cat_by_game[gid] = _split_tags(row.get("categories"))
            name_by_game[gid] = row.get("name") or ""
    return mech_by_game, cat_by_game, name_by_game


def _load_selected_ids(selected_csv: Path) -> set[int]:
    ids: set[int] = set()
    with selected_csv.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                ids.add(int(row["bgg_id"]))
            except (KeyError, ValueError):
                continue
    return ids


def _load_reliable_usernames(users_csv: Path) -> set[str]:
    names: set[str] = set()
    with users_csv.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            u = (row.get("username") or "").strip()
            if u:
                names.add(u)
    return names


def _analyze_tag(
    label: str,
    tags_by_game: dict[int, list[str]],
    edges_path: Path,
    selected_ids: set[int],
) -> list[dict]:
    """Return one dict per distinct tag with coverage metrics."""
    # n_games_with_tag_in_universe
    games_with_tag: dict[str, set[int]] = defaultdict(set)
    for gid, tags in tags_by_game.items():
        for t in tags:
            games_with_tag[t].add(gid)

    # n_distinct_users per tag, n_edges per tag, n_own_edges per tag, games touched per tag
    users_per_tag: dict[str, set[str]] = defaultdict(set)
    edges_per_tag: dict[str, int] = defaultdict(int)
    own_edges_per_tag: dict[str, int] = defaultdict(int)
    games_touched_per_tag: dict[str, set[int]] = defaultdict(set)

    with edges_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                gid = int(row.get("bgg_id") or 0)
            except ValueError:
                continue
            if gid not in selected_ids:
                continue
            tags = tags_by_game.get(gid)
            if not tags:
                continue
            user = row.get("username") or ""
            if not user:
                continue
            own_flag = row.get("own") == "1"
            for t in tags:
                users_per_tag[t].add(user)
                edges_per_tag[t] += 1
                games_touched_per_tag[t].add(gid)
                if own_flag:
                    own_edges_per_tag[t] += 1

    results: list[dict] = []
    for tag, games in games_with_tag.items():
        n_games = len(games)
        touched = games_touched_per_tag.get(tag, set())
        users = users_per_tag.get(tag, set())
        results.append(
            {
                f"{label}": tag,
                "n_games_with_tag_in_universe": n_games,
                "n_games_touched": len(touched),
                "n_distinct_users": len(users),
                "n_edges": edges_per_tag.get(tag, 0),
                "n_own_edges": own_edges_per_tag.get(tag, 0),
                "users_per_game": round(len(users) / n_games, 2) if n_games else 0,
            }
        )
    return results


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _fmt_table(rows: list[dict], keys: list[str], widths: list[int]) -> list[str]:
    out: list[str] = []
    header = "  ".join(f"{k:<{w}}" for k, w in zip(keys, widths))
    out.append(header)
    out.append("-" * len(header))
    for r in rows:
        out.append("  ".join(f"{str(r[k]):<{w}}" for k, w in zip(keys, widths)))
    return out


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    project_root = settings["_meta"]["project_root"]

    proc_root = Path(settings["paths"]["processed_data_dir"])
    if not proc_root.is_absolute():
        proc_root = project_root / proc_root
    run_dir = proc_root / "reliable_users" / args.run_label

    selected_csv = run_dir / "selected_games.csv"
    edges_csv = run_dir / "reliable_user_collection_edges.csv"
    users_csv = run_dir / "reliable_users.csv"
    details_csv = Path(args.details_csv)
    if not details_csv.is_absolute():
        details_csv = project_root / details_csv

    for p in (selected_csv, edges_csv, users_csv, details_csv):
        if not p.exists():
            raise FileNotFoundError(f"Missing required file: {p}")

    selected_ids = _load_selected_ids(selected_csv)
    reliable_users = _load_reliable_usernames(users_csv)
    mech_by_game, cat_by_game, _ = _load_game_tags(details_csv, selected_ids)

    total_users = len(reliable_users)
    print(f"Selected games:   {len(selected_ids)}")
    print(f"Games with details: {len(mech_by_game)}")
    print(f"Reliable users:   {total_users}")
    missing = len(selected_ids) - len(mech_by_game)
    if missing:
        print(f"  (note: {missing} selected games are missing from details CSV — excluded from analysis)")

    print("\n[mechanics] streaming edges...")
    mech_rows = _analyze_tag("mechanic", mech_by_game, edges_csv, selected_ids)
    for r in mech_rows:
        r["user_coverage_ratio"] = round(r["n_distinct_users"] / total_users, 4) if total_users else 0.0

    print("[categories] streaming edges...")
    cat_rows = _analyze_tag("category", cat_by_game, edges_csv, selected_ids)
    for r in cat_rows:
        r["user_coverage_ratio"] = round(r["n_distinct_users"] / total_users, 4) if total_users else 0.0

    mech_rows.sort(key=lambda r: (r["n_distinct_users"], r["n_games_with_tag_in_universe"]))
    cat_rows.sort(key=lambda r: (r["n_distinct_users"], r["n_games_with_tag_in_universe"]))

    mech_fields = [
        "mechanic",
        "n_games_with_tag_in_universe",
        "n_games_touched",
        "n_distinct_users",
        "user_coverage_ratio",
        "n_edges",
        "n_own_edges",
        "users_per_game",
    ]
    cat_fields = [
        "category",
        "n_games_with_tag_in_universe",
        "n_games_touched",
        "n_distinct_users",
        "user_coverage_ratio",
        "n_edges",
        "n_own_edges",
        "users_per_game",
    ]

    mech_out = run_dir / "taxonomy_coverage_mechanics.csv"
    cat_out = run_dir / "taxonomy_coverage_categories.csv"
    _write_csv(mech_out, mech_rows, mech_fields)
    _write_csv(cat_out, cat_rows, cat_fields)

    # Report
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"TAXONOMY COVERAGE REPORT — {args.run_label}")
    lines.append("=" * 78)
    lines.append(f"reliable users      = {total_users}")
    lines.append(f"selected games      = {len(selected_ids)}")
    lines.append(f"games with details  = {len(mech_by_game)}")
    lines.append(f"distinct mechanics  = {len(mech_rows)}")
    lines.append(f"distinct categories = {len(cat_rows)}")

    # --- mechanics ---
    lines.append("")
    lines.append("[MECHANICS] 20 most underrepresented (lowest n_distinct_users)")
    lines.append("            filter: n_games_with_tag >= 3 (ignore singleton tags)")
    filtered = [r for r in mech_rows if r["n_games_with_tag_in_universe"] >= 3][:20]
    lines.extend(_fmt_table(
        filtered,
        ["mechanic", "n_games_with_tag_in_universe", "n_games_touched", "n_distinct_users", "user_coverage_ratio", "users_per_game"],
        [42, 10, 10, 10, 10, 10],
    ))

    lines.append("")
    lines.append("[MECHANICS] 20 best represented (highest n_distinct_users)")
    best = sorted(mech_rows, key=lambda r: -r["n_distinct_users"])[:20]
    lines.extend(_fmt_table(
        best,
        ["mechanic", "n_games_with_tag_in_universe", "n_distinct_users", "user_coverage_ratio", "users_per_game"],
        [42, 10, 10, 10, 10],
    ))

    # --- categories ---
    lines.append("")
    lines.append("[CATEGORIES] 20 most underrepresented (lowest n_distinct_users)")
    lines.append("             filter: n_games_with_tag >= 3")
    filtered_c = [r for r in cat_rows if r["n_games_with_tag_in_universe"] >= 3][:20]
    lines.extend(_fmt_table(
        filtered_c,
        ["category", "n_games_with_tag_in_universe", "n_games_touched", "n_distinct_users", "user_coverage_ratio", "users_per_game"],
        [40, 10, 10, 10, 10, 10],
    ))

    lines.append("")
    lines.append("[CATEGORIES] 20 best represented (highest n_distinct_users)")
    best_c = sorted(cat_rows, key=lambda r: -r["n_distinct_users"])[:20]
    lines.extend(_fmt_table(
        best_c,
        ["category", "n_games_with_tag_in_universe", "n_distinct_users", "user_coverage_ratio", "users_per_game"],
        [40, 10, 10, 10, 10],
    ))

    lines.append("")
    lines.append("Files written:")
    lines.append(f"  {mech_out}")
    lines.append(f"  {cat_out}")
    lines.append("=" * 78)

    text = "\n".join(lines)
    print("\n" + text)
    report_path = run_dir / "taxonomy_coverage_report.txt"
    report_path.write_text(text, encoding="utf-8")
    print(f"\nReport saved to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
