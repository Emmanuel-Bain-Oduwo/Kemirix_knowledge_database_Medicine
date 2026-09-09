"""Conservative identity normalization for KMX name lookups.

Deliberately minimal: Unicode NFKC folding, case folding and whitespace
collapsing only. Everything else — strength, concentration, dose form,
release type, route, stereochemistry, salts, isomers, combination
ingredients and ALL punctuation — is treated as identity-bearing and is
never stripped, rewritten or collapsed. A name that does not match exactly
after this normalization is NOT the same identity; it is a mapping-exception
candidate for human review, never an LLM or similarity guess.
"""

import unicodedata


def normalize_name(text):
    """NFKC-fold, case-fold and whitespace-collapse one identity name."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("identity name must be a non-empty string")
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(folded.split())
