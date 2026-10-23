"""Readable crystal names derived only from public publisher content."""

import html
import re

# These are article framing, not part of the compound's name.
TITLE_PREFIX = re.compile(
    r"^(?:(?:the |a )?(?:crystal|molecular) structure(?: determination)? of |"
    r"synthesis and (?:crystal )structure of |redetermination of (?:the )?(?:crystal structure of )?)",
    re.IGNORECASE,
)
GENERIC = re.compile(
    r"^(?:(?:the )?(?:title |target )?compound(?:\s+.*)?|"
    r"(?:complex|structure|product|polymorph|form)\s+[\w()\-]+|"
    r"\(?[IVXivx\d]+[a-z]?\)?|not (?:identified|specified)|unknown)$"
)


def clean(value):
    return (
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", value or "")))
        .replace("\u00ad", "")
        .strip()
    )


def crystal_name(entry):
    """Return a display label and its source; never consult CSD metadata or CIFs.

    A multi-structure paper's title is not assigned to every crystal. Short labels
    stay labels; a missing name falls back to the public refcode.
    """
    label = clean(entry["extraction"].get("compound_label"))
    if label and not GENERIC.fullmatch(label) and len(label) > 3:
        return label, "Publisher compound name / label."
    paper = entry["paper"]
    if paper["provenance"].get("collection") == "Acta E":
        title = TITLE_PREFIX.sub("", clean(paper["title"])).strip(" .")
        # Acta E titles often *are* the chemical name. Exclude titles describing
        # a group of structures or a general study instead of one substance.
        broad = re.search(
            r"\b(?:structures|compounds|derivatives|studies|study|comparison|series|"
            r"three|four|five|six|seven|eight|nine|ten)\b|"
            r"^(?:synthesis|structural|supramolecular|investigation|crystallographic)\b",
            title,
            re.IGNORECASE,
        )
        if title and not broad:
            return title, "Molecule name from the publisher article title."
    if label:
        if re.fullmatch(r"\(?[IVXivx\d]+[a-z]?\)?", label):
            label = "Compound " + label
        return label, "Publisher compound label; full molecule name not identified."
    return "Crystal " + entry[
        "id"
    ], "Molecule name not identified in the imported publisher extraction."
