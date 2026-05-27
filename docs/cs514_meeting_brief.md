# CS514 Network Science Project Meeting Brief

Last updated: 2026-05-04

## 1. Project Overview

This project studies the BoardGameGeek ecosystem through behavioral network structure. The central question is:

> Among engaged BGG users and the top-ranked game universe, how do behavioral game communities derived from co-ownership align with, diverge from, or extend official metadata classifications such as mechanics and categories?

The project began as a data collection and graph construction effort and has now moved into validated network analysis. The main analytical object is a game-game co-ownership network. Games are represented as nodes, and edges represent statistically meaningful shared ownership patterns among users.

Official game metadata is not used to construct the behavioral network. Instead, mechanics, categories, designers, publication year, BGG rank, and manual labels are used after community detection to interpret and validate the discovered structure.

The current interpretation is:

> BGG metadata describes what games are. Co-ownership reveals what role games play in collections.

## 2. Dataset Construction

The project uses a dense engaged-user sample built from BoardGameGeek data.

Game-level data:

- detailed metadata was collected for the top 5,000 ranked BGG games;
- the primary network analysis uses the top 2,500 selected games as graph nodes;
- game metadata includes rank, year, ratings, weight, mechanics, categories, designers, publishers, and collection-related signals.

Baseline user data:

- the initial reliable-user dataset contains 5,175 users;
- users were discovered through interactions with high-ranked games;
- candidate discovery used BGG rating comments and play logs;
- full user collections were then fetched using the BGG collection XML endpoint;
- reliable users were selected using minimum collection and selected-game-overlap thresholds.

Baseline caveat:

- the initial user pool was discovered from high-visibility top-ranked games;
- this produced a dense and useful engaged-user sample, but with a mainstream hobbyist bias.

Diversity expansion:

- a second isolated sweep was implemented to target underrepresented BGG communities;
- weakly represented mechanics and categories were identified from taxonomy coverage diagnostics;
- expansion seeds included taxonomy-deficit games, rank-stratified games, and wishlist-ratio contrast games;
- candidate users were again discovered from rating comments and play logs;
- user collections were fetched once per user using `collection?stats=1`;
- the expansion produced 478 strict reliable users;
- 28 out of 30 target underrepresented tags improved by at least 20%.

Current dataset characterization:

- the dataset is not a neutral sample of all BGG users;
- it is best described as a dense engaged-user dataset with targeted correction for previously underrepresented communities;
- this framing is important for the final report and poster.

## 3. Network Construction Method

The primary network is game-centric.

Pipeline:

1. A user-game ownership bipartite graph was constructed.
2. The bipartite graph was projected into a game-game co-ownership network.
3. A Newman-style user-normalized projection was used.
4. The dense projected graph was pruned using a disparity backbone filter.
5. Communities were detected using modularity-based community detection.
6. Metadata enrichment, stability checks, and null-model tests were used for validation.

The Newman-style projection reduces heavy-collector dominance. A user with `d` selected owned games contributes `1 / (d - 1)` to each induced game pair. This prevents users with very large collections from overwhelming the projection simply by creating many pairwise co-ownership links.

The disparity backbone filter removes weak edges from the dense projection using a local statistical criterion. Instead of applying one global edge-weight threshold, the filter asks whether an edge is unusually strong relative to the distribution of edge weights around each endpoint.

This combination was selected because the raw game-game projection is too dense to interpret directly.

## 4. Parameter Tuning and Validation

Two main parameters were tuned:

- `alpha`: the strictness of the disparity backbone filter;
- `gamma`: the community-detection resolution parameter.

Lower `alpha` values retain fewer edges and create cleaner but sparser graphs. Higher `alpha` values retain more edges and support finer community structure, but risk keeping weak or noisy co-ownership relationships.

Lower `gamma` values produce fewer, larger communities. Higher `gamma` values produce more, smaller communities.

The final parameter selection was based on two validation gates:

1. **Stability gate:** community assignments had to be reproducible across random seeds, measured by median pairwise NMI.
2. **Null-model gate:** observed modularity had to exceed the modularity expected under degree-preserving randomized graphs.

The selected main graph is:

- projection: ownership-only Newman projection;
- backbone: disparity filter with `alpha = 0.025`;
- community resolution: `gamma = 1.75`;
- nodes: 2,500 games;
- edges: 214,379;
- communities: 43;
- largest community: 13.5% of games;
- median pairwise NMI: approximately 0.758;
- observed modularity: approximately 0.077;
- null mean modularity: approximately 0.068;
- z-score: approximately 27.31.

This setting became the main validated graph because it preserved interpretability while passing both the stability and null-model checks.

Three analytical tiers are currently retained:

