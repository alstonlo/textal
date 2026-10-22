// The paper, from its Markdown, with the extraction's evidence quotes highlighted.
const md = document.getElementById("paper-md").textContent;
const paper = document.getElementById("paper-text");
if (md.trim()) paper.innerHTML = markdownit({ html: false, linkify: true }).render(md);

const quotes = JSON.parse(document.getElementById("evidence").textContent).map((e) => e.quote).filter(Boolean);
const walker = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
const nodes = [];
while (walker.nextNode()) nodes.push(walker.currentNode);
for (const node of nodes) {
  const hit = quotes.find((qt) => node.data.includes(qt));
  if (!hit) continue;
  const [before, after] = node.data.split(hit, 2);
  const mark = document.createElement("mark");
  mark.textContent = hit;
  node.replaceWith(before, mark, after);
}
