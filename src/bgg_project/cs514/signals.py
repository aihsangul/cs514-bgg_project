"""Signal column definitions and per-row masking."""
from __future__ import annotations

import pandas as pd

# Maps signal name → tuple of raw edge-CSV column names that constitute it.
SIGNAL_SPECS: dict[str, tuple[str, ...]] = {
    "ownership": ("own",),
    "positive_interest": ("own", "wishlist", "want", "wanttoplay", "wanttobuy"),
    "did_not_retain": ("prevowned", "fortrade"),
}


def signal_mask(frame: pd.DataFrame, signal: str) -> pd.Series:
    """Return a boolean Series: True where any column for *signal* equals 1."""
    cols = SIGNAL_SPECS[signal]
    mask = pd.Series(False, index=frame.index)
    for col in cols:
        if col not in frame:
            raise KeyError(f"Missing edge-status column {col!r}")
        mask = mask | (pd.to_numeric(frame[col], errors="coerce").fillna(0).astype(int) == 1)
    return mask


def split_pipe(value: object) -> list[str]:
    """Split a pipe-delimited string into a list of stripped tokens."""
    if pd.isna(value) or value is None:
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]