| Tier | Parameters | Role |
|---|---:|---|
| Macro graph | `alpha = 0.001`, `gamma = 0.75` | broad statistically strong structure |
| Validated midline graph | `alpha = 0.025`, `gamma = 1.75` | main result |
| Fine descriptive graph | `alpha = 0.025`, `gamma = 2.0` | exploratory detail only |

The fine graph was stable and interpretable, but it did not pass the modularity null-model check. It is therefore treated as descriptive rather than as the basis for the strongest statistical claims.

## 5. Main Community Findings

The validated midline graph produced interpretable communities that cannot be reduced to simple BGG metadata categories.

The main community types include:

- taste-specialist communities;
- hobby-era communities;
- cross-over or supplementary communities;
- bridge-game clusters;
- franchise or series clusters;
- recent-release temporal clusters.

Important examples:

- **Historical wargames + conflict strategy:** a highly coherent specialist community, including games such as `Twilight Struggle`, `War of the Ring`, `Paths of Glory`, `Labyrinth`, and `Combat Commander`.
- **BGG Golden Age canon:** an older hobby-era community centered on influential titles such as `Puerto Rico`, `Agricola`, `Power Grid`, `Ra`, `El Grande`, and `Tigris & Euphrates`.
- **Current heavy euro engine builders:** a modern heavy euro cluster including games such as `Gaia Project`, `A Feast for Odin`, `Barrage`, `Kanban EV`, `On Mars`, and `Underwater Cities`.
- **Dungeon crawl / cooperative campaign adventure:** a campaign and cooperative community including `Gloomhaven`, `Spirit Island`, `Frosthaven`, `Arkham Horror LCG`, and `Too Many Bones`.
- **Party / family / social deduction:** a broad cross-over community including `The Resistance`, `Secret Hitler`, `Dixit`, `Sushi Go Party!`, `Deception`, and `Telestrations`.

The community structure suggests that co-ownership captures not only genre similarity, but also era, audience identity, collection function, and market timing.

### Validated-Midline Community Labels

The table below summarizes the main interpreted communities from the validated `alpha = 0.025`, `gamma = 1.75` graph.

| ID | Community | Type | Interpretation | Example games |
|---:|---|---|---|---|
| 10 | BGG Golden Age canon | temporal_canon | Classic hobby-defining games, especially older euros and strategy games owned by long-tenure BGG collectors. | Puerto Rico, Agricola, Power Grid, El Grande, Ra, Tigris & Euphrates, Caylus, Hansa Teutonica |
| 9 | Amerithrash / miniatures / LCG | taste_specialist | Thematic conflict, miniatures, variable powers, sci-fi/fantasy, and living/collectible card game audience. | Twilight Imperium 4, Star Wars: Rebellion, Mage Knight, Blood Rage, Android: Netrunner, Mansions of Madness |
| 12 | Dungeon crawl / cooperative campaign adventure | taste_specialist | Modern campaign/cooperative adventure games, often solo-friendly or scenario-driven. | Gloomhaven, Spirit Island, Frosthaven, Arkham Horror LCG, Too Many Bones, Sleeping Gods |
| 19 | Recent releases / new-hotness cluster | temporal_artifact | Recent games co-owned because they are currently popular, not because they share one stable taste identity. | Dune: Imperium Uprising, Sky Team, Heat, Harmonies, Arcs, SCOUT, Wyrmspan |
| 2 | Current heavy euro engine builders | taste_specialist | Modern complex euros with engine-building, worker placement, resource systems, and heavier strategic planning. | Gaia Project, SETI, A Feast for Odin, Barrage, Kanban EV, Underwater Cities, On Mars |
| 20 | Historical wargames + conflict strategy | taste_specialist | Wargame/economic-conflict audience; one of the cleanest identity communities. | War of the Ring, Twilight Struggle, Brass: Lancashire, Pax Pamir 2E, Dominant Species, Undaunted: Normandy, Memoir '44 |
| 25 | Party / family / social deduction | taste_cross_over | Social, party, gateway, and group-play games; widely owned across many user types. | The Resistance: Avalon, Secret Hitler, Sushi Go Party!, Deception, Dixit, Telestrations, Captain Sonar |
| 13 | Puzzle / nature tableau builders | taste_cross_over | Accessible tableau, pattern, nature, and puzzle-like games; often broad-appeal additions to collections. | Cascadia, PARKS, Cartographers, Isle of Cats, Earth, Meadow, Sagrada |
| 8 | Medium worker-placement euros | taste_specialist | Earlier/midweight eurogame cluster, especially 2010s worker-placement and resource-management games. | Great Western Trail, Terra Mystica, Orleans, Caverna, Tzolk'in, Le Havre, Keyflower, Troyes |
| 35 | Cooperative trick-taking + deduction | taste_cross_over | Social deduction, trick-taking, word/deduction, and social filler games that cross many communities. | The Crew: Mission Deep Sea, Blood on the Clocktower, Decrypto, The Search for Planet X, Codenames: Duet, Monikers |
| 23 | Fantasy adventure / deck-building gateway | taste_cross_over | Gateway-friendly fantasy/adventure and deck-building games; coherent but currently marked review for profile use. | Everdell, Clank!, Clank! In! Space!, Champions of Midgard, Roll Player, Above and Below, Mystic Vale |
| 5 | Area-control crossover / Root-Eclipse cluster | bridge_cluster | Area-control / conflict games that bridge euro, thematic, and strategy audiences. | Eclipse: Second Dawn, Root, Inis, Tyrants of the Underdark, War Chest, Res Arcana, Ankh, Kemet |
| 17 | Roll-and-write / number dice games | taste_cross_over | Roll-and-write, number, dice, and lighter tactical games; more supplementary than identity-defining. | That's Pretty Clever!, Twice as Clever!, Clever Cubed, Qwixx, Trails of Tucana, The Taverns of Tiefenthal |
| 4 | Legacy + narrative mystery | shared_culture | Legacy, campaign, mystery, and narrative puzzle games; widely recognized shared hobby experiences. | Pandemic Legacy S1, Clank! Legacy, Ticket to Ride Legacy, Pandemic Legacy S0/S2, My City, EXIT games, Betrayal Legacy |

