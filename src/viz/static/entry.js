var ROOT = document.querySelector('meta[name="root"]').content;
"use strict";
const media = document.getElementById("publisher-media");
if (media)
  PaperMedia.mount(
    media,
    { pmcid: media.dataset.pmcid, doi: media.dataset.doi },
    media.dataset.ref,
  );
window.addEventListener("pagehide", () => PaperMedia.dispose());

(async () => {
  const host = document.getElementById("paper-text"),
    pane = document.querySelector(".paper"),
    status = document.getElementById("paper-status");
  if (!host || !pane) return;
  const evidence = JSON.parse(document.getElementById("evidence").textContent);
  const select = document.getElementById("paper-document");
  const normalize = (s) =>
    String(s ?? "")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]/gu, "");
  let docs = [],
    active = 0;
  const md = markdownit({ html: false, linkify: true });
  // Publication image paths point into the supplied archive, which is private.
  // Keep article figures as publisher links instead of exposing arbitrary files.
  md.renderer.rules.image = () =>
    '<span class="muted">[Figure in the original publisher article]</span>';
  function highlight() {
    for (const block of host.querySelectorAll("p,li")) {
      const text = normalize(block.textContent);
      if (
        evidence.some(
          (q) =>
            normalize(q.quote).length > 20 && text.includes(normalize(q.quote)),
        )
      )
        block.classList.add("quoted");
    }
  }
  function draw() {
    active = Number(select.value) || 0;
    host.innerHTML = md.render(
      docs[active].text.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, ""),
    );
    status.textContent =
      active === 0 && docs[active].main
        ? "Full article text from the publisher archive."
        : "Supplementary text from the publisher archive.";
    status.classList.add("sr-only");
    highlight();
    host.scrollTop = 0;
  }
  try {
    const response = await fetch(
      ROOT + "/api/paper-text?doi=" + encodeURIComponent(pane.dataset.doi),
    );
    if (!response.ok) throw Error("Text unavailable");
    const data = await response.json();
    if (data.main_text)
      docs.push({ name: "Article", text: data.main_text, main: true });
    for (const file of data.supplements || [])
      docs.push({ name: file.name, text: file.text, main: false });
    if (docs.length) {
      for (const [i, file] of docs.entries()) {
        const option = document.createElement("option");
        option.value = String(i);
        option.textContent = file.name;
        select.append(option);
      }
      select.parentElement.hidden = docs.length < 2;
      select.onchange = draw;
      draw();
    } else {
      status.textContent =
        "Only excerpts are shown; the full article text is not stored here.";
      highlight();
    }
  } catch {
    status.textContent =
      "Only excerpts are shown; the full article text could not be loaded.";
    highlight();
  }
  for (const quote of document.querySelectorAll(".record-fields blockquote")) {
    const find = () => {
      const text = normalize(quote.textContent);
      if (text.length < 20) return;
      let target = [...host.querySelectorAll("p,li")].find((node) =>
        normalize(node.textContent).includes(text),
      );
      if (!target && docs.length) {
        const i = docs.findIndex((doc) => normalize(doc.text).includes(text));
        if (i >= 0 && i !== active) {
          select.value = String(i);
          draw();
          target = [...host.querySelectorAll("p,li")].find((node) =>
            normalize(node.textContent).includes(text),
          );
        }
      }
      if (target) {
        target.classList.add("quoted");
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    };
    quote.classList.add("found");
    quote.onclick = find;
    quote.onkeydown = (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        find();
      }
    };
  }
})();
