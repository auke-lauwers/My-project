"""Names -> candidate email local parts, and learning a company's pattern back from a known address."""

import re
import unicodedata

# Ordered by how common they are in B2B mailboxes
PATTERNS = [
    "{first}.{last}",
    "{first}",
    "{f}{last}",
    "{first}{last}",
    "{f}.{last}",
    "{first}_{last}",
    "{first}{l}",
    "{last}",
    "{last}.{first}",
    "{first}-{last}",
    "{last}{f}",
    "{first}.{l}",
    "{last}{first}",
    "{f}{l}",
]

# Surname particles (Dutch, German, French, ...) that companies sometimes drop
PARTICLES = {"van", "de", "der", "den", "het", "ten", "ter", "te", "von", "zu", "du", "des",
             "la", "le", "da", "di", "del", "dos", "das", "op", "in", "t", "'t", "vd"}


def ascii_slug(text: str) -> str:
    """'Jérôme Ørsted-Smit' -> 'jeromeorstedsmit'."""
    text = text.replace("ø", "o").replace("Ø", "O").replace("æ", "ae").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def split_full_name(full: str) -> tuple[str, str]:
    full = re.sub(r"\(.*?\)", "", full).split(",")[0].strip()
    words = full.split()
    if not words:
        return "", ""
    return words[0], " ".join(words[1:])


def last_name_variants(last: str) -> list[str]:
    """'van der Berg' -> ['vanderberg', 'berg']; 'Smith-Jones' -> ['smithjones', 'smith', 'jones']."""
    words = [w for w in re.split(r"\s+", last.strip()) if w]
    variants = [ascii_slug(last)]
    core = [w for w in words if w.lower() not in PARTICLES]
    if core and len(core) < len(words):
        variants.append(ascii_slug(" ".join(core)))
    for part in last.split("-"):
        if "-" in last:
            variants.append(ascii_slug(part.split()[-1] if part.split() else part))
    return [v for i, v in enumerate(variants) if v and v not in variants[:i]]


def render(pattern: str, first: str, last: str) -> str:
    return pattern.format(first=first, last=last, f=first[:1], l=last[:1])


def candidates(first_name: str, last_name: str, preferred: str | None = None) -> list[tuple[str, str]]:
    """[(local_part, pattern), ...] most likely first. `preferred` is a pattern known for this domain."""
    first = ascii_slug(first_name.split()[0] if first_name.split() else first_name)
    lasts = last_name_variants(last_name) if last_name else []
    out: list[tuple[str, str]] = []
    patterns = ([preferred] if preferred else []) + [p for p in PATTERNS if p != preferred]
    for pattern in patterns:
        needs_last = "{last}" in pattern or "{l}" in pattern
        if needs_last and not lasts:
            continue
        for last in (lasts if needs_last else [""]):
            local = render(pattern, first, last)
            if first and local and local not in (c[0] for c in out):
                out.append((local, pattern))
    return out


def infer_pattern(email: str, first_name: str, last_name: str) -> str | None:
    """Which pattern turns this person's name into this address? None if no pattern fits."""
    local = email.split("@")[0].lower()
    for cand, pattern in candidates(first_name, last_name):
        if cand == local:
            return pattern
    return None


def guess_shape(local: str) -> str | None:
    """Pattern from an address alone, when no name is known: 'jane.doe' -> '{first}.{last}'."""
    if re.fullmatch(r"[a-z]{2,}\.[a-z]{2,}", local):
        return "{first}.{last}"
    if re.fullmatch(r"[a-z]\.[a-z]{2,}", local):
        return "{f}.{last}"
    if re.fullmatch(r"[a-z]{2,}_[a-z]{2,}", local):
        return "{first}_{last}"
    if re.fullmatch(r"[a-z]{2,}-[a-z]{2,}", local):
        return "{first}-{last}"
    return None