## 6. Centrality and Bridge-Game Analysis

A later network-science diagnostic was added to formalize the previously manual interpretation of bridge games.

Centrality measures were computed on the validated `alpha = 0.025`, `gamma = 1.75` backbone:

- degree: number of significant co-ownership neighbors;
- strength: total weighted co-ownership connection strength;
- approximate weighted betweenness: frequency with which a game lies on shortest paths between other games, using `distance = 1 / weight`.

Betweenness centrality is especially important because it formalizes the idea of a bridge game. A high-betweenness game connects otherwise separate areas of the network.

The top approximate betweenness games include:

| Game | BGG Rank | Community | Interpretation |
|---|---:|---:|---|
| `7 Wonders Duel` | 24 | C33 | broad two-player bridge / tiny fragment |
| `Azul` | 96 | C14 | abstract tile-placement bridge |
| `Carcassonne` | 239 | C38 | gateway / route-family bridge |
| `Terraforming Mars` | 9 | C0 | universal-appeal micro-cluster |
| `Codenames` | 161 | C37 | broad social/deduction bridge |
| `Wingspan` | 38 | C34 | licensed family/fandom crossover |
| `Pandemic` | 170 | C26 | Pandemic system / shared-culture bridge |
| `Twilight Struggle` | 14 | C20 | wargame identity anchor with bridging role |
| `Brass: Birmingham` | 1 | C7 | universal-appeal bridge-like fragment |
| `Ark Nova` | 2 | C24 | universal-appeal micro-cluster |

This analysis strengthens the earlier community interpretation in two ways.

First, several manually identified bridge or universal-appeal games also appear as high-betweenness nodes. This gives a formal network basis for the claim that games such as `Terraforming Mars`, `Brass: Birmingham`, `Ark Nova`, `Wingspan`, and `Pandemic` do not function simply as members of one genre community.

Second, the result explains why some top-ranked games do not land cleanly in their expected taste communities. For example, `Brass: Birmingham`, `Ark Nova`, and `Terraforming Mars` are often understood as heavy or strategic euro-style games, but behaviorally they are owned across many collector types. Their network role is therefore closer to a cultural touchstone or bridge than to a narrow specialist-community marker.

The centrality result supports the broader thesis:

> Some games become so widely adopted that popularity reduces community specificity. These games may define the public image of a genre while failing to identify the specialist audience of that genre.

## 7. Network Topology Diagnostics

The validated backbone was also characterized structurally.

Key topology values:

- nodes: 2,500;
- edges: 214,379;
- density: 0.0686;
- average degree: 171.5;
- median degree: 94;
- maximum degree: 2,486;
- connected components: 1;
- isolates: 0;
- average unweighted clustering: 0.783;
- expected clustering under same-density random graph: 0.069;
- average shortest path length on the connected graph: 1.93.

The graph is dense and connected, but it also has very high local clustering relative to a simple random graph baseline. This supports the presence of tightly grouped local taste neighborhoods inside a broadly connected hobby ecosystem.

This topology result also helps explain the visual structure seen in Gephi: the graph appears as a large connected mass rather than isolated islands, but colored community regions still appear because dense local clustering remains inside the global connected structure.

## 8. Metadata Alignment at the Edge Level

A multi-label edge-similarity diagnostic was added to estimate how strongly behavioral edges align with BGG mechanics and categories.

Because games can have multiple mechanics and categories, a simple single-label assortativity coefficient is not ideal. Instead, observed co-ownership edges were compared to random game pairs using Jaccard similarity over mechanics and categories.

