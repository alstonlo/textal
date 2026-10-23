<div align="center">

# TEXtal

**A dataset of crystal structures paired with text-mined crystallization procedures and outcomes.**

[![data](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Data-blue)](https://huggingface.co/datasets/alstonlo/textal-data)
[![explorer](https://img.shields.io/badge/%F0%9F%A4%97%20Explorer-6f42c1)](https://huggingface.co/spaces/alstonlo/textal)

<img src="assets/example.png" width="800" alt="The unit cell of caffeinium bisulfate monohydrate beside its extracted record: the compound matched in the paper, its synthesis, its crystallization and its solid form">

</div>

TEXtal links entries in the Cambridge Structural Database (CSD) to the crystallization procedures and outcomes reported in their papers. We download the open-access papers cited by the CSD from PubMed Central (PMC), convert them to Markdown and use a large language model (LLM) to extract each entry's synthesis and crystallization procedures, with quotes from the paper as evidence. The pairs support multimodal problems such as text-conditioned crystal structure prediction (CSP), which predicts the crystal that a molecule forms under a written procedure, and condition generation, which predicts a procedure that yields a given crystal.

> [!WARNING]
> This project was created for the Open Scientific Intelligence Hackathon 2026. It is still a prototype: the records cover 28,920 of the 54,961 papers in the corpus (53%).

## Installation

We use the [pixi](https://pixi.sh) dependency manager (Linux only). MinerU, the optical character recognition (OCR) tool for scanned PDFs, needs a GPU and its own environment (`pixi install -e ocr`).

```bash
git clone https://github.com/alstonlo/textal.git
cd textal
pixi install
```

## Usage

### Quickstart

The dataset is uploaded to Hugging Face at [alstonlo/textal-data](https://huggingface.co/datasets/alstonlo/textal-data). Download and unpack the dataset into `data/textal/` using:

```bash
pixi run hf download alstonlo/textal-data --repo-type dataset --local-dir data/textal
cd data/textal && tar -xf texts.tar && tar -xf files.tar && rm texts.tar files.tar
```

Launch the local web explorer for the TEXtal data:

```bash
pixi run web --port 8000
```

### Processing

**CSD metadata.** The pipeline starts from `data/raw/csd_metadata.full.parquet`, the metadata of every CSD entry (refcode, compound name, journal and DOI). Exporting it requires a licence from the Cambridge Crystallographic Data Centre (CCDC), so it is not in this repository. Install the CSD data from the [CCDC downloads page](https://www.ccdc.cam.ac.uk/support-and-resources/csdsdownloads/), install the CSD Python API in its own environment (`pixi install -e csd`) and write your licence code to a file named `.env` at the repository root:

```bash
CCDC_LICENSING_CONFIGURATION=la-code;<your-licence-code>
CSD_DATA_DIRECTORY=<folder of the CSD data>
```

The second line is needed only if the CCDC installer did not record the location of the CSD data in `~/.config/CCDC/CSD.ini`. Then export the metadata:

```bash
pixi run -e csd python scripts/runs/csd/s0_metadata.py
```

**Corpus.** The following command matches each CSD entry's DOI against PMC's list, downloads the available papers from PMC's open-access bucket and converts them to Markdown. The download takes several hours and about 200 GB of storage, and resumes if interrupted. We also downloaded the papers of Acta Crystallographica Section E (Acta E), the journal with the most CSD entries, as complete PMC packages. These packages contain the original crystallographic information files (CIFs) and chemical schemes shown on the website.

```bash
pixi run snakemake -s scripts/Snakefile -j1 all
```

**Extraction.** The model is called through a LiteLLM proxy and needs an API key. A run writes `data/runs/<name>/extractions.parquet`, one record per CSD entry, and resumes if stopped.

```bash
export LITELLM_API_KEY=...
pixi run python -m dataset.extraction_stream --sample 200 --run data/runs/pilot200   # a sample
pixi run python -m dataset.extraction_stream --run data/runs/corpus                  # every paper
```

This runner reads the full Markdown of a paper. We read the Acta E papers with a second runner that reads only the experimental sections and has the model select its quotes from numbered passages, so that the quotes are verbatim by construction. We combine the records of both runs in `data/extractions.parquet`, keeping only records from papers in the corpus. Its `prompt_version` column identifies the run.

```bash
pixi run snakemake -s scripts/Snakefile -j1 plot_extraction   # Figure 1
pixi run snakemake -s scripts/Snakefile -j1 example           # the example above (needs Chrome)
```

**Release.** The dataset was built from the corpus with `pixi run snakemake -s scripts/Snakefile -j1 release`.

## About TEXtal

Generative models for crystal structure prediction (CSP) predict how a molecule packs into a crystal from the molecule alone. Yet the same molecule can form polymorphs (different molecular arrangements), solvates (crystals containing solvent) or salts (ionic compounds), depending on how it was crystallized. Generative models of crystals increasingly use text or several types of input at once. The crystallization procedure is a natural input for these models, but the Cambridge Structural Database (CSD) does not store it, and we found no public dataset pairing CSD structures with their procedures.

Mining these procedures is limited by access more than by method. Of the 554,956 papers the CSD cites, only the 56,225 in the open-access list of PubMed Central (PMC) can be downloaded freely; they cover 121,147 CSD entries, including about one in five of the CSD entries added since 2020. TEXtal links 39,082 CSD entries to their crystallization paragraphs extracted from these papers.

### Approach

We use a large language model (LLM) to extract one record per CSD entry from its paper. We download the papers from PMC's open-access bucket on Amazon Web Services, which held 54,961 of them (203 GB) with full text as XML; these papers form the corpus. Pandoc converts the XML to Markdown without optical character recognition (OCR), and PyMuPDF4LLM reads the text layer of supplementary PDFs. In 861 papers (1.6%), a supplementary PDF is a scanned image without a text layer. These PDFs require OCR with MinerU and remain unread.

Each record holds the paper's label for the compound (e.g. "3a"), the model's confidence in the match between the entry and the compound (high, medium or low) with its reason, and one paragraph per topic: synthesis (compound preparation), crystallization (crystal growth), characterization (other measurements), solid form (such as a salt or hydrate, a crystal containing water) and purpose and properties. Each filled paragraph must cite at least one verbatim quote. We chose paragraphs over fixed fields (solvent, method, temperature) because we did not know what the papers would report; fields can be derived later.

We send one LLM request per paper, with the paper's Markdown and a table of its CSD entries: refcode (entry identifier), Cambridge Crystallographic Data Centre (CCDC) deposition number (deposited structure identifier), name, formula and fields such as temperature, polymorph and colour. The reply follows a JSON schema with one record per entry. We instruct the model to keep records separate for polymorphs, solvates and measurements at different temperatures, to copy shared procedures into each compound's record, to write only what the paper says and to omit what the CSD already holds (unit cell, the repeating crystal cell; molecular geometry; molecular packing).

In the full-text run, `gpt-6-luna` read the full papers from journals other than Acta Crystallographica Section E (Acta E). Acta E papers report one structure each in a fixed layout, so in the Acta E run, `gpt-5.6-luna` read only their experimental sections, split into numbered sentences. The model cites sentence numbers, and the code copies the cited sentences from the paper, so the quotes in the Acta E run are verbatim. Both runs used the reasoning-effort setting `high`, which gave the same matches as `max` about 10 times faster.

### Results

The extraction covers **45,066 CSD entries from 28,920 papers**, 53% of the corpus (Figure 1a). Coverage is higher for Acta E: 23,420 entries from 23,077 Acta E papers (85% of the Acta E papers in the corpus), compared with 21,646 entries from 5,843 papers in other journals (21% of their papers in the corpus).

Most records describe synthesis (97%) and crystallization (87%); fewer describe characterization (62%), purpose and properties (46%) or solid form (42%) (Figure 1b).

The model returned a record for 44,826 of the 45,066 entries (99.5%) and rated its confidence in the match as high in 98% of the records (Figure 1c).

In a manual check of 10 papers, the model matched all 23 entries to the right compound; of its 337 quotes, 27 differed from the paper, mostly in hyphenation or letter case.

Of the papers, 74% are under Creative Commons Attribution (CC BY), so their text can be shared.

<div align="center"><figure>
<img src="assets/results.png" width="700" alt="Extracted papers of the ten largest journals, and the filled paragraphs and match confidence of the records of the two runs">
</figure></div>

> **Figure 1.** Extraction coverage is higher for Acta E than for other journals. (a) Paper counts for the ten largest journals, split into papers that were extracted (blue) and papers that were not (grey), with the share extracted. We extracted the papers one journal at a time, and extraction for Inorganic Chemistry is incomplete. (b) The share of records with each topic paragraph filled, per run (Acta E or other journals). The Acta E run read only the experimental sections, so its records rarely cover characterization, purpose or the solid form. (c) The confidence of the match between the CSD entry and the compound, as rated by the model.

### Next steps

- Extract the remaining 26,041 papers, mostly from general chemistry journals (4,149 are Acta E).
- Automatically check the full-text run's quotes against the source papers.
- Read the 861 scanned supplementary PDFs with MinerU.
- Derive fixed fields, such as solvent, method and temperature, from the topic paragraphs.

## Licence

The CSD metadata is licensed by the CCDC and is not redistributed here, nor are tables built from it: the dataset holds only refcodes and DOIs from the CSD, and sentences in the extracted records that repeat CSD metadata are removed. Each paper keeps its licence (that of its PMC copy, or for Acta E that of its XML). The dataset and the website include the text, CIFs and chemical schemes of a paper only if it is under a Creative Commons licence, and they credit each paper by its authors, title, journal and DOI.
