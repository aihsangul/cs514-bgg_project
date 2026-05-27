# Compatibility shim — re-exports everything from the cs514 sub-package.
# New code should import directly from bgg_project.cs514.<module>.
from bgg_project.cs514.cohort import balance_summary, build_nn_matcher, draw_matched_subsample, draw_random_subsample
from bgg_project.cs514.community import detect_louvain
from bgg_project.cs514.data_io import edge_paths_for, load_games, load_users, user_names_for
from bgg_project.cs514.graph_io import (
    attach_communities,
    graph_diagnostics,
    graph_from_matrix,
    read_graph_csv,
    write_gexf,
    write_graph_edges,
    write_json,
)
from bgg_project.cs514.incidence import (
    build_incidence,
    compute_edge_overlap,
    incidence_diagnostics,
    load_incidence,
    save_incidence,
)
from bgg_project.cs514.metadata import binary_tag_modularity, community_tag_enrichment, tag_sets
from bgg_project.cs514.null_model import degree_preserving_null_modularity
from bgg_project.cs514.paths import ProjectPaths, ensure_dirs
from bgg_project.cs514.projection import (
    cosine_projection,
    disparity_backbone,
    matrix_to_edges,
    newman_projection,
)
from bgg_project.cs514.signals import SIGNAL_SPECS, signal_mask, split_pipe

__all__ = [
    "SIGNAL_SPECS",
    "ProjectPaths",
    "attach_communities",
    "balance_summary",
    "binary_tag_modularity",
    "build_incidence",
    "build_nn_matcher",
    "community_tag_enrichment",
    "compute_edge_overlap",
    "cosine_projection",
    "degree_preserving_null_modularity",
    "detect_louvain",
    "disparity_backbone",
    "draw_matched_subsample",
    "draw_random_subsample",
    "edge_paths_for",
    "ensure_dirs",
    "graph_diagnostics",
    "graph_from_matrix",
    "incidence_diagnostics",
    "load_games",
    "load_incidence",
    "load_users",
    "matrix_to_edges",
    "newman_projection",
    "read_graph_csv",
    "save_incidence",
    "signal_mask",
    "split_pipe",
    "tag_sets",
    "user_names_for",
    "write_gexf",
    "write_graph_edges",
    "write_json",
]