Results from a 100,000-pair comparison:

| Measure | Observed Edges | Random Pairs | Lift |
|---|---:|---:|---:|
| mean mechanic Jaccard | 0.091 | 0.065 | 1.40x |
| mean category Jaccard | 0.098 | 0.059 | 1.67x |

This shows that behavioral co-ownership edges are more metadata-similar than random pairs. Metadata therefore does predict part of the behavioral structure.

However, the lift is moderate rather than overwhelming. This supports the main interpretation: behavioral structure partially aligns with metadata, but also captures additional phenomena such as hobby era, universal bridge games, franchise collecting, and recent-release trends.

## 9. Community-Level Condensation Graph

A community condensation graph was also constructed. In this graph:

- each node is one detected game community;
- each edge represents total backbone weight between two communities.

This produces a 43-node meta-network of taste-community adjacency.

The strongest inter-community ties include:

- medium worker-placement euros with BGG Golden Age canon;
- current heavy euros with recent releases;
- Amerithrash / miniatures / LCG with BGG Golden Age canon;
- BGG Golden Age canon with party / family / social deduction;
- BGG Golden Age canon with historical wargames;
- current heavy euros with medium worker-placement euros;
- Amerithrash / miniatures / LCG with dungeon crawl / cooperative campaign adventure.

This result connects the community detection analysis to a higher-level network structure. It shows not only which games cluster together, but also which taste communities are behaviorally adjacent.

## 10. User Archetype Extension

After game communities were labeled, user profiles were built by measuring each user's owned games across accepted community dimensions.

Only users with at least 15 selected owned games were included in the archetype analysis.

Key results:

- eligible users: 5,125;
- other-dominant users: 3,221, or 62.8%;
- generalists: 723, or 14.1%;
- leaning users: 634, or 12.4%;
- specialists: 524, or 10.2%.

The high other-dominant share initially appears problematic, but decomposition shows that the `other` bucket is meaningful rather than empty noise.

Sources of `other` ownership among other-dominant users:

- recent-release temporal artifact cluster: 36.1%;
- bridge clusters: 27.8%;
- franchise / series clusters: 17.8%;
- review-level taste-crossover clusters: 7.9%;
- tiny fragments: 7.2%;
- universal-appeal bridge singletons: 3.2%.

This suggests that a large share of engaged BGG collection behavior is organized around recent popularity cycles, cross-community games, and franchise systems rather than stable single-genre specialization.

## 11. Current Interpretive Claims

The main findings can be summarized as follows.

### Claim 1: Behavioral communities are not equivalent to metadata categories.

Mechanics and categories help explain the communities, but co-ownership also reveals structures not encoded directly in BGG taxonomy.

### Claim 2: Some communities function as identity anchors.

Historical wargames, BGG Golden Age canon, heavy euros, dungeon crawl/campaign games, and Amerithrash-style games form stronger identity communities.

### Claim 3: Some communities function as supplementary layers.

Party games, trick-taking games, roll-and-write games, puzzle/nature games, and legacy/narrative games are widely owned but rarely define an entire collection identity.

### Claim 4: Some games function as bridges rather than community members.

High-betweenness games and universal-appeal micro-clusters show that some highly ranked games are behaviorally important because they connect audiences.

### Claim 5: Recent-release behavior is a major structural signal.

The new-hotness cluster and the other-dominant user profiles suggest that current BGG engagement is partly organized around temporal trend-following.

## 12. Crucial Findings Ranked by Impact

The findings below provide the most effective "things found out" narrative for a professor-facing discussion or final poster/report.

### Finding 1: Metadata Partly Explains Behavior, But Does Not Determine It

This is the most direct answer to the research question.

Behavioral backbone edges are more metadata-similar than random game pairs:

- mechanic Jaccard lift: approximately 1.40x;
- category Jaccard lift: approximately 1.67x;
- shared-mechanic lift: approximately 1.31x;
- shared-category lift: approximately 1.52x.

This means BGG metadata has real explanatory power. Games connected by behavior are more likely to share mechanics and categories than random pairs of games.

However, the lift is moderate rather than overwhelming. If metadata fully determined ownership behavior, the lift would be much larger. If metadata were irrelevant, the lift would be close to 1.0.

The gap between random behavior and full metadata determination is where the main contribution of the project sits. Bridge singletons, temporal artifacts, franchise clusters, community types, and the other-dominant user decomposition explain what structures behavior beyond official taxonomy.

Concise framing:

> Behavioral edges are 1.4-1.7x more metadata-similar than random game pairs. That is real signal, but not overwhelming signal. The rest of the analysis explains what structures behavior beyond taxonomy.

### Finding 2: The Backbone Is A Dense, Highly Clustered Small World

