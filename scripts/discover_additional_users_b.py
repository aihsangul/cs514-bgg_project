"""Diversity-expansion pipeline: collect additional BGG users from deliberately
broader seed games to correct the top-69 discovery bias in reliable_users_batch1.

Four stages, each resumable:
  1. SEED SELECTION  (offline) - 180 taxonomy-deficit + 90 rank-stratified + 30 wishlist-contrast
  2. DISCOVERY       (API)     - plays + ratingcomments per seed, feeds candidate pool
  3. ENRICHMENT      (API)     - scored, asymmetric prioritization; stats=1 single-fetch per user
  4. EVALUATION      (offline) - cohort comparison vs core_top69 baseline

The baseline batch (reliable_users_batch1) is not touched. Merging is a separate
step the user performs after reviewing the evaluation report.

Outputs to:
  data/raw/reliable_users/diversity_expansion_batch1/
  data/processed/reliable_users/diversity_expansion_batch1/

Usage:
  python scripts/discover_additional_users_b.py
  python scripts/discover_additional_users_b.py --max-runtime-hours 12
  python scripts/discover_additional_users_b.py --resume   (default: always resumes if state exists)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.candidate_users import (
    parse_play_users,
    parse_rating_comment_users,
)
from bgg_project.collectors.rank_range_users import (
    USER_COLLECTION_EDGE_FIELDNAMES,
    USER_SUMMARY_FIELDNAMES,
    build_failed_user_summary,
    build_user_summary,
    merge_collection_rows,
    parse_collection_items,
)
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


# -----------------------------------------------------------------------------
# Constants (tuned per methodology agreement)
# -----------------------------------------------------------------------------
RUN_LABEL = "diversity_expansion_batch1"
BASELINE_RUN_LABEL = "reliable_users_batch1"

# Seed budget
SEED_TOTAL = 300
SEED_TAXONOMY_QUOTA = 180
SEED_RANK_STRATIFIED_QUOTA = 90
SEED_CONTRAST_QUOTA = 30

# Rank-stratified sampling quotas (sum == SEED_RANK_STRATIFIED_QUOTA)
RANK_BANDS = [
    (70, 200),
    (201, 500),
    (501, 1000),
    (1001, 2500),
]
RANK_BAND_QUOTAS = [25, 25, 20, 20]

# Contrast-seed operational definition
CONTRAST_MIN_OWNED = 500

# Discovery depth per seed type
PLAYS_PAGES_TAXONOMY = 2
PLAYS_PAGES_RANK = 1
PLAYS_PAGES_CONTRAST = 1
RATINGCOMMENTS_PAGES_ALL = 1
RATINGCOMMENTS_PAGE_SIZE = 100

# API hygiene for long unattended runs
MIN_REQUEST_SPACING_SECONDS = 7

# Enrichment thresholds (dual-pool)
MIN_COLLECTION_ITEMS_STRICT = 50
MIN_OVERLAP_STRICT = 10
MIN_COLLECTION_ITEMS_LOOSE = 20
MIN_OVERLAP_LOOSE = 3

# Stopping rules
DEFAULT_MAX_RUNTIME_HOURS = 14.0
MAX_ENRICHED_USERS = 5000
QUALITY_COLLAPSE_WINDOW = 200
QUALITY_COLLAPSE_MIN_RATE = 0.15  # <15% established over window => collapse
SNAPSHOT_EVERY_N_ENRICHED = 500
TARGET_TAG_IMPROVEMENT_FRACTION = 0.20  # 20% committed-user growth vs baseline
TARGET_TAGS_IMPROVED_FRACTION = 0.75    # 75% of target tags must clear the bar
PLATEAU_RELATIVE_GAIN = 0.05            # <5% delta between last 2 snapshots => plateau

# Candidate scoring tiers (lower = higher priority)
SCORE_FROM_UNDERREP_SEED = 0
SCORE_MULTI_SEED = 1
SCORE_SINGLE_PLAYS = 2
SCORE_SINGLE_RATING_COMMENT = 3

DISCOVERY_ROW_FIELDS_RATING = [
    "username", "source_type", "bgg_id", "game_name", "overall_rank",
    "page", "rating", "comment_has_text", "seed_type", "seed_tags",
]
DISCOVERY_ROW_FIELDS_PLAY = [
    "username", "source_type", "bgg_id", "game_name", "overall_rank",
    "page", "play_id", "play_userid", "play_date", "quantity", "length",
    "seed_type", "seed_tags",
]

CANDIDATE_FIELDS = [
    "username", "score_tier", "discovery_count",
    "rating_comment_count", "play_player_count",
    "source_games", "source_game_ranks", "source_types",
    "source_seed_types", "source_underrep_tags",
    "enrichment_status",  # pending | done | skipped_baseline | error
]

COHORT_LABEL = "expanded_diversity_01"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diversity-expansion user collection (isolated from reliable_users_batch1)."
    )
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--run-label", default=RUN_LABEL)
    parser.add_argument("--baseline-run-label", default=BASELINE_RUN_LABEL)
    parser.add_argument(
        "--details-csv",
        default="data/processed/top_ranked_games_details/top_ranked_games_details_top5000_ranked_only/top_ranked_games_details.csv",
    )
    parser.add_argument(
        "--coverage-mechanics-csv",
        default=None,
        help="Taxonomy coverage CSV (mechanics). Defaults to baseline run's output.",
    )
    parser.add_argument(
        "--coverage-categories-csv",
        default=None,
        help="Taxonomy coverage CSV (categories). Defaults to baseline run's output.",
    )
    parser.add_argument("--max-runtime-hours", type=float, default=DEFAULT_MAX_RUNTIME_HOURS)
    parser.add_argument("--max-enriched-users", type=int, default=MAX_ENRICHED_USERS)
    parser.add_argument("--dry-run", action="store_true", help="Run seed selection only; don't hit the API.")
    parser.add_argument("--seed-random", type=int, default=42, help="RNG seed for stratified sampling.")
    return parser.parse_args()


def _user_file_stem(username: str) -> str:
    safe = "".join(ch for ch in username.lower() if ch.isalnum())[:16] or "user"
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:12]
    return f"{safe}_{digest}"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append_csv_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = " | ".join(str(x) for x in v) if isinstance(v, list) else v
            w.writerow(out)


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _safe_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except ValueError:
        return None


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _split_pipe(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split("|") if t.strip()]


# -----------------------------------------------------------------------------
# Stage 1: Seed Selection
# -----------------------------------------------------------------------------
def select_taxonomy_deficit_seeds(
    details_rows: list[dict],
    coverage_mech_rows: list[dict],
    coverage_cat_rows: list[dict],
    *,
    quota: int,
    already_picked: set[int],
    logger: logging.Logger,
) -> list[dict]:
    """Pick games carrying underrepresented tags.

    Strategy: take the bottom-20 underrepresented mechanics + bottom-20 categories
    (filtered to n_games_with_tag_in_universe >= 5 so we don't chase singletons).
    For each tag, pick its top 4 games by num_comments. Deduplicate. Cap at quota.
    """
    def _bottom_tags(rows: list[dict], label: str, n: int = 20) -> list[str]:
        filt = [r for r in rows if _safe_int(r.get("n_games_with_tag_in_universe")) and int(r["n_games_with_tag_in_universe"]) >= 5]
        filt.sort(key=lambda r: (_safe_float(r.get("user_coverage_ratio")) or 0.0))
        return [r[label] for r in filt[:n]]

    mech_targets = _bottom_tags(coverage_mech_rows, "mechanic", n=20)
    cat_targets = _bottom_tags(coverage_cat_rows, "category", n=20)
    logger.info("Taxonomy targets: %s mechanics, %s categories", len(mech_targets), len(cat_targets))

    # Build a game-index with parsed num_comments
    for row in details_rows:
        row["_bgg_id_int"] = _safe_int(row.get("bgg_id"))
        row["_rank_int"] = _safe_int(row.get("overall_rank"))
        row["_num_comments"] = _safe_int(row.get("num_comments")) or 0
        row["_owned"] = _safe_int(row.get("owned")) or 0
        row["_mechanics_list"] = _split_pipe(row.get("mechanics"))
        row["_categories_list"] = _split_pipe(row.get("categories"))

    chosen: list[dict] = []
    chosen_ids: set[int] = set()

    def _pick_for_tag(target_label: str, tag: str, pool_list_key: str, n_per_tag: int) -> int:
        picked = 0
        candidates = [g for g in details_rows if tag in g[pool_list_key]
                      and g["_bgg_id_int"] and g["_bgg_id_int"] not in chosen_ids
                      and g["_bgg_id_int"] not in already_picked]
        candidates.sort(key=lambda g: -g["_num_comments"])
        for g in candidates[:n_per_tag]:
            chosen.append({
                "bgg_id": g["_bgg_id_int"],
                "name": g.get("name"),
                "overall_rank": g["_rank_int"],
                "seed_type": "taxonomy_deficit",
                "seed_tag_kind": target_label,
                "seed_tag": tag,
                "reason": f"underrep_{target_label}={tag}",
            })
            chosen_ids.add(g["_bgg_id_int"])
            picked += 1
            if len(chosen) >= quota:
                break
        return picked

    # Round-robin across tags so no single tag monopolizes the budget
    tag_queue: list[tuple[str, str]] = [("mechanic", t) for t in mech_targets] + [("category", t) for t in cat_targets]
    per_tag_n = 4
    while tag_queue and len(chosen) < quota:
        label, tag = tag_queue.pop(0)
        pool_key = "_mechanics_list" if label == "mechanic" else "_categories_list"
        _pick_for_tag(label, tag, pool_key, n_per_tag=per_tag_n)

    logger.info("Taxonomy-deficit seeds picked: %s (quota %s)", len(chosen), quota)
    return chosen


def select_rank_stratified_seeds(
    details_rows: list[dict],
    *,
    quotas: list[int],
    bands: list[tuple[int, int]],
    already_picked: set[int],
    rng: random.Random,
    logger: logging.Logger,
) -> list[dict]:
    chosen: list[dict] = []
    for (lo, hi), quota in zip(bands, quotas):
        pool = [g for g in details_rows
                if g["_rank_int"] and lo <= g["_rank_int"] <= hi
                and g["_bgg_id_int"] not in already_picked]
        rng.shuffle(pool)
        pick = pool[:quota]
        for g in pick:
            chosen.append({
                "bgg_id": g["_bgg_id_int"],
                "name": g.get("name"),
                "overall_rank": g["_rank_int"],
                "seed_type": "rank_stratified",
                "seed_tag_kind": "rank_band",
                "seed_tag": f"{lo}-{hi}",
                "reason": f"rank_band={lo}-{hi}",
            })
            already_picked.add(g["_bgg_id_int"])
        logger.info("Rank band %s-%s: picked %s (quota %s, pool %s)", lo, hi, len(pick), quota, len(pool))
    return chosen


def select_contrast_seeds(
    details_rows: list[dict],
    *,
    quota: int,
    already_picked: set[int],
    logger: logging.Logger,
) -> list[dict]:
    """Wishlist-heavy games: high (wanting + wishing) / owned ratio, owned >= CONTRAST_MIN_OWNED."""
    scored: list[tuple[float, dict]] = []
    for g in details_rows:
        if g["_bgg_id_int"] in already_picked:
            continue
        owned = _safe_int(g.get("owned")) or 0
        if owned < CONTRAST_MIN_OWNED:
            continue
        wanting = _safe_int(g.get("wanting")) or 0
        wishing = _safe_int(g.get("wishing")) or 0
        if (wanting + wishing) <= 0:
            continue
        ratio = (wanting + wishing) / owned
        scored.append((ratio, g))
    scored.sort(key=lambda t: -t[0])
    chosen: list[dict] = []
    for ratio, g in scored[:quota]:
        chosen.append({
            "bgg_id": g["_bgg_id_int"],
            "name": g.get("name"),
            "overall_rank": g["_rank_int"],
            "seed_type": "wishlist_contrast",
            "seed_tag_kind": "wishlist_ratio",
            "seed_tag": f"ratio={ratio:.3f}",
            "reason": f"wishlist_ratio={ratio:.3f}_owned={g['_owned']}",
        })
        already_picked.add(g["_bgg_id_int"])
    logger.info("Contrast seeds picked: %s (quota %s)", len(chosen), quota)
    return chosen


def run_seed_selection(
    *,
    details_csv: Path,
    coverage_mech_csv: Path,
    coverage_cat_csv: Path,
    out_path: Path,
    rng: random.Random,
    logger: logging.Logger,
) -> list[dict]:
    if out_path.exists():
        logger.info("Seed file exists, loading: %s", out_path)
        return _read_csv_rows(out_path)

    details_rows = _read_csv_rows(details_csv)
    mech_rows = _read_csv_rows(coverage_mech_csv)
    cat_rows = _read_csv_rows(coverage_cat_csv)
    logger.info("Loaded %s game-detail rows, %s mechanic-coverage rows, %s category-coverage rows",
                len(details_rows), len(mech_rows), len(cat_rows))

    already_picked: set[int] = set()

    # Must enrich each game row with int fields before seed selection
    for row in details_rows:
        row["_bgg_id_int"] = _safe_int(row.get("bgg_id"))
        row["_rank_int"] = _safe_int(row.get("overall_rank"))
        row["_num_comments"] = _safe_int(row.get("num_comments")) or 0
        row["_owned"] = _safe_int(row.get("owned")) or 0
        row["_mechanics_list"] = _split_pipe(row.get("mechanics"))
        row["_categories_list"] = _split_pipe(row.get("categories"))

    # Exclude ranks 1-69 (the core_top69 seed region) from all picks
    CORE_TOP_LIMIT = 69
    for g in details_rows:
        if g["_rank_int"] and g["_rank_int"] <= CORE_TOP_LIMIT:
            already_picked.add(g["_bgg_id_int"])

    seeds: list[dict] = []
    seeds += select_taxonomy_deficit_seeds(
        details_rows, mech_rows, cat_rows,
        quota=SEED_TAXONOMY_QUOTA, already_picked=already_picked, logger=logger,
    )
    already_picked.update(s["bgg_id"] for s in seeds)
    seeds += select_rank_stratified_seeds(
        details_rows, quotas=RANK_BAND_QUOTAS, bands=RANK_BANDS,
        already_picked=already_picked, rng=rng, logger=logger,
    )
    already_picked.update(s["bgg_id"] for s in seeds)
    seeds += select_contrast_seeds(
        details_rows, quota=SEED_CONTRAST_QUOTA,
        already_picked=already_picked, logger=logger,
    )

    # Write seed CSV
    seed_fields = ["bgg_id", "name", "overall_rank", "seed_type", "seed_tag_kind", "seed_tag", "reason"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=seed_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(seeds)
    logger.info("Wrote %s seed games -> %s", len(seeds), out_path)
    return seeds


# -----------------------------------------------------------------------------
# Stage 2: Discovery
# -----------------------------------------------------------------------------
def _plays_pages_for_seed(seed_type: str) -> int:
    if seed_type == "taxonomy_deficit":
        return PLAYS_PAGES_TAXONOMY
    if seed_type == "rank_stratified":
        return PLAYS_PAGES_RANK
    return PLAYS_PAGES_CONTRAST


def run_discovery(
    client: BGGClient,
    seeds: list[dict],
    *,
    raw_dir: Path,
    processed_dir: Path,
    state: dict,
    logger: logging.Logger,
) -> None:
    rating_rows_path = processed_dir / "all_discovery_rating_comment_rows.csv"
    play_rows_path = processed_dir / "all_discovery_play_rows.csv"
    discovery_raw_dir = raw_dir / "discovery"
    discovery_raw_dir.mkdir(parents=True, exist_ok=True)

    processed_seeds: set[int] = set(state.get("processed_seed_ids", []))
    total_seeds = len(seeds)
    logger.info("Discovery: %s seeds total, %s already processed", total_seeds, len(processed_seeds))

    for idx, seed in enumerate(seeds, start=1):
        try:
            bgg_id = int(seed["bgg_id"])
        except (KeyError, ValueError, TypeError):
            continue
        if bgg_id in processed_seeds:
            continue

        seed_type = seed.get("seed_type") or "unknown"
        seed_tag = seed.get("seed_tag") or ""
        rank = _safe_int(seed.get("overall_rank"))
        game_name = seed.get("name") or ""

        logger.info("[discovery %s/%s] seed %s (%s, rank=%s, type=%s, tag=%s)",
                    idx, total_seeds, bgg_id, game_name, rank, seed_type, seed_tag)

        rating_rows: list[dict] = []
        play_rows: list[dict] = []

        # ratingcomments
        for page in range(1, RATINGCOMMENTS_PAGES_ALL + 1):
            try:
                xml = client.get_thing_ratingcomments(bgg_id, page=page, page_size=RATINGCOMMENTS_PAGE_SIZE)
            except Exception as exc:
                logger.warning("  ratingcomments fetch failed for %s page %s: %s", bgg_id, page, exc)
                continue
            _write_text(discovery_raw_dir / f"ratingcomments_{bgg_id}_p{page:02d}.xml", xml)
            try:
                rows = parse_rating_comment_users(xml, bgg_id=bgg_id, game_name=game_name,
                                                  overall_rank=rank or 0, page=page)
            except Exception as exc:
                logger.warning("  ratingcomments parse failed for %s page %s: %s", bgg_id, page, exc)
                rows = []
            for r in rows:
                r["seed_type"] = seed_type
                r["seed_tags"] = seed_tag
            rating_rows.extend(rows)

        # plays
        plays_pages = _plays_pages_for_seed(seed_type)
        for page in range(1, plays_pages + 1):
            try:
                xml = client.get_plays_for_item(bgg_id, page=page)
            except Exception as exc:
                logger.warning("  plays fetch failed for %s page %s: %s", bgg_id, page, exc)
                continue
            _write_text(discovery_raw_dir / f"plays_{bgg_id}_p{page:02d}.xml", xml)
            try:
                rows = parse_play_users(xml, bgg_id=bgg_id, game_name=game_name,
                                        overall_rank=rank or 0, page=page)
            except Exception as exc:
                logger.warning("  plays parse failed for %s page %s: %s", bgg_id, page, exc)
                rows = []
            for r in rows:
                r["seed_type"] = seed_type
                r["seed_tags"] = seed_tag
            play_rows.extend(rows)

        if rating_rows:
            _append_csv_rows(rating_rows_path, rating_rows, DISCOVERY_ROW_FIELDS_RATING)
        if play_rows:
            _append_csv_rows(play_rows_path, play_rows, DISCOVERY_ROW_FIELDS_PLAY)
        logger.info("  -> rating_rows=%s, play_rows=%s", len(rating_rows), len(play_rows))

        processed_seeds.add(bgg_id)
        state["processed_seed_ids"] = sorted(processed_seeds)
        state["stage"] = "discovery"
        state["discovery_seeds_processed"] = len(processed_seeds)
        _save_state(processed_dir, state)


# -----------------------------------------------------------------------------
# Stage 3: Candidate aggregation + scoring + enrichment
# -----------------------------------------------------------------------------
def aggregate_and_score_candidates(
    rating_rows: list[dict],
    play_rows: list[dict],
    *,
    underrep_tag_set: set[str],
    baseline_usernames: set[str],
    logger: logging.Logger,
) -> list[dict]:
    """Aggregate discovery rows into per-user candidate records with an asymmetric score tier."""
    agg: dict[str, dict] = {}

    def _touch(row: dict, source_type: str) -> None:
        u = row.get("username") or ""
        if not u:
            return
        entry = agg.setdefault(u, {
            "username": u,
            "discovery_count": 0,
            "rating_comment_count": 0,
            "play_player_count": 0,
            "source_games": [],
            "source_game_ranks": [],
            "source_types": [],
            "source_seed_types": [],
            "source_underrep_tags": [],
        })
        entry["discovery_count"] += 1
        if source_type == "rating_comment":
            entry["rating_comment_count"] += 1
        else:
            entry["play_player_count"] += 1
        name = row.get("game_name")
        rank = _safe_int(row.get("overall_rank"))
        stype = row.get("source_type") or source_type
        seed_type = row.get("seed_type") or ""
        seed_tag = row.get("seed_tags") or ""
        if name and name not in entry["source_games"]:
            entry["source_games"].append(name)
        if rank is not None and rank not in entry["source_game_ranks"]:
            entry["source_game_ranks"].append(rank)
        if stype and stype not in entry["source_types"]:
            entry["source_types"].append(stype)
        if seed_type and seed_type not in entry["source_seed_types"]:
            entry["source_seed_types"].append(seed_type)
        if seed_tag and seed_tag in underrep_tag_set and seed_tag not in entry["source_underrep_tags"]:
            entry["source_underrep_tags"].append(seed_tag)

    for r in rating_rows:
        _touch(r, "rating_comment")
    for r in play_rows:
        _touch(r, "play_player")

    # Score assignment
    candidates: list[dict] = []
    for u, entry in agg.items():
        if u in baseline_usernames:
            entry["enrichment_status"] = "skipped_baseline"
            entry["score_tier"] = -1
        else:
            entry["enrichment_status"] = "pending"
            # Asymmetric scoring
            if entry["source_underrep_tags"]:
                entry["score_tier"] = SCORE_FROM_UNDERREP_SEED
            elif entry["discovery_count"] >= 2:
                entry["score_tier"] = SCORE_MULTI_SEED
            elif entry["play_player_count"] >= 1 and entry["rating_comment_count"] == 0:
                entry["score_tier"] = SCORE_SINGLE_PLAYS
            else:
                entry["score_tier"] = SCORE_SINGLE_RATING_COMMENT
        candidates.append(entry)

    # Sort by score ASC (lower = higher priority), break ties by discovery_count DESC
    candidates.sort(key=lambda e: (e["score_tier"] if e["score_tier"] >= 0 else 999,
                                   -e["discovery_count"],
                                   e["username"].lower()))

    n_baseline = sum(1 for c in candidates if c["enrichment_status"] == "skipped_baseline")
    by_tier: dict[int, int] = defaultdict(int)
    for c in candidates:
        if c["enrichment_status"] == "pending":
            by_tier[c["score_tier"]] += 1
    logger.info("Aggregated %s unique candidates (%s already in baseline, skipped)", len(candidates), n_baseline)
    logger.info("Score tier distribution (pending only):")
    for tier in sorted(by_tier.keys()):
        label = {
            0: "underrep_seed",
            1: "multi_seed",
            2: "single_plays",
            3: "single_rating_comment",
        }.get(tier, f"tier_{tier}")
        logger.info("  tier %s (%s): %s", tier, label, by_tier[tier])
    return candidates


def run_enrichment(
    client: BGGClient,
    candidates: list[dict],
    *,
    selected_game_ids: set[int],
    raw_dir: Path,
    processed_dir: Path,
    state: dict,
    max_runtime_hours: float,
    max_enriched_users: int,
    baseline_game_tag_map: dict[int, list[str]],
    target_underrep_tags: set[str],
    baseline_target_tag_users: dict[str, set[str]],
    logger: logging.Logger,
) -> str:
    """Enrich candidates with collection?stats=1. Returns stop reason string."""
    edges_path = processed_dir / "all_user_collection_edges.csv"
    summaries_path = processed_dir / "all_user_summaries.csv"
    errors_path = processed_dir / "all_user_errors.csv"
    reliable_path = processed_dir / "reliable_users.csv"
    community_path = processed_dir / "community_users.csv"
    collections_raw_dir = raw_dir / "collections"
    collections_raw_dir.mkdir(parents=True, exist_ok=True)

    enriched_ids: set[str] = set(state.get("enriched_usernames", []))
    already_reliable: set[str] = set(state.get("reliable_usernames", []))
    already_community: set[str] = set(state.get("community_usernames", []))

    start_time = time.time()
    deadline = start_time + max_runtime_hours * 3600.0

    # Running state for quality-collapse + periodic snapshots
    recent_results: list[int] = []  # 1 if reliable, 0 if not, rolling last QUALITY_COLLAPSE_WINDOW
    new_enriched_this_run = 0
    requests_made_this_run = 0
    throughput_start_time = time.time()
    snapshots_dir = processed_dir / "diversity_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Expansion cohort's per-tag committed users (rebuilt as we go)
    expansion_tag_users: dict[str, set[str]] = defaultdict(set)

    total_pending = sum(1 for c in candidates if c["enrichment_status"] == "pending" and c["username"] not in enriched_ids)
    logger.info("Enrichment queue size: %s (already enriched this run label: %s)", total_pending, len(enriched_ids))
    if total_pending == 0:
        return "queue_empty"

    stop_reason = "completed"
    processed_count = 0

    for cand in candidates:
        if cand["enrichment_status"] != "pending":
            continue
        username = cand["username"]
        if username in enriched_ids:
            continue

        # Hard caps
        if time.time() >= deadline:
            stop_reason = "max_runtime_hours"
            break
        if new_enriched_this_run >= max_enriched_users:
            stop_reason = "max_enriched_users"
            break

        # Quality-collapse check (only kicks in after window is full)
        if len(recent_results) >= QUALITY_COLLAPSE_WINDOW:
            est_rate = sum(recent_results) / len(recent_results)
            if est_rate < QUALITY_COLLAPSE_MIN_RATE:
                stop_reason = f"quality_collapse_rate_{est_rate:.3f}"
                break

        processed_count += 1
        logger.info("[enrich %s/%s] %s (tier=%s, disc=%s, plays=%s, ratings=%s)",
                    processed_count, total_pending, username, cand["score_tier"],
                    cand["discovery_count"], cand["play_player_count"], cand["rating_comment_count"])

        try:
            xml = client.get_collection_for_user(username, stats=True)
            requests_made_this_run += 1
            _write_text(collections_raw_dir / f"{_user_file_stem(username)}_collection_all.xml", xml)
            rows = parse_collection_items(xml, username=username, source_label="collection_all")
            merged = merge_collection_rows(rows)
            candidate_stub = {
                "username": username,
                "discovery_count": cand["discovery_count"],
                "rating_comment_count": cand["rating_comment_count"],
                "play_player_count": cand["play_player_count"],
                "source_games": cand.get("source_games") or [],
                "source_game_ranks": cand.get("source_game_ranks") or [],
                "source_types": cand.get("source_types") or [],
            }
            # Source fields may have been flattened to pipe-strings if loaded from CSV - handle both
            for k in ("source_games", "source_game_ranks", "source_types"):
                v = candidate_stub[k]
                if isinstance(v, str):
                    candidate_stub[k] = [p.strip() for p in v.split("|") if p.strip()]
                    if k == "source_game_ranks":
                        candidate_stub[k] = [int(p) for p in candidate_stub[k] if p.isdigit()]
            summary = build_user_summary(candidate_stub, merged, selected_game_ids=selected_game_ids)
            _append_csv_rows(edges_path, merged, USER_COLLECTION_EDGE_FIELDNAMES)
            _append_csv_rows(summaries_path, [summary], USER_SUMMARY_FIELDNAMES)

            ci = summary["collection_item_count"] or 0
            ov = summary["selected_game_overlap_count"] or 0
            is_reliable = ci >= MIN_COLLECTION_ITEMS_STRICT and ov >= MIN_OVERLAP_STRICT
            is_community = ci >= MIN_COLLECTION_ITEMS_LOOSE and ov >= MIN_OVERLAP_LOOSE
            if is_reliable:
                _append_csv_rows(reliable_path, [summary], USER_SUMMARY_FIELDNAMES)
                already_reliable.add(username)
            if is_community and not is_reliable:
                _append_csv_rows(community_path, [summary], USER_SUMMARY_FIELDNAMES)
                already_community.add(username)

            # Update expansion tag map for committed edges
            for row in merged:
                if row.get("own") == 1 or row.get("own") == "1":
                    gid = row.get("bgg_id")
                    tags = baseline_game_tag_map.get(gid, []) if gid else []
                    for t in tags:
                        if t in target_underrep_tags:
                            expansion_tag_users[t].add(username)

            recent_results.append(1 if is_reliable else 0)
            if len(recent_results) > QUALITY_COLLAPSE_WINDOW:
                recent_results.pop(0)

            enriched_ids.add(username)
            new_enriched_this_run += 1
            cand["enrichment_status"] = "done"

            logger.info("  -> items=%s, owned=%s, rated=%s, overlap=%s, reliable=%s, community=%s",
                        ci, summary["owned_count"], summary["rated_count"], ov, is_reliable, is_community and not is_reliable)

        except Exception as exc:
            logger.exception("  enrichment failed for %s: %s", username, exc)
            _append_csv_rows(errors_path, [{"username": username, "error_message": str(exc),
                                            "ts_utc": datetime.now(timezone.utc).isoformat()}],
                             ["username", "error_message", "ts_utc"])
            failed_summary = build_failed_user_summary({
                "username": username,
                "discovery_count": cand["discovery_count"],
                "rating_comment_count": cand["rating_comment_count"],
                "play_player_count": cand["play_player_count"],
                "source_games": cand.get("source_games") or [],
                "source_game_ranks": cand.get("source_game_ranks") or [],
                "source_types": cand.get("source_types") or [],
            }, error_message=str(exc))
            _append_csv_rows(summaries_path, [failed_summary], USER_SUMMARY_FIELDNAMES)
            enriched_ids.add(username)
            new_enriched_this_run += 1
            cand["enrichment_status"] = "error"
            recent_results.append(0)
            if len(recent_results) > QUALITY_COLLAPSE_WINDOW:
                recent_results.pop(0)

        # Persist state often but not after every user (too chatty)
        if new_enriched_this_run % 10 == 0:
            state["enriched_usernames"] = sorted(enriched_ids)
            state["reliable_usernames"] = sorted(already_reliable)
            state["community_usernames"] = sorted(already_community)
            state["stage"] = "enrichment"
            state["enriched_count"] = len(enriched_ids)
            _save_state(processed_dir, state)

        # Throughput log every 100 enrichments
        if new_enriched_this_run % 100 == 0:
            dt = time.time() - throughput_start_time
            rate = requests_made_this_run / dt if dt > 0 else 0.0
            logger.info("[throughput] %s users / %.1fs = %.2f req/s (%.0f users/hour extrapolated)",
                        requests_made_this_run, dt, rate, rate * 3600)

        # Periodic diversity snapshot + plateau / target-improvement check
        if new_enriched_this_run % SNAPSHOT_EVERY_N_ENRICHED == 0 and new_enriched_this_run > 0:
            snapshot = _compute_diversity_snapshot(
                baseline_tag_users=baseline_target_tag_users,
                expansion_tag_users=expansion_tag_users,
                target_tags=target_underrep_tags,
                enriched_count=new_enriched_this_run,
            )
            snap_path = snapshots_dir / f"snapshot_{new_enriched_this_run:05d}.json"
            snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            logger.info("[snapshot] wrote %s", snap_path)

            # Diversity-based soft stop
            if _should_stop_for_diversity(snapshots_dir, snapshot, logger):
                stop_reason = "diversity_target_met_or_plateau"
                break

    # Final state persist
    state["enriched_usernames"] = sorted(enriched_ids)
    state["reliable_usernames"] = sorted(already_reliable)
    state["community_usernames"] = sorted(already_community)
    state["stage"] = "enrichment"
    state["enriched_count"] = len(enriched_ids)
    _save_state(processed_dir, state)

    logger.info("Enrichment stage done. stop_reason=%s, new_enriched=%s, reliable_added=%s, community_added=%s",
                stop_reason, new_enriched_this_run, len(already_reliable), len(already_community))
    return stop_reason


def _compute_diversity_snapshot(
    *,
    baseline_tag_users: dict[str, set[str]],
    expansion_tag_users: dict[str, set[str]],
    target_tags: set[str],
    enriched_count: int,
) -> dict:
    per_tag = []
    improved = 0
    for tag in sorted(target_tags):
        base = len(baseline_tag_users.get(tag, set()))
        exp = len(expansion_tag_users.get(tag, set()))
        if base > 0:
            gain = exp / base
        else:
            gain = float("inf") if exp > 0 else 0.0
        did_improve = gain >= TARGET_TAG_IMPROVEMENT_FRACTION
        if did_improve:
            improved += 1
        per_tag.append({
            "tag": tag,
            "baseline_committed_users": base,
            "expansion_committed_users": exp,
            "relative_gain": gain if math.isfinite(gain) else None,
            "meets_threshold": did_improve,
        })
    total_targets = len(target_tags) or 1
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "enriched_count": enriched_count,
        "n_target_tags": len(target_tags),
        "n_tags_improved": improved,
        "fraction_tags_improved": improved / total_targets,
        "per_tag": per_tag,
    }


def _should_stop_for_diversity(snap_dir: Path, latest: dict, logger: logging.Logger) -> bool:
    # Stop if we've hit the target-tag improvement goal
    if latest["fraction_tags_improved"] >= TARGET_TAGS_IMPROVED_FRACTION:
        logger.info("[stop] fraction_tags_improved=%.2f >= %.2f",
                    latest["fraction_tags_improved"], TARGET_TAGS_IMPROVED_FRACTION)
        return True
    # Plateau: compare to previous snapshot
    snaps = sorted(snap_dir.glob("snapshot_*.json"))
    if len(snaps) >= 2:
        prev = json.loads(snaps[-2].read_text(encoding="utf-8"))
        gain = latest["fraction_tags_improved"] - prev["fraction_tags_improved"]
        if gain < PLATEAU_RELATIVE_GAIN:
            logger.info("[stop] plateau: fraction_tags_improved delta=%.3f < %.3f", gain, PLATEAU_RELATIVE_GAIN)
            return True
    return False


# -----------------------------------------------------------------------------
# Stage 4: Diversity Evaluation (cohort comparison)
# -----------------------------------------------------------------------------
def run_evaluation(
    *,
    processed_dir: Path,
    baseline_dir: Path,
    selected_game_ids: set[int],
    game_tag_map: dict[int, list[str]],
    target_underrep_tags: set[str],
    stop_reason: str,
    logger: logging.Logger,
) -> None:
    """Three metrics: coverage delta, structural delta, JS divergence on game-ownership distribution."""
    baseline_edges = baseline_dir / "reliable_user_collection_edges.csv"
    baseline_users = baseline_dir / "reliable_users.csv"
    exp_edges = processed_dir / "all_user_collection_edges.csv"
    exp_reliable = processed_dir / "reliable_users.csv"
    exp_community = processed_dir / "community_users.csv"

    # Load user sets
    baseline_user_set = {r["username"] for r in _read_csv_rows(baseline_users)}
    exp_reliable_set = {r["username"] for r in _read_csv_rows(exp_reliable)}
    exp_community_set = {r["username"] for r in _read_csv_rows(exp_community)}
    exp_all_set = exp_reliable_set | exp_community_set

    def _scan(edges_path: Path, user_filter: set[str] | None) -> tuple[dict[int, set[str]], dict[str, set[str]], int, int]:
        per_game_users: dict[int, set[str]] = defaultdict(set)
        per_tag_committed: dict[str, set[str]] = defaultdict(set)
        n_edges = 0
        n_own_edges = 0
        if not edges_path.exists():
            return per_game_users, per_tag_committed, 0, 0
        with edges_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                u = row.get("username") or ""
                if user_filter is not None and u not in user_filter:
                    continue
                try:
                    gid = int(row.get("bgg_id") or 0)
                except ValueError:
                    gid = 0
                if gid == 0 or gid not in selected_game_ids:
                    continue
                n_edges += 1
                own = row.get("own") == "1"
                if own:
                    n_own_edges += 1
                    per_game_users[gid].add(u)
                    for tag in game_tag_map.get(gid, []):
                        per_tag_committed[tag].add(u)
        return per_game_users, per_tag_committed, n_edges, n_own_edges

    logger.info("[evaluation] scanning baseline edges...")
    base_game_users, base_tag_users, base_edges, base_own = _scan(baseline_edges, None)
    logger.info("[evaluation] scanning expansion edges (all pool)...")
    exp_game_users, exp_tag_users, exp_edges_n, exp_own = _scan(exp_edges, exp_all_set)
    logger.info("[evaluation] scanning expansion edges (reliable pool)...")
    rel_game_users, rel_tag_users, rel_edges_n, rel_own = _scan(exp_edges, exp_reliable_set)

    # 1. Taxonomy coverage delta per target tag
    coverage_delta = []
    for tag in sorted(target_underrep_tags):
        base_n = len(base_tag_users.get(tag, set()))
        exp_n = len(exp_tag_users.get(tag, set()))
        rel_n = len(rel_tag_users.get(tag, set()))
        coverage_delta.append({
            "tag": tag,
            "core_committed_users": base_n,
            "expansion_all_committed_users": exp_n,
            "expansion_reliable_committed_users": rel_n,
            "delta_all_pct": (100.0 * exp_n / base_n) if base_n else None,
        })

    # 2. Structural stats
    n_base_users = len(baseline_user_set)
    n_exp_all = len(exp_all_set)
    n_exp_reliable = len(exp_reliable_set)
    n_selected = len(selected_game_ids)
    structural = {
        "core_top69_users": n_base_users,
        "expansion_all_users": n_exp_all,
        "expansion_reliable_users": n_exp_reliable,
        "expansion_community_only_users": n_exp_all - n_exp_reliable,
        "core_own_edges_on_selected": base_own,
        "expansion_all_own_edges_on_selected": exp_own,
        "expansion_reliable_own_edges_on_selected": rel_own,
        "core_avg_owned_per_user": (base_own / n_base_users) if n_base_users else 0,
        "expansion_reliable_avg_owned_per_user": (rel_own / n_exp_reliable) if n_exp_reliable else 0,
        "core_bipartite_own_density_pct": (100.0 * base_own / (n_base_users * n_selected)) if (n_base_users and n_selected) else 0,
        "expansion_reliable_bipartite_own_density_pct": (100.0 * rel_own / (n_exp_reliable * n_selected)) if (n_exp_reliable and n_selected) else 0,
    }

    # 3. JS divergence between aggregate "% of users who own game g" distributions
    def _ownership_dist(game_users: dict[int, set[str]], n_users: int) -> dict[int, float]:
        if n_users == 0:
            return {}
        return {gid: len(us) / n_users for gid, us in game_users.items()}

    p = _ownership_dist(base_game_users, n_base_users)
    q = _ownership_dist(rel_game_users, n_exp_reliable)
    js_div = _js_divergence_over_games(p, q, list(selected_game_ids))

    # Write report
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("DIVERSITY EXPANSION - EVALUATION REPORT")
    lines.append(f"Run label:     {processed_dir.name}")
    lines.append(f"Baseline:      {baseline_dir.name}")
    lines.append(f"Stop reason:   {stop_reason}")
    lines.append(f"Generated:     {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 78)

    lines.append("")
    lines.append("[1] USER COUNTS")
    for k, v in structural.items():
        if isinstance(v, float):
            lines.append(f"  {k:<55} = {v:.3f}")
        else:
            lines.append(f"  {k:<55} = {v}")

    lines.append("")
    lines.append("[2] JS DIVERGENCE (aggregate game-ownership distribution)")
    lines.append(f"  core_top69  vs  expanded_reliable   =  {js_div:.4f}  (0 = identical, 1 = maximally different)")
    lines.append(f"  interpretation: higher = expansion users own structurally different games vs core")

    lines.append("")
    lines.append("[3] TAXONOMY COVERAGE DELTA (target underrepresented tags only)")
    lines.append(f"  target tags = {len(target_underrep_tags)}")
    header = f"  {'tag':<42}  {'core':>6}  {'exp_all':>8}  {'exp_rel':>8}  {'delta_all%':>11}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    coverage_delta.sort(key=lambda r: (-(r["delta_all_pct"] or 0)))
    for r in coverage_delta[:40]:
        tag = r["tag"][:40]
        dlt = f"{r['delta_all_pct']:.1f}%" if r["delta_all_pct"] is not None else "n/a"
        lines.append(f"  {tag:<42}  {r['core_committed_users']:>6}  "
                     f"{r['expansion_all_committed_users']:>8}  {r['expansion_reliable_committed_users']:>8}  {dlt:>11}")

    lines.append("")
    lines.append("[4] INTERPRETATION GUIDE")
    lines.append("  * Large JS divergence (>~0.05) and healthy coverage deltas (>25%) => expansion")
    lines.append("    meaningfully broadens the user pool. Safe to merge as a separate cohort with the")
    lines.append("    core baseline.")
    lines.append("  * Small JS divergence (<~0.02) and mostly-flat coverage deltas => expansion did not")
    lines.append("    add new behavioral regions. Consider adjusting seed selection before merging.")
    lines.append("")
    lines.append("Merging is NOT done automatically. Review this report, then run a separate merge step.")
    lines.append("=" * 78)

    text = "\n".join(lines)
    report_path = processed_dir / "diversity_evaluation_report.txt"
    _write_text(report_path, text)
    print("\n" + text)
    logger.info("Wrote evaluation report -> %s", report_path)


def _js_divergence_over_games(p: dict[int, float], q: dict[int, float], game_ids: list[int]) -> float:
    """Compute Jensen-Shannon divergence between two ownership-frequency distributions.

    p[g] = fraction of core users who own game g
    q[g] = fraction of expansion users who own game g
    Both are treated as distributions over the game universe. We normalize each
    to a probability distribution, then compute JS via KL against the mixture.
    """
    # Build aligned distributions
    p_vals = []
    q_vals = []
    for g in game_ids:
        p_vals.append(p.get(g, 0.0))
        q_vals.append(q.get(g, 0.0))
    p_sum = sum(p_vals)
    q_sum = sum(q_vals)
    if p_sum <= 0 or q_sum <= 0:
        return 0.0
    p_norm = [x / p_sum for x in p_vals]
    q_norm = [x / q_sum for x in q_vals]

    def _kl(a: list[float], b: list[float]) -> float:
        total = 0.0
        for ai, bi in zip(a, b):
            if ai > 0 and bi > 0:
                total += ai * math.log(ai / bi, 2)
        return total

    m = [(pi + qi) / 2 for pi, qi in zip(p_norm, q_norm)]
    return 0.5 * _kl(p_norm, m) + 0.5 * _kl(q_norm, m)


# -----------------------------------------------------------------------------
# Main pipeline orchestration
# -----------------------------------------------------------------------------
def _save_state(processed_dir: Path, state: dict) -> None:
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    path = processed_dir / "pipeline_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_state(processed_dir: Path) -> dict:
    path = processed_dir / "pipeline_state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _load_game_tag_map(details_csv: Path, selected_ids: set[int]) -> dict[int, list[str]]:
    mapping: dict[int, list[str]] = {}
    for row in _read_csv_rows(details_csv):
        gid = _safe_int(row.get("bgg_id"))
        if gid is None or gid not in selected_ids:
            continue
        tags = _split_pipe(row.get("mechanics")) + _split_pipe(row.get("categories"))
        mapping[gid] = tags
    return mapping


def _scan_baseline_committed_tag_users(
    edges_path: Path, selected_ids: set[int], tag_map: dict[int, list[str]]
) -> dict[str, set[str]]:
    """For each tag, the set of baseline users with >=1 own-edge on a selected game carrying that tag."""
    out: dict[str, set[str]] = defaultdict(set)
    if not edges_path.exists():
        return out
    with edges_path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("own") != "1":
                continue
            try:
                gid = int(row.get("bgg_id") or 0)
            except ValueError:
                continue
            if gid == 0 or gid not in selected_ids:
                continue
            u = row.get("username") or ""
            if not u:
                continue
            for t in tag_map.get(gid, []):
                out[t].add(u)
    return out


def _load_target_underrep_tags(mech_csv: Path, cat_csv: Path, top_k: int = 20) -> tuple[set[str], set[str]]:
    def _bottom(rows: list[dict], key: str) -> list[str]:
        filt = [r for r in rows if _safe_int(r.get("n_games_with_tag_in_universe")) and int(r["n_games_with_tag_in_universe"]) >= 5]
        filt.sort(key=lambda r: (_safe_float(r.get("user_coverage_ratio")) or 0.0))
        return [r[key] for r in filt[:top_k]]
    mech = set(_bottom(_read_csv_rows(mech_csv), "mechanic"))
    cat = set(_bottom(_read_csv_rows(cat_csv), "category"))
    return mech, cat


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    setup_logging(settings)
    logger = logging.getLogger("bgg_project.discover_additional_users_b")

    project_root = settings["_meta"]["project_root"]
    raw_root = Path(settings["paths"]["raw_data_dir"])
    if not raw_root.is_absolute():
        raw_root = project_root / raw_root
    proc_root = Path(settings["paths"]["processed_data_dir"])
    if not proc_root.is_absolute():
        proc_root = project_root / proc_root

    raw_dir = raw_root / "reliable_users" / args.run_label
    proc_dir = proc_root / "reliable_users" / args.run_label
    baseline_dir = proc_root / "reliable_users" / args.baseline_run_label
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    # Default coverage CSVs live in baseline_dir
    coverage_mech = Path(args.coverage_mechanics_csv) if args.coverage_mechanics_csv else (baseline_dir / "taxonomy_coverage_mechanics.csv")
    coverage_cat = Path(args.coverage_categories_csv) if args.coverage_categories_csv else (baseline_dir / "taxonomy_coverage_categories.csv")
    details_csv = Path(args.details_csv)
    if not details_csv.is_absolute():
        details_csv = project_root / details_csv

    selected_games_csv = baseline_dir / "selected_games.csv"

    # Sanity checks
    for p in (coverage_mech, coverage_cat, details_csv, selected_games_csv, baseline_dir / "reliable_users.csv"):
        if not p.exists():
            logger.error("Missing prerequisite file: %s", p)
            return 2

    # Record thresholds used
    thresholds = {
        "run_label": args.run_label,
        "cohort_label": COHORT_LABEL,
        "baseline_run_label": args.baseline_run_label,
        "seed_total": SEED_TOTAL,
        "seed_taxonomy_quota": SEED_TAXONOMY_QUOTA,
        "seed_rank_stratified_quota": SEED_RANK_STRATIFIED_QUOTA,
        "seed_contrast_quota": SEED_CONTRAST_QUOTA,
        "rank_bands": RANK_BANDS,
        "rank_band_quotas": RANK_BAND_QUOTAS,
        "contrast_min_owned": CONTRAST_MIN_OWNED,
        "plays_pages_taxonomy": PLAYS_PAGES_TAXONOMY,
        "plays_pages_rank": PLAYS_PAGES_RANK,
        "plays_pages_contrast": PLAYS_PAGES_CONTRAST,
        "ratingcomments_pages": RATINGCOMMENTS_PAGES_ALL,
        "ratingcomments_page_size": RATINGCOMMENTS_PAGE_SIZE,
        "min_request_spacing_seconds": MIN_REQUEST_SPACING_SECONDS,
        "min_collection_items_strict": MIN_COLLECTION_ITEMS_STRICT,
        "min_overlap_strict": MIN_OVERLAP_STRICT,
        "min_collection_items_loose": MIN_COLLECTION_ITEMS_LOOSE,
        "min_overlap_loose": MIN_OVERLAP_LOOSE,
        "max_runtime_hours": args.max_runtime_hours,
        "max_enriched_users": args.max_enriched_users,
        "snapshot_every_n_enriched": SNAPSHOT_EVERY_N_ENRICHED,
        "target_tag_improvement_fraction": TARGET_TAG_IMPROVEMENT_FRACTION,
        "target_tags_improved_fraction": TARGET_TAGS_IMPROVED_FRACTION,
        "plateau_relative_gain": PLATEAU_RELATIVE_GAIN,
        "quality_collapse_window": QUALITY_COLLAPSE_WINDOW,
        "quality_collapse_min_rate": QUALITY_COLLAPSE_MIN_RATE,
    }
    _write_text(proc_dir / "selection_thresholds.json", json.dumps(thresholds, indent=2, default=str))

    # Load state
    state = _load_state(proc_dir)
    logger.info("Loaded pipeline state: stage=%s, enriched_count=%s",
                state.get("stage", "not_started"), state.get("enriched_count", 0))

    # Stage 1: seed selection (always idempotent)
    rng = random.Random(args.seed_random)
    seed_path = proc_dir / "seed_games.csv"
    seeds = run_seed_selection(
        details_csv=details_csv,
        coverage_mech_csv=coverage_mech,
        coverage_cat_csv=coverage_cat,
        out_path=seed_path,
        rng=rng,
        logger=logger,
    )
    logger.info("Seeds ready: %s", len(seeds))

    if args.dry_run:
        logger.info("--dry-run specified; exiting before Stage 2 (no API calls).")
        return 0

    # Build API client
    token = get_api_token(settings)
    client = BGGClient(
        base_url=settings["api"]["base_url"],
        token=token,
        use_environment_proxies=False,
        timeout_seconds=settings["api"]["request_timeout_seconds"],
        min_seconds_between_requests=max(settings["api"]["min_seconds_between_requests"], MIN_REQUEST_SPACING_SECONDS),
        max_retries=settings["api"]["max_retries"],
        retry_backoff_seconds=settings["api"]["retry_backoff_seconds"],
        logger=logger,
    )

    # Stage 2: discovery
    run_discovery(client, seeds, raw_dir=raw_dir, processed_dir=proc_dir, state=state, logger=logger)

    # Prepare baseline structures needed for scoring + evaluation
    baseline_usernames: set[str] = {r["username"] for r in _read_csv_rows(baseline_dir / "reliable_users.csv")}
    logger.info("Baseline reliable users: %s (will skip these during enrichment)", len(baseline_usernames))

    selected_ids: set[int] = set()
    for r in _read_csv_rows(selected_games_csv):
        gid = _safe_int(r.get("bgg_id"))
        if gid is not None:
            selected_ids.add(gid)

    game_tag_map = _load_game_tag_map(details_csv, selected_ids)
    target_mech, target_cat = _load_target_underrep_tags(coverage_mech, coverage_cat, top_k=20)
    target_underrep_tags = target_mech | target_cat
    logger.info("Target underrepresented tags: %s mechanics + %s categories = %s total",
                len(target_mech), len(target_cat), len(target_underrep_tags))

    # Baseline per-tag committed users (for before/after comparison)
    logger.info("Scanning baseline edges for per-tag committed users (this takes a minute)...")
    baseline_target_tag_users = _scan_baseline_committed_tag_users(
        baseline_dir / "reliable_user_collection_edges.csv", selected_ids, game_tag_map,
    )
    logger.info("Baseline per-tag snapshot: %s tags covered", len(baseline_target_tag_users))

    # Aggregate candidates from discovery rows
    rating_rows = _read_csv_rows(proc_dir / "all_discovery_rating_comment_rows.csv")
    play_rows = _read_csv_rows(proc_dir / "all_discovery_play_rows.csv")
    logger.info("Discovery rows loaded: rating=%s, play=%s", len(rating_rows), len(play_rows))

    candidates = aggregate_and_score_candidates(
        rating_rows, play_rows,
        underrep_tag_set=target_underrep_tags,
        baseline_usernames=baseline_usernames,
        logger=logger,
    )

    # Persist candidate list (for inspection)
    _append_csv_rows  # no-op, keep import linter happy
    cand_path = proc_dir / "candidate_users.csv"
    with cand_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CANDIDATE_FIELDS, extrasaction="ignore")
        w.writeheader()
        for c in candidates:
            row = {k: c.get(k) for k in CANDIDATE_FIELDS}
            for k in ("source_games", "source_game_ranks", "source_types", "source_seed_types", "source_underrep_tags"):
                v = row.get(k)
                if isinstance(v, list):
                    row[k] = " | ".join(str(x) for x in v)
            w.writerow(row)
    logger.info("Wrote candidates -> %s", cand_path)

    # Stage 3: enrichment
    stop_reason = run_enrichment(
        client, candidates,
        selected_game_ids=selected_ids,
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        state=state,
        max_runtime_hours=args.max_runtime_hours,
        max_enriched_users=args.max_enriched_users,
        baseline_game_tag_map=game_tag_map,
        target_underrep_tags=target_underrep_tags,
        baseline_target_tag_users=baseline_target_tag_users,
        logger=logger,
    )

    _write_text(proc_dir / "SCRIPT_STOPPED_REASON.txt",
                f"stop_reason: {stop_reason}\n"
                f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}\n")

    # Stage 4: evaluation
    run_evaluation(
        processed_dir=proc_dir,
        baseline_dir=baseline_dir,
        selected_game_ids=selected_ids,
        game_tag_map=game_tag_map,
        target_underrep_tags=target_underrep_tags,
        stop_reason=stop_reason,
        logger=logger,
    )

    state["stage"] = "evaluation_complete"
    state["stop_reason"] = stop_reason
    _save_state(proc_dir, state)

    logger.info("All stages complete. Review diversity_evaluation_report.txt before merging with baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
