# scripts

Every script is run from the repository root with `pixi run python scripts/<path>.py`; its
arguments are the keyword arguments of its `main` (`--help` lists them). [The
Snakefile](Snakefile) is the reference for which script produces which file from which input, and
for how to run them in order.

```bash
pixi install
pixi run snakemake -s scripts/Snakefile -n                   # what would run
pixi run snakemake -s scripts/Snakefile -j1 all              # the corpus
pixi run snakemake -s scripts/Snakefile -j1 plot_extraction  # the extraction figure
pixi run snakemake -s scripts/Snakefile -j1 example          # the README's example record (needs Chrome)
pixi run snakemake -s scripts/Snakefile -j1 assets           # the tables of the website
```

`runs/` holds the scripts that make the data, `analysis/` those that only read it. The analysis
scripts that print statistics instead of writing files (`s0_csd_journal_stats.py`,
`s0_clari_stats.py`) are not Snakemake rules; run them directly. The scripts of `runs/viz/`
written by the website's author take `argparse` flags instead of keyword arguments. Every
script in a stage folder is named `s<N>_<name>.py`, where `<N>` is the order in which it runs: a
script may only use the outputs of scripts with a smaller `<N>`, and scripts that share an `<N>`
do not depend on each other.