Before communities are interpreted, the backbone itself has an important structural profile.

Key values:

- nodes: 2,500;
- edges: 214,379;
- average degree: 171.5;
- median degree: 94;
- connected components: 1;
- diameter: 2;
- average shortest path length: 1.93;
- average clustering: 0.783;
- same-density Erdos-Renyi clustering expectation: 0.069.

This means the graph is not a sparse network with isolated taste islands. It is a dense, globally connected small world where every game is at most two hops from every other game. The important fact is that local clustering is still about 11x higher than a same-density random graph.

The disparity filter therefore did not create isolated clusters from nothing. It identified locally significant edges inside an already highly overlapping co-ownership space.

Concise framing:

> The engaged BGG ownership network is a near-complete small world: diameter 2, average path 1.93, and clustering about 11x higher than random at the same density. The hobby is broadly overlapping, but local taste neighborhoods are still unusually clustered.

### Finding 3: Betweenness Centrality Formalizes Bridge Games

Manual bridge labels were later checked using formal centrality measures. Betweenness centrality gives a structural definition of bridge games: games that lie on shortest paths between other parts of the graph.

The structural-analysis betweenness table ranks the top bridge-like games as:

| Rank | Game | BGG Rank | Community | Betweenness | Interpretation |
|---:|---|---:|---:|---:|---|
| 1 | Terraforming Mars | 9 | C0 | 0.230 | universal-appeal micro-cluster |
| 2 | 7 Wonders Duel | 24 | C33 | 0.190 | broad two-player bridge |
| 3 | Azul | 96 | C14 | 0.172 | abstract gateway bridge |
| 4 | Carcassonne | 239 | C38 | 0.165 | gateway / route-family bridge |
| 5 | Wingspan | 38 | C34 | 0.145 | family/fandom crossover |
| 6 | Codenames | 161 | C37 | 0.132 | social/deduction bridge |
| 7 | Twilight Struggle | 14 | C20 | 0.090 | specialist wargame bridge |
| 8 | Pandemic | 170 | C26 | 0.080 | shared-culture / system bridge |
| 9 | Ark Nova | 2 | C24 | 0.069 | universal-appeal micro-cluster |
| 11 | Brass: Birmingham | 1 | C7 | 0.048 | universal-appeal fragment |

The important point is that betweenness and BGG rank diverge. The highest-ranked game is not the most structurally central connector. `Twilight Struggle` is especially informative: it has much lower degree than the broad gateway bridges, but it has high betweenness because it sits at a specific junction between the wargame community and the broader hobby.

Concise framing:

> Betweenness centrality tells a different story from BGG rank. Structural bridges are not simply the highest-ranked games. They are games that connect otherwise different ownership regions.

### Finding 4: Extreme Popularity Can Erase Community Specificity

`Brass: Birmingham`, `Ark Nova`, and `Terraforming Mars` are among the highest-ranked games on BGG, but they do not behave as clean members of one taste community in the validated network.

Instead, they appear in universal-appeal or tiny bridge-like fragments. This is not necessarily a classification error. It is a behavioral result: these games are owned across many collector types, so they do not have a strong enough preferential association with one specific community.

This creates a bridge-singleton paradox:

> A game can become so broadly owned that it stops identifying one taste group.

The implication is that popularity and community specificity can diverge at the extreme. Highly ranked games may represent the public face of a genre while failing to identify the specialist audience of that genre.

Concise framing:

> The highest-ranked games can become structurally ambiguous. Extreme popularity makes a game less useful as a taste-community marker because it is owned by everyone.

### Finding 5: Recent Releases Form A Temporal Artifact Community

Community C19 is a large recent-release cluster:

- size: 231 games;
- median year: 2023;
- examples: `Dune: Imperium Uprising`, `Sky Team`, `Heat`, `Harmonies`, `Arcs`, `SCOUT`, `Wyrmspan`.

The games in this community do not share one stable genre identity. Instead, they share timing and attention. They are recent games that engaged BGG users were acquiring during the same period.

This is a finding about BGG culture rather than only game similarity. The behavioral network captures the new-hotness cycle, which official mechanics/categories do not directly encode.

Concise framing:

> One of the largest communities is not a taste community. It is a temporal artifact: recent, high-attention games that engaged users acquired at the same time.

### Finding 6: Community Type Is A Conceptual Contribution

The project does not only label communities by mechanics. It classifies why each community exists.

The current functional taxonomy includes:

| Community type | Meaning |
|---|---|
| `taste_specialist` | coherent behavioral identity, such as wargames, heavy euros, dungeon crawl |
| `taste_cross_over` | real but permeable taste community, such as party/social or puzzle/nature |
| `temporal_canon` | older hobby-era community, such as BGG Golden Age canon |
| `temporal_artifact` | recency-driven cluster, such as the new-hotness community |
| `franchise_series` | publisher/system loyalty, such as Pandemic, Unmatched, Ticket to Ride |
| `bridge_cluster` | games that sit between communities without forming a narrow taste identity |
| `bridge_singleton` | individual universal-appeal games that escape ordinary community structure |

