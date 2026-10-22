import json
import pathlib
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

import polars as pl
import pymupdf
import pymupdf4llm
from jsonargparse import auto_cli
from lxml import etree
from tqdm import tqdm

from dataset.paths import DATA_DIR

FILTER = pathlib.Path(__file__).with_suffix(".lua")
# The columns of `parsed.parquet`, one row per downloaded paper.
SCHEMA = {
    "dir": pl.String,
    "doi": pl.String,
    "files": pl.List(pl.String),
    "chars": pl.List(pl.Int64),
    "needs_ocr": pl.List(pl.String),
    "error": pl.String,
}
# The pandoc reader for each file type; `.doc` goes through LibreOffice to `.docx` first.
PANDOC_FORMATS = {
    ".xml": "jats",
    ".docx": "docx",
    ".odt": "odt",
    ".rtf": "rtf",
    ".htm": "html",
    ".html": "html",
}
# The JATS elements inside which whitespace is never a word separator.
INLINE = ["xref", "sup", "sub", "bold", "italic", "underline", "sc", "ext-link", "uri"]


def text(el):
    return " ".join("".join(el.itertext()).split())


def citation(cit):
    """Returns a citation as a line of text, from its free text or its structured fields."""
    if cit.tag != "element-citation":
        return text(cit)
    names = [text(n) for n in cit.iter("name", "collab")]
    pages = "–".join(p for p in [cit.findtext("fpage"), cit.findtext("lpage")] if p)
    doi = cit.find('pub-id[@pub-id-type="doi"]')
    parts = [", ".join(names)]
    parts += [text(t) for t in cit.iter("article-title", "chapter-title", "source")]
    parts += [cit.findtext("year"), cit.findtext("volume"), pages]
    parts += [doi.text if (doi is not None) else ""]
    return ". ".join(p.strip(" .") for p in parts if p and p.strip(" ."))


def prepare_xml(xml):
    """Returns the JATS XML with the fixes pandoc needs.

    Each figure's and table's label (e.g. `Figure 2`) is prepended to its caption, since pandoc
    drops the labels. The reference list becomes a section of plain paragraphs, since pandoc
    keeps only the structured citations (most are free text), and only as YAML metadata.
    Unnumbered lists are marked as bullet lists, which pandoc would number. Self-citations and
    the copyright lines of figures and tables are dropped. The indentation that
    `s0_download.py` added inside inline elements (`<xref>\\n<sup>1</sup>\\n</xref>`) is
    removed, since pandoc would turn it into spaces (`[ ¹ ]`).
    """
    root = etree.parse(xml, etree.XMLParser(resolve_entities=False, no_network=True)).getroot()
    for el in root.iter("fig", "table-wrap"):
        label, caption = el.findtext("label"), el.find("caption")
        if (not label) or (caption is None) or (len(caption) == 0):
            continue
        for title in caption.findall("title"):
            title.tag = "p"  # pandoc would make a heading of it
        label = label.strip().rstrip(".:")
        first = caption[0]
        first.text = f"{label}. {first.text or ''}"

    for given in root.iter("given-names"):
        surname = given.getprevious()
        if (surname is not None) and (surname.tag == "surname") and (not surname.tail):
            surname.tail = " "
    for ref_list in list(root.iter("ref-list")):
        sec = etree.Element("sec")
        title = ref_list.find("title")
        etree.SubElement(sec, "title").text = text(title) if (title is not None) else "References"
        for i, ref in enumerate(ref_list.iter("ref"), start=1):
            label = (ref.findtext("label") or str(i)).strip().strip("[]().")
            cits = ref.findall("mixed-citation") + ref.findall("element-citation")
            line = " ".join(citation(c) for c in cits) if cits else text(ref)
            etree.SubElement(sec, "p").text = f"{label}. {line}"
        ref_list.getparent().replace(ref_list, sec)

    for el in root.iter("list"):
        if el.get("list-type") == "simple":
            el.set("list-type", "bullet")
    drop = '//p[@content-type="self-citation"] | //fig//permissions | //table-wrap//permissions'
    for el in root.xpath(drop):
        el.getparent().remove(el)

    for el in root.iter(*INLINE):
        if el.text and (not el.text.strip()) and ("\n" in el.text):
            el.text = None
        for child in el:
            if child.tail and (not child.tail.strip()) and ("\n" in child.tail):
                child.tail = None
    return etree.tostring(root)


def pandoc(src, dst, fmt):
    """Converts `src` to GitHub Markdown, with a YAML front matter (title, authors, date,
    licence) and no HTML in the body (`FILTER`)."""
    # Without raw HTML, pandoc writes complex tables as pipe tables instead of `<table>`; without
    # GitHub's math syntax, it writes formulas as `$...$`.
    cmd = ["pandoc", "-f", fmt, "-t", "gfm-raw_html-tex_math_gfm", "-s", "--wrap=none"]
    cmd += ["--lua-filter", str(FILTER)]
    stdin = prepare_xml(src) if (fmt == "jats") else None
    if stdin is None:
        cmd.append(str(src))
    run = subprocess.run(cmd, input=stdin, check=False, capture_output=True, timeout=600)
    if run.returncode != 0:
        raise RuntimeError(f"pandoc {src.name}: {run.stderr.decode().strip()[:300]}")
    # Pandoc escapes what could be Markdown syntax, e.g. `[13]` as `\[13\]` and the filter's
    # `_{...}` as `\_{...}` (doubled inside the YAML strings, where it is not even valid); the
    # text is for reading, not rendering, so the escapes go.
    md = run.stdout.decode()
    for ch in "[]_*<>.":
        md = md.replace(f"\\\\{ch}", ch).replace(f"\\{ch}", ch)
    # Soft hyphens inside words and IUCr's link glyphs (`2015 ▸`) are typesetting, not text.
    md = md.replace("\u00ad", "").replace(" ▸", "").replace(" ▶", "").replace("\u00a0", " ")
    dst.write_text("\n".join(line.rstrip() for line in md.splitlines()) + "\n")


