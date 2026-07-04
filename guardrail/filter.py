import re


def _tokenize(prompt: str) -> list:
    # same normalization as the original tokenization(): lowercase + split on
    # non-word runs, so "Hack!" and "hack" match the same banned-list entry.
    normalized = prompt.strip().casefold()
    return [item for item in re.split(r'(\W+)', normalized) if item.strip()]


def local_filter(prompt: str) -> bool:
    """Return True if prompt is safe (no banned word found), False if flagged."""
    tokens = _tokenize(prompt)
    with open("banned.txt", "r") as file:
        banned_list = file.read().split()
    for word in tokens:
        if word in banned_list:
            return False
    return True