This functional classification answers the research question more completely than a simple list of clusters. Co-ownership is structured, but not only by game type. It is also structured by era, recency, franchise loyalty, and universal appeal.

Concise framing:

> The original result was not just 43 communities. The more important result is a behavioral taxonomy explaining why communities exist.

### Finding 7: Historical Wargames Are The Cleanest Identity Community

The historical wargame community is the clearest validation case for the framework.

It shows:

- low broad reach compared with most other profile dimensions;
- high internal weight share;
- clear specialist users;
- deep niche ownership among specialists;
- strong semantic coherence through wargame and conflict-strategy metadata.

This community behaves like an identity community. Fewer users enter it, but those who do tend to go deep.

Examples include `Twilight Struggle`, `War of the Ring`, `Paths of Glory`, `Labyrinth`, `Combat Commander`, `Hannibal`, `Maria`, and `Wilderness War`.

Concise framing:

> Wargamers are the validation case. The network finds them as a distinct, internally coherent, niche-reaching ownership community, which matches domain intuition about the hobby.

### Finding 8: Other-Dominant Users Are Not A Failure Case

The user archetype analysis initially produced a surprising result:

- 62.8% of eligible users were classified as `other_dominant`.

At first, this could look like a failure of the profile system. The decomposition shows otherwise.

The `other` ownership among other-dominant users is mostly:

- 36.1% recent-release temporal artifact ownership;
- 27.8% bridge-cluster ownership;
- 17.8% franchise/series ownership.

So `other_dominant` users are not an uninterpretable remainder. They represent trend followers, cross-genre collectors, franchise completionists, and users whose collections are dominated by universal-appeal games.

Concise framing:

> The other-dominant bucket is not empty noise. It decomposes into three meaningful behavioral modes: new-hotness trend following, bridge-game collecting, and franchise completionism.

## 13. Limitations

Several limitations remain important.

First, the dataset is an engaged-user sample rather than a representative sample of all BGG users.

Second, the diversity expansion improved targeted taxonomy coverage but also introduced users with heavier average engagement. This makes the expansion valuable, but not equivalent to a clean randomized sampling intervention.

Third, high-ranked universal games can be difficult to classify into taste dimensions. `Brass: Birmingham`, `Ark Nova`, and `Terraforming Mars` are especially important examples. Their placement in bridge-like or micro-cluster regions should be interpreted as behavioral ambiguity, not as a failure to recognize their genre.

Fourth, the fine `gamma = 2.0` graph is useful for examples and exploratory interpretation, but the strongest statistical claims should rely on the validated `gamma = 1.75` graph.

Fifth, user archetypes depend on manual decisions about which communities are included as taste dimensions and which are assigned to the `other` bucket.

## 14. Current Status

The project currently has:

- a completed dataset construction story;
- a documented diversity-expansion methodology;
- a validated game-game co-ownership network;
- parameter-sweep evidence for the selected graph setting;
- null-model validation;
- community labels and enrichment interpretation;
- user archetype analysis;
- centrality analysis formalizing bridge games;
- topology characterization;
- metadata edge-similarity diagnostics;
- community condensation graph outputs;
- Gephi-ready graph files and notebook-generated figures.

The analysis is now in a mature reporting stage. The main remaining work is deciding which results should be foregrounded in the final poster/report and which should remain supporting material.

## 15. Candidate Final Poster Framing

The strongest poster framing is:

> Behavioral co-ownership networks reveal how games function in BGG collections. Some games anchor specialist identities, some supplement many identities, some bridge otherwise separate communities, and some reflect temporal trend-following.

The most important poster results are likely:

1. the validated midline community graph;
2. the community interpretation table;
3. the centrality / bridge-game result;
4. the topology and metadata-alignment diagnostics;
5. the user archetype decomposition as an extension.

The cleanest headline finding is:

> Official metadata and behavioral function overlap, but they are not the same. The strongest divergences occur for universal-appeal games, recent-release trends, and franchise systems.

## 16. Repository Evidence Map

The table below maps the main claims in this brief to the files where the corresponding analysis, data, or figure resides.

