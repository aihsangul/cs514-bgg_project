#!/usr/bin/env python3
"""Add manual interpretation columns to the CS514 community summary table."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_RUN_LABEL = "merged_ownership_newman_disparity_a0p025_r1p75"


COMMUNITY_SEEDS: dict[int, dict[str, str]] = {
    0: {
        "manual_label": "Historical wargames + economic strategy",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Most self-contained specialist group; strong wargame/simulation/CRT enrichment.",
    },
    2: {
        "manual_label": "Current heavy euro engine builders",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Modern heavy euros; income, worker placement, industry/manufacturing.",
    },
    5: {
        "manual_label": "Cooperative trick-taking + deduction",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Meaningful but low closure; The Crew-style games appear across many shelves.",
    },
    7: {
        "manual_label": "BGG Golden Age canon",
        "community_type": "temporal_canon",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Temporal/generational community around classic hobby canon, not only abstract/auction mechanics.",
    },
    8: {
        "manual_label": "Dungeon crawl / cooperative campaign adventure",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Cooperative, campaign, role-playing, fantasy/adventure.",
    },
    9: {
        "manual_label": "Medium worker-placement euros",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Rosenberg-era/medium euros; farming, Renaissance, worker placement.",
    },
    11: {
        "manual_label": "Unmatched / skirmish series cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Structurally coherent franchise/fandom cluster rather than broad taste identity.",
    },
    12: {
        "manual_label": "Puzzle / nature tableau builders",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Pattern-building, animals, puzzle/nature games; lower closure because audience is broad.",
    },
    13: {
        "manual_label": "Recent releases / undifferentiated new-hotness",
        "community_type": "temporal_artifact",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Likely temporal co-purchase artifact around recent releases; avoid as stable taste dimension.",
    },
    15: {
        "manual_label": "Amerithrash / miniatures / LCG",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Fighting, miniatures, collectible components, variable powers.",
    },
    28: {
        "manual_label": "Legacy + narrative mystery",
        "community_type": "shared_culture",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "high",
        "manual_notes": "Coherent but very cross-community; may be shared hobby heritage rather than specialist taste.",
    },
    35: {
        "manual_label": "Print-and-play solo microgames",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Small but strongly enriched specialist cluster.",
    },
    36: {
        "manual_label": "Family / children's games",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Children's, dexterity, memory/family signal.",
    },
    39: {
        "manual_label": "Social deduction and party games",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Hidden roles, voting, party, traitor games; broad audience, lower closure.",
    },
}


MIDLINE_R1P75_COMMUNITY_SEEDS: dict[int, dict[str, str]] = {
    10: {
        "manual_label": "BGG Golden Age canon",
        "community_type": "temporal_canon",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Classic hobby canon centered on Puerto Rico, Power Grid, Agricola, El Grande, Ra, and Tigris & Euphrates; strongest internal closure in the midline graph.",
    },
    9: {
        "manual_label": "Amerithrash / miniatures / LCG",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Thematic conflict, miniatures, variable powers, dice, and collectible/card-system signal.",
    },
    12: {
        "manual_label": "Dungeon crawl / cooperative campaign adventure",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Modern cooperative/campaign adventure cluster around Gloomhaven, Spirit Island, Arkham Horror LCG, Nemesis, and related games.",
    },
    19: {
        "manual_label": "Recent releases / new-hotness cluster",
        "community_type": "temporal_artifact",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Median year 2023 and mixed mechanics; likely temporal co-purchase signal rather than stable taste identity.",
    },
    2: {
        "manual_label": "Current heavy euro engine builders",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Modern heavy euros with strong worker-placement, income, variable setup, and industry/manufacturing signal.",
    },
    20: {
        "manual_label": "Historical wargames + conflict strategy",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Most self-contained specialist group after the Golden Age canon; strong wargame, simulation, CDG, CRT, political, and historical signal.",
    },
    25: {
        "manual_label": "Party / family / social deduction",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Party, hidden roles, deduction, children's/family, memory, and real-time signal; broad cross-community appeal.",
    },
    13: {
        "manual_label": "Puzzle / nature tableau builders",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Cascadia/Wingspan-adjacent puzzle, pattern-building, animal/nature, set-collection cluster with broad appeal.",
    },
    8: {
        "manual_label": "Medium worker-placement euros",
        "community_type": "taste_specialist",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Rosenberg-era and medium-heavy eurogames around Great Western Trail, Terra Mystica, Orleans, Caverna, Tzolk'in, and Le Havre.",
    },
    35: {
        "manual_label": "Cooperative trick-taking + deduction",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "The Crew, Decrypto, The Mind, Search for Planet X, Blood on the Clocktower, Crokinole, and adjacent social/deduction titles.",
    },
    23: {
        "manual_label": "Fantasy adventure / deck-building gateway",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Everdell, Clank!, Roll Player, Tiny Epic, and adventure/fantasy gateway games; low internal closure, likely bridge-oriented.",
    },
    5: {
        "manual_label": "Area-control crossover / Root-Eclipse cluster",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Root, Eclipse, Inis, Res Arcana, War Chest, and related hybrid conflict/area-control titles; likely bridge cluster across strategy audiences.",
    },
    17: {
        "manual_label": "Roll-and-write / number dice games",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "medium",
        "manual_notes": "That's Pretty Clever, Qwixx, Taverns of Tiefenthal, Port Royal, and dice/number/paper-and-pencil signal.",
    },
    4: {
        "manual_label": "Legacy + narrative mystery",
        "community_type": "shared_culture",
        "include_in_user_profiles": "yes",
        "manual_meaningfulness": "high",
        "manual_notes": "Pandemic Legacy, EXIT/Unlock-style mystery, and narrative/legacy signal; coherent but cross-community.",
    },
    16: {
        "manual_label": "Unmatched / skirmish series cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Very coherent Unmatched/franchise ownership cluster; useful structurally but not a broad taste dimension.",
    },
    38: {
        "manual_label": "Racing / sports / route bridge",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Flamme Rouge, Baseball Highlights, K2, Thunder Alley, and route/family titles; small low-closure bridge cluster.",
    },
    36: {
        "manual_label": "Light set-collection gateway",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Splendor, Century, Photosynthesis, and light set-collection/tableau games; likely broad gateway bridge.",
    },
    37: {
        "manual_label": "Escape-room / Unlock series cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Unlock/Codenames escape-room/storytelling cluster; strong series signal but small.",
    },
    39: {
        "manual_label": "Take-that card/fandom cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Love Letter, Smash Up, Evolution, and take-that/fandom card games; partly series-driven.",
    },
    26: {
        "manual_label": "Pandemic system cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Pandemic variants and related cooperative system games; coherent franchise/system ownership cluster.",
    },
    34: {
        "manual_label": "Licensed family/fandom games",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Wingspan with Disney Villainous/Lorcana and licensed/fandom family titles; mixed bridge/franchise signal.",
    },
    29: {
        "manual_label": "Small two-player/set-collection card games",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Jaipur, Morels, Dale of Merchants, Valley of the Kings, and small card/set-collection titles.",
    },
    32: {
        "manual_label": "Open-drafting tactical euro cluster",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Five Tribes, Abyss, Quadropolis, Yamatai, and related drafting/tactical euros; small bridge-like cluster.",
    },
    41: {
        "manual_label": "Ticket to Ride / route-building series cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Ticket to Ride maps and route-building variants; franchise/system cluster.",
    },
    31: {
        "manual_label": "Railroad Ink / spatial puzzle cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Railroad Ink variants plus Patchwork; small series/spatial-puzzle cluster.",
    },
    0: {
        "manual_label": "Terraforming Mars universal-appeal micro-cluster",
        "community_type": "bridge_singleton",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Terraforming Mars is too broadly owned to sit cleanly in one taste community; treat as universal-appeal bridge/micro-cluster.",
    },
    1: {
        "manual_label": "Thematic adventure / licensed bridge cluster",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Lost Ruins of Arnak plus Star Wars/licensed adventure titles; mixed gateway/bridge signal.",
    },
    3: {
        "manual_label": "Thematic sandbox worker-placement bridge",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Scythe, Western Legends, Euphoria, and thematic sandbox/worker-placement titles; bridge-like rather than broad taste axis.",
    },
    11: {
        "manual_label": "KeyForge / Catan gateway-franchise cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Mixed small cluster dominated by KeyForge system ownership plus gateway editions such as Catan.",
    },
    14: {
        "manual_label": "Abstract tile-placement puzzle bridge",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Azul, Ginkgopolis, Dragon Castle, Cat Lady; coherent but small aesthetically driven abstract/tile-placement cluster.",
    },
    15: {
        "manual_label": "Deck-manipulation / engine gateway cluster",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Dominion, Imhotep, Eminent Domain, Core Worlds; small deck/engine gateway cluster.",
    },
    18: {
        "manual_label": "Mass-market gateway / family strategy bridge",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Ticket to Ride, Pan Am, Freedom, Back to the Future; accessible family strategy bridge cluster.",
    },
    21: {
        "manual_label": "Viticulture / Dinosaur Island gateway bridge",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Viticulture plus Dinosaur Island family; small gateway/publisher-adjacent bridge cluster.",
    },
    22: {
        "manual_label": "Trade-route / area-influence euros",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Concordia, Ethnos, Lords of Vegas, Caylus 1303; recognizable but too small for a profile dimension.",
    },
    24: {
        "manual_label": "Ark Nova universal-appeal micro-cluster",
        "community_type": "bridge_singleton",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Ark Nova appears in a tiny cluster rather than the nature/tableau community, suggesting broad cross-audience ownership.",
    },
    27: {
        "manual_label": "Race for the Galaxy system cluster",
        "community_type": "franchise_series",
        "include_in_user_profiles": "no",
        "manual_meaningfulness": "medium",
        "manual_notes": "Race for the Galaxy, New Frontiers, Jump Drive, and related card-engine titles; system/franchise-like cluster.",
    },
    28: {
        "manual_label": "Real-time cooperative micro-cluster",
        "community_type": "taste_cross_over",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Just One, Kitchen Rush, Rush M.D., and real-time/action-timer games; strong enrichment but very small.",
    },
    40: {
        "manual_label": "Light gateway tile/claim-action cluster",
        "community_type": "bridge_cluster",
        "include_in_user_profiles": "review",
        "manual_meaningfulness": "medium",
        "manual_notes": "Kingdomino, Queendomino, Downforce, World's Fair 1893; small light gateway cluster.",
    },
}


COMMUNITY_SEEDS_BY_RUN_LABEL: dict[str, dict[int, dict[str, str]]] = {
    "merged_ownership_newman_disparity_a0p025_r2p0": COMMUNITY_SEEDS,
    "merged_ownership_newman_disparity_a0p025_r1p75": MIDLINE_R1P75_COMMUNITY_SEEDS,
}


MANUAL_COLUMNS = [
    "manual_label",
    "community_type",
    "include_in_user_profiles",
    "manual_meaningfulness",
    "manual_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", default=DEFAULT_RUN_LABEL)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--overwrite-seeds",
        action="store_true",
        help="Overwrite existing manual columns when a curated seed exists for the community.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    base = root / "data" / "processed" / "cs514_network_analysis" / "metadata"
    in_path = args.input or base / f"{args.run_label}_community_interpretation_summary.csv"
    out_path = args.output or in_path

    summary = pd.read_csv(in_path)
    community_seeds = COMMUNITY_SEEDS_BY_RUN_LABEL.get(args.run_label, COMMUNITY_SEEDS)
    for col in MANUAL_COLUMNS:
        if col not in summary.columns:
            summary[col] = ""
        summary[col] = summary[col].fillna("").astype(str)

    for idx, row in summary.iterrows():
        cid = int(row["community"])
        seed = community_seeds.get(cid)
        if seed is None:
            if row["rough_meaningfulness_flag"] == "tiny_fragment":
                seed = {
                    "community_type": "tiny_fragment",
                    "include_in_user_profiles": "no",
                    "manual_meaningfulness": "low",
                }
            else:
                seed = {
                    "community_type": "review",
                    "include_in_user_profiles": "review",
                    "manual_meaningfulness": "review",
                }

        for col, value in seed.items():
            if args.overwrite_seeds or not summary.at[idx, col]:
                summary.at[idx, col] = value

    front = [
        "community",
        "size",
        "manual_label",
        "community_type",
        "include_in_user_profiles",
        "manual_meaningfulness",
        "manual_notes",
    ]
    ordered_cols = front + [c for c in summary.columns if c not in front]
    summary = summary[ordered_cols]
    summary.to_csv(out_path, index=False)

    mapping_path = out_path.with_name(out_path.name.replace("_community_interpretation_summary.csv", "_community_manual_mapping.csv"))
    summary[front + ["rough_meaningfulness_flag"]].to_csv(mapping_path, index=False)
    print(f"wrote {out_path}")
    print(f"wrote {mapping_path}")
    print(summary[front].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
