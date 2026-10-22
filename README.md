<div align="center">

# TEXtal

**A dataset of crystal structures paired with text-mined crystallization procedures and outcomes.**

<img src="assets/example.png" width="800" alt="The unit cell of caffeinium bisulfate monohydrate beside its extracted record: the compound matched in the paper, its synthesis, its crystallization and its solid form">

</div>

TEXtal links entries in the Cambridge Structural Database (CSD) to the crystallization
procedures and outcomes reported in their papers. We download the open-access papers of the CSD
from PubMed Central (PMC), convert them to Markdown and use a large language model (LLM) to
extract the synthesis and crystallization procedure of each entry, with quotes from the paper
as evidence. The pairs support text-conditioned crystal structure prediction (CSP), which
predicts the crystal that a molecule forms under a written procedure, and condition generation,
which predicts a procedure that yields a given crystal.

**The extraction is not finished.** The hackathon ended before the model had read every paper:
the records cover 28,920 of the 54,961 papers (53%). The rest of the corpus is downloaded and
converted, and the extraction resumes where it stopped.

## Installation

We use the [pixi](https://pixi.sh) dependency manager (Linux only). MinerU, the optical
character recognition (OCR) tool for scanned PDFs, needs a GPU and its own environment
(`pixi install -e ocr`).

```bash
git clone https://github.com/alstonlo/clari-data-osi-hack.git
cd clari-data-osi-hack
pixi install
```

## Usage

**CSD metadata.** The pipeline starts from `data/raw/csd_metadata.full.parquet`, the metadata of
every CSD entry (refcode, compound name, journal and DOI). Exporting it needs a licence from the
Cambridge Crystallographic Data Centre (CCDC), so it is not in this repository. Install the CSD
data from the [CCDC downloads page](https://www.ccdc.cam.ac.uk/support-and-resources/csdsdownloads/),
install the CSD Python API in its own environment (`pixi install -e csd`), write your licence
code to a file named `.env` at the repository root (the second line is needed only if the CCDC
installer did not record the location of the CSD data in `~/.config/CCDC/CSD.ini`), then export:

```bash
CCDC_LICENSING_CONFIGURATION=la-code;<your-licence-code>
CSD_DATA_DIRECTORY=<folder of the CSD data>
```

```bash
pixi run -e csd python scripts/runs/csd/s0_metadata.py
```

**Corpus.** This command looks up the DOI of every CSD entry in PMC's list, downloads the papers
that are there from PMC's open-access bucket (several hours and about 200 GB; an interrupted
download resumes) and converts them to Markdown. The papers of Acta Crystallographica Section E
(Acta E), the journal with the most CSD entries, were also fetched as complete PMC packages,
which hold the original crystallographic information files (CIFs) and chemical schemes that the
website shows; those scripts ran on a cluster and are not on this branch.

```bash
pixi run snakemake -s scripts/Snakefile -j1 all
```

**Extraction.** The model is called through a LiteLLM proxy and needs an API key. A run writes
`data/runs/<name>/extractions.parquet`, one record per CSD entry, and resumes if stopped.

```bash
export LITELLM_API_KEY=...
pixi run python -m dataset.extraction_stream --sample 200 --run data/runs/pilot200   # a sample
pixi run python -m dataset.extraction_stream --run data/runs/corpus                  # every paper
```

This runner reads the full Markdown of a paper. The Acta E papers were read by a second runner
(`acta_e_stream.py`, which ran on the cluster with the Acta E packages) that reads only the
experimental sections and makes the model pick its quotes from numbered passages, so that the
quotes are verbatim by construction. The records of both runs are gathered in
`data/extractions.parquet`, kept to the papers of the corpus; its `prompt_version` column tells
the runs apart.

```bash
pixi run snakemake -s scripts/Snakefile -j1 plot_extraction   # Figure 1
pixi run snakemake -s scripts/Snakefile -j1 example           # the example above (needs Chrome)
```

**Website.** For each extracted entry, the website shows the crystal structures of its paper
(drawn from the publisher's CIFs), its chemical scheme, the paper's text and the record, with the
quote behind each paragraph. It reads only the tables in `src/viz/assets/`, built with
`pixi run snakemake -s scripts/Snakefile -j1 assets`, which hold nothing from the CSD but
refcodes and DOIs; it shows the text of the CC BY papers only.

```bash
pixi run web --port 8000
```

## About TEXtal

The CSD holds 1.4 million crystal structures, but it does not systematically record their
crystallization procedures: its `solvent` field is a single string, empty for 84% of entries,
and the procedures are only in the papers. CSP models such as [Clari](https://github.com/the-matter-lab/clari)
predict how a molecule packs into a crystal from the molecule alone, yet the same molecule can
form different crystals (polymorphs, solvates or salts) depending on how it is crystallized.
Text-conditioned CSP and condition generation both need crystallization procedures linked to
crystal structures, and we found no public dataset that provides them for the CSD.

**Approach.** The CSD entries cite 554,956 unique DOIs, of which 56,225 are in PMC's list. Most
publisher sites block automated downloads, but PMC's open-access bucket on Amazon Web Services
(AWS) allows them: it held 54,961 of the papers (203 GB), every one with its full text as XML,
which pandoc converts to Markdown without OCR. Supplementary PDFs go through PyMuPDF4LLM; the
1.6% that are scanned still need MinerU. We send one LLM request per paper, with its text and a
table of its CSD entries (refcode, CCDC number, name and formula). For each entry, the model
names the compound in the paper, rates its confidence in the match (high, medium or low) and
writes one short paragraph per topic: synthesis, crystallization, characterization, solid form
(such as a salt or hydrate) and purpose and properties, each backed by at least one verbatim
quote. We ask for paragraphs rather than fixed fields (solvent, method, temperature) because we
do not know in advance what the papers report; the fields can be derived from the paragraphs
later. The papers of the other journals were read in full by `gpt-6-luna`; the Acta E papers,
which report one structure each in a fixed layout, were read by `gpt-5.6-luna` from their
experimental sections only, because the first run used up gpt-6-luna's quota. Both ran at
reasoning effort `high`, which gave the same matches and core paragraphs as `max` about 10 times
faster.

**Results.** The extraction covers **45,066 CSD entries from 28,920 papers**, 53% of the corpus
(Figure 1a): 23,420 entries from 23,077 Acta E papers (85% of Acta E) and 21,646 entries from
5,843 papers in other journals (21%), extracted in about six hours. The model wrote a record for
44,826 entries (99.5%) and rated 98% of its matches high confidence. Of the records, 97%
describe the synthesis, 87% the crystallization, 62% the characterization, 46% the purpose and
properties and 42% the solid form (Figure 1b); the Acta E run, reading experimental sections
only, nearly always has the first two and rarely the rest. Of the 39,082 entries with a
crystallization paragraph, 71% have an empty `solvent` field in the CSD. In a manual check of 10
papers, the model matched all 23 entries to the right compound; of its 337 quotes, 27 differed
from the paper, mostly in hyphenation or letter case. Of the papers, 74% are under Creative
Commons Attribution (CC BY), so their text can be shared.

<div align="center"><figure>
<img src="assets/extraction.png" width="700" alt="Extracted papers of the ten largest journals, and the filled paragraphs and match confidence of the records of the two runs">
</figure></div>

> **Figure 1.** (a) The papers of the ten largest journals, split into those the model
has read (blue) and those still waiting (grey), with the share read. The extraction ran journal
by journal and stopped at the end of the hackathon, in the middle of Inorganic Chemistry. (b) The
share of records with each paragraph filled, per run. The Acta E run read only the experimental
sections, so its records rarely cover characterization, purpose or the solid form. (c) The
confidence of the match between the CSD entry and the compound in the paper.

**Next steps.** Finish the extraction (26,041 papers, mostly general chemistry journals, and the
4,149 Acta E papers the second run had not reached); check every quote of the full-text run
against the source text automatically; derive fixed fields (method, solvents, temperature, time)
from the paragraphs and compare them with the CSD's `solvent` field; run OCR on the scanned
supplementary PDFs; and release the records of the CC BY papers as a public dataset.

## Licence

The CSD metadata is licensed by the CCDC and is not redistributed here, nor are tables built from
it (the website's tables hold only refcodes and DOIs; `stats.json` holds counts only). Each paper
keeps the licence given in its PMC record, and the Acta E files (CIFs and chemical schemes) the
[terms of use](https://journals.iucr.org/services/termsofuse.html) of the IUCr; the website shows
the text of the CC BY papers only.
