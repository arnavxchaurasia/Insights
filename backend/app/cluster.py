import re
import uuid

# Stop words tailored for Indian financial and economic news headlines.
_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "above",
        "across",
        "after",
        "again",
        "against",
        "all",
        "almost",
        "along",
        "already",
        "also",
        "although",
        "always",
        "am",
        "amid",
        "among",
        "an",
        "and",
        "another",
        "any",
        "are",
        "aren't",
        "around",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "between",
        "both",
        "but",
        "by",
        "can",
        "can't",
        "cannot",
        "cent",
        "could",
        "did",
        "do",
        "does",
        "down",
        "due",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "get",
        "got",
        "had",
        "has",
        "have",
        "he",
        "held",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "isn't",
        "it",
        "its",
        "just",
        "keep",
        "keeps",
        "latest",
        "may",
        "me",
        "meeting",
        "might",
        "more",
        "most",
        "much",
        "must",
        "my",
        "no",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "own",
        "per",
        "re",
        "said",
        "says",
        "see",
        "set",
        "shall",
        "she",
        "should",
        "since",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "upon",
        "us",
        "very",
        "via",
        "was",
        "wasn't",
        "we",
        "were",
        "weren't",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "within",
        "without",
        "won't",
        "would",
        "you",
        "your",
    }
)

_PUNCT_SPLIT = re.compile(r"[^\w\s%]+")
_NUMERIC_CANONICAL = re.compile(r"(\d+)\s*(?:points|pts|pt)", re.I)

# Threshold justification:
# A Jaccard similarity threshold of 0.50 on informative headline tokens requires that
# at least half of the combined distinct vocabulary between two headlines matches.
# Cross-publisher articles covering the exact same event typically share numbers, company/regulator
# names, and key action verbs (e.g. "Sensex plunges 800 pts" vs "Sensex crashes 800 points"),
# yielding token overlap >= 0.50. Meanwhile, different articles in the same sector (e.g.,
# "HDFC Bank quarterly profit rises" vs "SBI reports record net profit") typically score below 0.35.
DEFAULT_SIMILARITY_THRESHOLD: float = 0.50


def normalize_title_tokens(title: str) -> set[str]:
    """Extract a normalized set of informative tokens from a headline."""
    if not title:
        return set()

    cleaned = title.lower()
    # Normalize "per cent" to "%"
    cleaned = re.sub(r"\bper\s+cent\b", "%", cleaned)
    # Remove commas inside numbers (e.g. 24,000 -> 24000)
    cleaned = re.sub(r"(\d+),(\d+)", r"\1\2", cleaned)
    # Standardize common headline variations like '800 pts' -> '800pts'
    cleaned = _NUMERIC_CANONICAL.sub(r"\1pts", cleaned)
    # Replace non-alphanumeric characters except % and decimal points between digits
    cleaned = re.sub(r"(?<!\d)\.|\.(?!\d)|[^\w\s%.]+", " ", cleaned)
    words = cleaned.split()

    tokens = {w for w in words if len(w) > 1 and w not in _STOP_WORDS}
    return tokens


def token_set_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Calculate token-set similarity between two sets of tokens.

    Combines Sørensen-Dice coefficient with subset containment to reliably group both
    equal-length rewrites and concise vs verbose headline variants.
    """
    if not tokens_a or not tokens_b:
        return 1.0 if tokens_a == tokens_b else 0.0

    intersection = len(tokens_a & tokens_b)
    if intersection == 0:
        return 0.0

    # Sørensen-Dice coefficient: 2 * |A ∩ B| / (|A| + |B|)
    dice = (2.0 * intersection) / (len(tokens_a) + len(tokens_b))

    # Overlap / containment handles cases where one headline is a concise subset of another
    min_len = min(len(tokens_a), len(tokens_b))
    containment = intersection / min_len if min_len > 0 else 0.0

    return max(dice, containment)


def find_matching_cluster(
    title: str,
    recent_articles: list[tuple[str, str]],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> str | None:
    """Find an existing cluster for a title among recent (cluster_id, title) tuples.

    Returns the cluster_id of the highest-scoring candidate if its similarity
    is greater than or equal to `threshold`, otherwise None.
    """
    tokens = normalize_title_tokens(title)
    if not tokens:
        return None

    best_cluster_id: str | None = None
    best_score = 0.0

    for cluster_id, candidate_title in recent_articles:
        if not cluster_id or not candidate_title:
            continue
        candidate_tokens = normalize_title_tokens(candidate_title)
        score = token_set_similarity(tokens, candidate_tokens)
        if score >= threshold and score > best_score:
            best_score = score
            best_cluster_id = cluster_id

    return best_cluster_id


def assign_cluster_id(
    title: str,
    recent_articles: list[tuple[str, str]],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> str:
    """Assign a cluster_id to a title: either reuse an existing cluster or generate a new UUID."""
    matching = find_matching_cluster(title, recent_articles, threshold)
    if matching:
        return matching
    return uuid.uuid4().hex