| Brief section | Claim or analysis | Primary repo locations |
|---|---|---|
| 1. Project Overview | Overall project narrative and running record of decisions/findings | `docs/cs514_analysis_log.md`; `docs/cs514_results_and_poster_plan.md`; `docs/cs514_meeting_brief.md` |
| 2. Dataset Construction | Top-ranked game details and selected game universe | `data/processed/top_ranked_games_details/top_ranked_games_details_top5000_ranked_only/top_ranked_games_details.csv`; `data/processed/cs514_network_analysis/incidence/merged_ownership_games.csv`; `notebooks/cs514_data_collection_walkthrough.ipynb` |
| 2. Dataset Construction | Baseline reliable-user dataset | `data/processed/reliable_users/reliable_users_batch1/reliable_users.csv`; `data/processed/reliable_users/reliable_users_batch1/reliable_user_collection_edges.csv`; `data/processed/reliable_users/reliable_users_batch1/dataset_quality_report.txt`; `scripts/collect_reliable_users.py`; `scripts/analyze_reliable_users_dataset.py` |
| 2. Dataset Construction | Taxonomy coverage diagnosis and underrepresented tags | `data/processed/reliable_users/reliable_users_batch1/taxonomy_coverage_report.txt`; `scripts/analyze_taxonomy_coverage.py`; `notebooks/cs514_bgg_eda.ipynb` |
| 2. Dataset Construction | Diversity expansion sweep and effect | `scripts/discover_additional_users_a.py`; `data/processed/reliable_users/diversity_expansion_batch1/diversity_evaluation_report.txt`; `data/processed/reliable_users/diversity_expansion_batch1/SCRIPT_STOPPED_REASON.txt`; `data/processed/reliable_users/diversity_expansion_batch1/reliable_users.csv`; `notebooks/cs514_data_collection_walkthrough.ipynb` |
| 3. Network Construction Method | Incidence matrices for ownership, positive interest, and did-not-retain layers | `data/processed/cs514_network_analysis/incidence/merged_ownership.npz`; `data/processed/cs514_network_analysis/incidence/merged_positive_interest.npz`; `data/processed/cs514_network_analysis/incidence/merged_did_not_retain.npz`; `scripts/cs514_build_incidence.py` |
| 3. Network Construction Method | Newman/user-normalized projection and disparity backbones | `scripts/cs514_build_backbones.py`; `src/bgg_project/cs514/projection.py`; `data/processed/cs514_network_analysis/backbones/merged_ownership_newman_disparity_a0p025_edges.csv`; `data/processed/cs514_network_analysis/diagnostics/backbone_diagnostics.csv` |
| 3. Network Construction Method | Main Gephi graph for validated midline structure | `data/processed/cs514_network_analysis/gephi/merged_ownership_newman_disparity_a0p025_r1p75_communities.gexf` |
| 4. Parameter Tuning and Validation | Initial alpha/gamma sweep | `scripts/cs514_parameter_sweep.py`; `data/processed/cs514_network_analysis/diagnostics/parameter_sweep.csv`; `data/processed/cs514_network_analysis/diagnostics/parameter_sweep_confirm_20seeds.csv`; `notebooks/cs514_parameter_refinement_walkthrough.ipynb` |
| 4. Parameter Tuning and Validation | Targeted gamma/null-model sweep at `alpha = 0.025` | `scripts/cs514_midline_gamma_null_sweep.py`; `data/processed/cs514_network_analysis/diagnostics/merged_ownership_newman_disparity_a0p025_midline_gamma_null_sweep.csv`; `data/processed/cs514_network_analysis/diagnostics/merged_ownership_newman_disparity_a0p025_midline_gamma_null_replicates.csv`; `data/processed/cs514_network_analysis/figures/parameter_refinement/midline_gamma_sweep_validation.png` |
| 4. Parameter Tuning and Validation | Null-model validation of selected graph | `scripts/cs514_null_model.py`; `src/bgg_project/cs514/null_model.py`; `data/processed/cs514_network_analysis/diagnostics/merged_ownership_newman_disparity_a0p025_midline_gamma_null_sweep.csv`; `notebooks/cs514_parameter_refinement_walkthrough.ipynb` |
| 5. Main Community Findings | Validated `alpha = 0.025`, `gamma = 1.75` community assignments | `data/processed/cs514_network_analysis/communities/merged_ownership_newman_disparity_a0p025_r1p75_communities.csv`; `data/processed/cs514_network_analysis/communities/merged_ownership_newman_disparity_a0p025_r1p75_community_runs.csv`; `scripts/cs514_detect_communities.py` |
| 5. Main Community Findings | Community enrichment and interpretation summary | `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r1p75_community_tag_enrichment.csv`; `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r1p75_tag_modularity.csv`; `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r1p75_community_interpretation_summary.csv`; `notebooks/cs514_community_interpretation.ipynb` |
| 5. Validated-Midline Community Labels | Manual labels, types, inclusion decisions, and notes | `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r1p75_community_manual_mapping.csv`; `data/processed/cs514_network_analysis/metadata/_r1p75_summary_for_labeling.csv`; `scripts/cs514_add_manual_community_columns.py` |
| 6. Centrality and Bridge-Game Analysis | Degree, strength, betweenness, and formal bridge-score tables | `notebooks/cs514_missing_network_analyses.ipynb`; `notebooks/cs514_network_findings.ipynb`; `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/centrality_scores.csv`; `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/top_betweenness_games.csv`; `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/bridge_score_table.csv` |
| 6. Centrality and Bridge-Game Analysis | Bridge-game figures | `data/processed/cs514_network_analysis/figures/missing_network_analyses/centrality_top_betweenness.png`; `data/processed/cs514_network_analysis/figures/missing_network_analyses/rank_vs_betweenness.png`; `data/processed/cs514_network_analysis/figures/poster_ready_network_findings/top_bridge_score_games.png` |
| 7. Network Topology Diagnostics | Degree distribution, clustering, density, path length, connectedness, and diameter | `notebooks/cs514_missing_network_analyses.ipynb`; `notebooks/cs514_structural_network_analyses.ipynb`; `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/network_topology_summary.csv`; `data/processed/cs514_network_analysis/structural_analysis/network_topology_alpha0p025_gamma1p75.csv`; `data/processed/cs514_network_analysis/figures/missing_network_analyses/degree_distribution.png` |
| 8. Metadata Alignment at the Edge Level | Observed-edge vs random-pair mechanic/category Jaccard lift | `notebooks/cs514_missing_network_analyses.ipynb`; `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/metadata_edge_similarity_summary.csv`; `data/processed/cs514_network_analysis/structural_analysis/metadata_alignment_proxy.csv`; `data/processed/cs514_network_analysis/structural_analysis/edge_metadata_overlap.csv` |
| 9. Community-Level Condensation Graph | 43-node community meta-network, where nodes are communities and edges are inter-community backbone weights | `notebooks/cs514_missing_network_analyses.ipynb`; `notebooks/cs514_network_findings.ipynb`; `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/community_condensation_nodes.csv`; `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/community_condensation_edges.csv`; `data/processed/cs514_network_analysis/figures/missing_network_analyses/community_condensation_graph.png` |
| 9. Community-Level Condensation Graph | Poster-ready strongest community-community links | `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/top_community_adjacencies.csv`; `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/community_exposure_table.csv`; `data/processed/cs514_network_analysis/figures/poster_ready_network_findings/top_community_adjacencies.png` |
| 10. User Archetype Extension | User profile dimensions and user archetype assignments | `scripts/cs514_build_user_profiles.py`; `scripts/cs514_analyze_user_archetypes.py`; `notebooks/cs514_user_archetype_analysis.ipynb`; `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_user_profiles.csv`; `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_user_archetypes.csv` |
| 10. User Archetype Extension | Other-dominant decomposition and archetype summaries | `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_other_dominant_decomposition.csv`; `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_summary.csv`; `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_dimension_summary.csv`; `data/processed/cs514_network_analysis/figures/user_archetype_family_counts.png`; `data/processed/cs514_network_analysis/figures/other_dominant_by_community_type.png` |
| 11. Current Interpretive Claims | Consolidated evidence table for poster/report claims | `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/poster_evidence_table.csv`; `notebooks/cs514_network_findings.ipynb`; `docs/cs514_results_and_poster_plan.md` |
| 12. Crucial Findings Ranked by Impact | Ranked narrative: metadata alignment, topology, betweenness, bridge singleton paradox, temporal artifact, community type taxonomy, wargames, other-dominant decomposition | `data/processed/cs514_network_analysis/structural_analysis/metadata_alignment_proxy.csv`; `data/processed/cs514_network_analysis/structural_analysis/network_topology_alpha0p025_gamma1p75.csv`; `data/processed/cs514_network_analysis/structural_analysis/game_centrality_alpha0p025_gamma1p75.csv`; `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r1p75_community_manual_mapping.csv`; `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_other_dominant_decomposition.csv`; `notebooks/cs514_network_findings.ipynb`; `notebooks/cs514_user_archetype_analysis.ipynb` |
| 13. Limitations | Sampling caveats, expansion caveats, and analysis decisions | `docs/cs514_analysis_log.md`; `notebooks/cs514_bgg_eda.ipynb`; `data/processed/reliable_users/reliable_users_batch1/dataset_quality_report.txt`; `data/processed/reliable_users/diversity_expansion_batch1/diversity_evaluation_report.txt` |
| 14. Current Status | Complete running record of completed work | `docs/cs514_analysis_log.md` |
| 15. Candidate Final Poster Framing | Poster framing and design guidance | `docs/cs514_results_and_poster_plan.md`; `docs/Poster_Design_Guidelines.pdf`; `data/processed/cs514_network_analysis/figures/parameter_refinement/`; `data/processed/cs514_network_analysis/figures/missing_network_analyses/`; `data/processed/cs514_network_analysis/figures/poster_ready_network_findings/` |
