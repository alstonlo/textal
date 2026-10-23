<div align="center">

# TEXtal

**Crystal structures paired with how they were made and grown.**

<img src="docs/assets/record.png" width="800" alt="Crystal structure beside procedure fields and supporting quotes">

*OSI Hackathon 2026*

</div>

TEXtal links the crystal structures of the Cambridge Structural Database (CSD) to the procedures
and outcomes reported in their papers. For each CSD entry, a large language model (LLM) reads the
open-access paper and writes a record of how the compound was made and how its crystals were
grown, backed by quotes from the paper.

## Why

The same molecule can form different crystals (polymorphs, solvates or salts) depending on how
it is crystallized. Crystal structure prediction (CSP) models such as
[Clari](https://github.com/the-matter-lab/clari) predict the crystal from the molecule alone.
They cannot take the procedure into account, nor say how to obtain a given crystal. This matters
because the crystal form sets properties such as solubility, stability and how a drug is
absorbed, and a chemist who wants a particular form needs to know how to make it.

The CSD holds 1.4 million crystal structures but does not systematically record how they were
grown. That knowledge is in the papers, written as free text in the experimental section or the
supplementary information. Each paper reports it differently, with its own level of detail, and
it is spread across many journals and decades of literature. Collecting it by hand does not
scale. We found no public dataset that links crystallization procedures to crystal structures.
LLMs can now read papers at this scale, which makes building one possible.

TEXtal's records could train models for two tasks:

- **Text-conditioned CSP:** predict the crystal from the molecule and a written procedure.
- **Condition generation:** predict a procedure that yields a given crystal.

## Approach

1. **Find the papers.** The CSD entries cite 554,956 unique DOIs. Of these, 56,225 are in PubMed
   Central (PMC), covering 121,147 CSD entries.
2. **Download.** 54,961 open-access papers (203 GB) from PMC, with their full text and
   supplementary documents.
3. **Convert.** Papers and supplementary documents become Markdown.
4. **Extract.** One LLM request per paper, with its text and its CSD entries. For each entry, the
   model identifies the compound, rates its confidence in the match, and writes a short paragraph
   per topic (synthesis, crystallization, characterization, solid form, and purpose and
   properties), each backed by quotes. Acta E papers, which report one structure each, use their own
   prompt. Paragraphs rather than fixed fields keep whatever the
   paper reports, and structured fields can be derived from them later.
5. **Browse.** A website shows corpus statistics and, for the CSD Drug Subset, each entry's 3D
   unit cell, molecule, paper and record.

<div align="center">
<img src="docs/assets/years.png" width="700" alt="Papers by year and journal">

*Papers by year and journal. Acta Crystallographica Section E, which publishes one structure per
paper, supplies the largest share of the corpus.*
</div>

## Results

- **Corpus.** 54,961 papers and 23,215 supplementary documents in Markdown (3.3 GB). 74% of the
  papers are under CC BY, so their text can be shared.
  Two thirds report a single CSD entry, which makes matching paper and entry easy.
- **Extraction.** As of 22 October, 52,786 CSD entries from 33,777 papers, in about six hours.
  The model wrote a record for 99.3% of the entries and rated 97.8% of its matches high
  confidence. Of the records, 97% describe the synthesis, 88% the crystallization, 63% the
  characterization, 48% the purpose and properties and 44% the solid form, citing 576,257
  quotes in total.

## Next steps

- Extract the rest of the corpus.
- Derive structured fields from the paragraphs.
- Add open-access papers from outside PMC.
- Release the records of the CC BY papers as an open dataset.

## Quickstart

TEXtal uses [pixi](https://pixi.sh) (Linux) and needs a CCDC licence for the CSD metadata.
Install the [CSD data](https://www.ccdc.cam.ac.uk/support-and-resources/csdsdownloads/), then:

```bash
git clone https://github.com/alstonlo/clari-data-osi-hack.git && cd clari-data-osi-hack
pixi install
pixi install -e csd   # CSD Python API, in its own env because it pins older NumPy, pandas and SciPy
```

Write your licence to `.env` at the repository root. The second line is needed only if
`~/.config/CCDC/CSD.ini` does not record the location of the CSD data.

```bash
CCDC_LICENSING_CONFIGURATION=la-code;<your-licence-code>
CSD_DATA_DIRECTORY=<folder of the CSD data>
```

Then run the pipeline. The download and the extraction resume if interrupted.

```bash
pixi run -e csd python scripts/runs/csd/s0_metadata.py   # CSD metadata -> data/raw/
pixi run snakemake -s scripts/Snakefile -j1 all           # download + convert papers (~200 GB)

export LITELLM_API_KEY=...                                # extraction runs via a LiteLLM proxy
pixi run python -m dataset.extraction_stream --run data/runs/corpus
# try it first on a sample: --sample 200 --run data/runs/pilot200

pixi run snakemake -s scripts/Snakefile -j1 assets        # build the website tables
pixi run web --port 8000                                  # http://localhost:8000
```

Each extraction run writes `data/runs/<name>/extractions.parquet`, one record per CSD entry.

## Licence

The CSD metadata is licensed by the CCDC and is not redistributed here, nor are the website
tables built from it (only `stats.json`, which holds counts). Each paper keeps the licence of its
PMC record. The website shows text from CC BY papers only.