def doc_to_docx(src, tmp):
    """Converts a `.doc` to `.docx` with LibreOffice, with its own profile so runs don't clash."""
    cmd = [
        "soffice",
        "--headless",
        f"-env:UserInstallation=file://{tmp}/profile",
        "--convert-to",
        "docx",
        "--outdir",
        str(tmp),
        str(src),
    ]
    subprocess.run(cmd, check=False, capture_output=True, timeout=600)
    dst = tmp / f"{src.stem}.docx"
    if not dst.exists():
        raise RuntimeError(f"soffice {src.name}: no output")
    return dst


def pdf_to_md(src, dst, min_chars):
    """Writes the text layer of `src` as Markdown, without images.

    Returns:
        Whether the PDF has fewer than `min_chars` characters per page on average, i.e. it is a
        scan with no usable text layer and needs OCR.
    """
    with pymupdf.open(src) as doc:
        needs_ocr = sum(len(page.get_text()) for page in doc) < (min_chars * doc.page_count)

    # Unless images and drawings are ignored, the text that overlaps them (e.g. figure captions)
    # is dropped too: checked on four files, this keeps 97-100% of the text layer, not 32-97%.
    md = pymupdf4llm.to_markdown(
        str(src),
        write_images=False,
        ignore_images=True,
        ignore_graphics=True,
    )
    dst.write_text(md)
    return needs_ocr


def parse(raw, out, min_chars):
    """Converts the files of one paper in `raw` to Markdown files of the same stem in `out`.

    `paper.pdf` is skipped, since `paper.xml` has the same text. Old files in `out` are deleted
    first, so a rerun starts from scratch.

    Returns:
        The columns of `parsed.parquet` that describe the conversion.
    """
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    res = {"files": [], "chars": [], "needs_ocr": [], "error": None}
    try:
        for src in sorted(raw.iterdir()):
            if src.name == "paper.pdf":
                continue
            dst = out / f"{src.stem}.md"
            if src.suffix == ".pdf":
                if pdf_to_md(src, dst, min_chars):
                    res["needs_ocr"].append(src.name)
            elif src.suffix in [".txt", ".tex"]:
                shutil.copy(src, dst)
            elif src.suffix == ".doc":
                with tempfile.TemporaryDirectory() as tmp:
                    pandoc(doc_to_docx(src, pathlib.Path(tmp)), dst, "docx")
            else:
                pandoc(src, dst, PANDOC_FORMATS[src.suffix])
            res["files"].append(dst.name)
            res["chars"].append(dst.stat().st_size)
    except Exception as err:  # noqa: BLE001  MuPDF raises many kinds, e.g. on a broken PDF
        res["error"] = repr(err)
    return res


def main(
    papers: str = str(DATA_DIR / "papers"),
    workers: int = 48,
    min_chars_per_page: int = 200,
    resume: bool = True,
):
    """Converts every downloaded paper to Markdown, in `<papers>/parsed/<DOI>/`.

    `paper.xml` becomes `paper.md` through pandoc's JATS reader. `paper.pdf` is not parsed: it
    has the same text as the XML (checked on a sample), and the XML has no page or column noise.
    Each supplementary file becomes `supplementary*.md`: PDFs through PyMuPDF4LLM, which reads
    the text layer (no OCR) and drops the images; Word, ODT, RTF and HTML files through pandoc;
    `.txt` and `.tex` files are copied (pandoc's LaTeX reader can hang). A PDF with fewer than
    `min_chars_per_page` characters per
    page on average is a scan, so it is listed in `needs_ocr` for a later OCR stage.

    Writes one row per downloaded paper to `<papers>/parsed.parquet` (columns in `SCHEMA`), and
    logs each parsed paper to `<papers>/parsed.jsonl`, so that a stopped run can resume. With
    `resume`, papers that parsed without an error are skipped.
    """
    papers = pathlib.Path(papers)
    meta = pl.read_parquet(papers / "metadata.parquet").filter(pl.col("error").is_null())

    log = papers / "parsed.jsonl"
    if not resume:
        log.unlink(missing_ok=True)
    done = {}
    if log.exists():
        with open(log) as f:
            done = {d["dir"]: d for d in map(json.loads, f)}
    ok = {d for d, r in done.items() if (not r["error"]) and (papers / "parsed" / d).exists()}

    todo = [d for d in meta["dir"] if d not in ok]
    print(f"{len(meta)} papers, {len(ok)} parsed, {len(todo)} to parse")
    with ProcessPoolExecutor(workers) as ex, open(log, "a") as f:
        futures = {
            ex.submit(
                parse,
                raw=papers / "raw" / d,
                out=papers / "parsed" / d,
                min_chars=min_chars_per_page,
            ): d
            for d in todo
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="parse"):
            d = futures[future]
            done[d] = {"dir": d, **future.result()}
            f.write(json.dumps(done[d]) + "\n")
            f.flush()

    rows = [{"doi": doi} | done[d] for d, doi in zip(meta["dir"], meta["doi"])]
    parsed = pl.DataFrame(rows, schema=SCHEMA).sort("dir")
    parsed.write_parquet(papers / "parsed.parquet")
    print(parsed.group_by(error=pl.col("error").str.extract(r"^([^:(]+)")).len().sort("len"))
    print(f"{parsed['needs_ocr'].list.len().sum()} PDFs need OCR")
    print(f"Wrote {papers / 'parsed.parquet'}")


if __name__ == "__main__":
    auto_cli(main)
