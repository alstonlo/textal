// The 3D viewer's second model holds the molecules around the unit cell; the button shows it.
// py3Dmol names its viewer after the id of its div, and fills it once 3Dmol has loaded.
const button = document.getElementById("supercell");
const id = document.querySelector('[id^="3dmolviewer_"]').id.replace("3dmolviewer_", "viewer_");
$3Dmolpromise.then(() => {
  const viewer = window[id];
  const shell = viewer.getModel(1);
  shell.hide();
  viewer.render();
  button.addEventListener("click", () => {
    const on = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", on);
    button.classList.toggle("on", on);
    on ? shell.show() : shell.hide();
    viewer.zoomTo(on ? {} : { model: 0 });
    viewer.render();
  });
});

// The paper, from its Markdown, with the extraction's evidence quotes highlighted.
const md = document.getElementById("paper-md").textContent;
const paper = document.getElementById("paper-text");
if (md.trim()) paper.innerHTML = markdownit({ html: false, linkify: true }).render(md);

// Each quote marks its first occurrence; a paragraph can hold several quotes, so every quote walks
// the text afresh, after the marks of the quotes before it have split the paragraph's text. A quote
// that runs across formatting (e.g. an italic word) is in no single text node, so its whole
// paragraph is highlighted instead.
const evidence = JSON.parse(document.getElementById("evidence").textContent);
const quotes = new Set(evidence.map((e) => e.quote).filter(Boolean));
const targets = new Map();
for (const qt of quotes) {
  const walker = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
  while (walker.nextNode() && !targets.has(qt)) {
    const node = walker.currentNode;
    const i = node.data.indexOf(qt);
    if (i < 0) continue;
    const mark = document.createElement("mark");
    mark.textContent = qt;
    node.replaceWith(node.data.slice(0, i), mark, node.data.slice(i + qt.length));
    targets.set(qt, mark);
  }
  const block = targets.has(qt) ? null : [...paper.querySelectorAll("p, li")].find((b) => b.textContent.includes(qt));
  if (block) {
    block.classList.add("quoted");
    targets.set(qt, block);
  }
}

for (const block of document.querySelectorAll(".record-fields blockquote")) {
  const target = targets.get(block.textContent);
  if (!target) continue;
  block.classList.add("found");
  block.addEventListener("click", () => target.scrollIntoView({ behavior: "smooth", block: "center" }));
}
