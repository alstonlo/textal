import datetime
import pathlib
import sys

from dotenv import load_dotenv

# CCDC_LICENSING_CONFIGURATION and CSD_DATA_DIRECTORY, which ccdc reads when it is imported.
load_dotenv()

import polars as pl
from ccdc.io import EntryReader
from jsonargparse import auto_cli
from tqdm import tqdm

from dataset.paths import DATA_DIR


# The CSD solubility platform raises from a destructor we have no control over.
def unraisablehook(unraisable):
    exc = unraisable.exc_value
    if isinstance(exc, RuntimeError) and ("Solubility Platform" in str(exc)):
        return
    sys.__unraisablehook__(unraisable)


sys.unraisablehook = unraisablehook


# A spec maps an output field to either a dotted path into the CCDC object, or a
# (path, subspec) pair. A subspec wrapped in a list reads a sequence of objects.
JOURNAL = {
    f: f
    for f in (
        "name",
        "full_name",
        "abbreviated_name",
        "translated_name",
        "abbreviated_translated_name",
        "international_coden",
        "issn",
        "eissn",
        "publisher_name",
        "language_name",
        "start_year",
        "end_year",
        "state",
        "url",
        "image_url",
    )
}

CITATION = {
    "authors": "authors",
    "journal": ("journal", JOURNAL),
    "volume": "volume",
    "year": "year",
    "first_page": "first_page",
    "doi": "doi",
    "title": "title",
}

CROSS_REFERENCE = {
    "text": "text",
    "scope": "scope",
    "type": "type",
    "identifiers": "identifiers",
}

INCHI = {
    "inchi": "inchi",
    "key": "key",
}

SOLVENT = {
    "name": "0",
    "percentage": "1",
}

SOLUBILITY = {
    "solubility_min": "solubility.min",
    "solubility_max": "solubility.max",
    "solubility_text": "solubility",
    "solubility_unit": "solubility_unit",
    "temperature": "temperature",
    "temperature_unit": "temperature_unit",
    "notes": "notes",
    "solvents": ("solvents", [SOLVENT]),
}

NESTED = {
    "component_inchis": [INCHI],
    "cross_references": [CROSS_REFERENCE],
    "publication": CITATION,
    "publications": [CITATION],
    "solubility_data": [SOLUBILITY],
}

FIELDS = (
    "identifier",
    "analogue",
    "bioactivity",
    "calculated_density",
    "ccdc_number",
    "chemical_name",
    "chemical_name_as_html",
    "color",
    "component_inchis",
    "cross_references",
    "database_name",
    "deposition_date",
    "disorder_details",
    "fcf_source",
    "flack_parameter",
    "formatted_melting_point_range",
    "formatted_melting_point_text",
    "formula",
    "habit",
    "has_3d_structure",
    "has_disorder",
    "heat_capacity",
    "heat_capacity_notes",
    "heat_of_fusion",
    "heat_of_fusion_notes",
    "hkl_source",
    "hydrogen_treatment",
    "input_melting_point_range",
    "input_melting_point_text",
    "is_organic",
    "is_organometallic",
    "is_polymeric",
    "is_powder_study",
    "melting_point",
    "melting_point_default_units",
    "melting_point_display_string",
    "peptide_sequence",
    "phase_transition",
    "polymorph",
    "pressure",
    "previous_identifier",
    "publication",
    "publications",
    "r_factor",
    "radiation_source",
    "raw_data_dois",
    "refinement_details",
    "refinement_goodness_of_fit",
    "refinement_max_shift",
    "refinement_number_of_constraints",
    "refinement_number_of_parameters",
    "refinement_number_of_restraints",
    "refinement_residual_electron_density_max",
    "refinement_residual_electron_density_min",
    "refinement_weighted_r_factor",
    "reflection_max_theta",
    "remarks",
    "res_source",
    "resolution",
    "solubility_data",
    "solvent",
    "source",
    "synonyms",
    "synonyms_as_html",
    "temperature",
    "wavelengths",
)

NATIVE_TYPES = (bool, int, float, str, datetime.date, datetime.datetime)


def to_native(value):
    if (value is None) or isinstance(value, NATIVE_TYPES):
        return value
    if isinstance(value, dict):
        return {str(k): to_native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_native(v) for v in value]
    return str(value)


def follow(obj, path):
    for part in path.split("."):
        if obj is None:
            return None
        try:
            obj = obj[int(part)] if part.isdigit() else getattr(obj, part)
        except Exception:  # noqa: BLE001  a missing ccdc property can raise any kind of error
            return None
    return obj


def read(value, spec=None):
    if value is None:
        return None
    if spec is None:
        return to_native(value)
    if isinstance(spec, list):
        return [read(item, spec[0]) for item in value]

    row = {}
    for field, source in spec.items():
        path, subspec = source if isinstance(source, tuple) else (source, None)
        row[field] = read(follow(value, path), subspec)
    return row


def main(out: str = str(DATA_DIR / "raw" / "csd_metadata.full.parquet")):
    reader = EntryReader("CSD")

    rows = []
    for entry in tqdm(reader.entries(), total=len(reader), desc="Exporting CSD metadata"):
        rows.append({f: read(follow(entry, f), NESTED.get(f)) for f in FIELDS})

    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pl.from_dicts(rows, infer_schema_length=None).write_parquet(out)
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    auto_cli(main)
