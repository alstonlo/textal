/* Local journal assets. Crystal rendering runs in an isolated document per selected paper. */
"use strict";
window.PaperMedia = (() => {
  const esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const cache = new Map(),
    selections = new Map();
  let current = null,
    serial = 0;
  function dispose() {
    serial++;
    if (current) {
      current.abort.abort();
      current = null;
    }
  }
  async function mount(root, paper, ref) {
    if (!root) return;
    dispose();
    const token = serial,
      abort = new AbortController(),
      state = { root, abort, paper, ref, frame: null };
    current = state;
    root.innerHTML = `<section class="paper-media-section"><div class="media-section-head"><div><span class="small-label">PUBLISHER ASSETS · PMC OA</span><h3>Crystal & chemical scheme</h3></div><span class="media-asset-status" role="status">Loading publisher assets…</span></div><p class="media-scope">Publisher CIFs and chemical schemes from the downloaded article package. Files are paper-level assets; a structure block is not automatically assigned to the selected CSD refcode.</p><div class="media-panels"><section class="crystal-panel"><h4>Publisher CIF · interactive 3D</h4><div class="crystal-body"><p class="media-empty">Loading CIF files…</p></div></section><section class="figure-panel"><h4>Chemical scheme</h4><div class="figure-body"><p class="media-empty">Loading publisher chemical schemes…</p></div></section></div><details class="media-provenance"><summary>Publisher file provenance</summary><div class="media-provenance-body"></div></details></section>`;
    const status = root.querySelector(".media-asset-status");
    if (!paper.pmcid) {
      status.textContent = "No PMC archive link";
      root.querySelector(".crystal-body").innerHTML =
        '<p class="media-empty">This paper has no linked downloaded PMC package.</p>';
      root.querySelector(".figure-body").innerHTML =
        '<p class="media-empty">No saved package is available to resolve its chemical scheme.</p>';
      return;
    }
    try {
      let data = cache.get(paper.pmcid);
      if (!data) {
        const response = await fetch(
          "/api/paper-assets/" + encodeURIComponent(paper.pmcid),
          { signal: abort.signal },
        );
        data = await response.json();
        if (!response.ok)
          throw Error(data.error || "Could not load saved assets");
        cache.set(paper.pmcid, data);
      }
      if (token !== serial) return;
      state.data = data;
      state.schemes = data.figures.filter((f) => f.kind === "chemical_scheme");
      status.textContent = `${data.cifs.length} CIF ${data.cifs.length === 1 ? "file" : "files"} · ${state.schemes.length} chemical ${state.schemes.length === 1 ? "scheme" : "schemes"} · cached locally`;
      renderCrystal(state);
      renderScheme(state);
      root.querySelector(".media-provenance-body").innerHTML =
        `<p>Original file bytes were checked against the archive’s SHA256 receipts. Gemmi parses the original CIF into coordinates, elements, occupancies, unit cell and symmetry operators for 3Dmol display. Safe internal atom labels prevent browser-parser errors; original labels and all original download bytes are preserved.</p>${[...data.cifs, ...state.schemes].map((f) => `<div><strong>${esc(f.name)}</strong><p class="source-path">${esc(f.source_url)}<br>SHA256 ${esc(f.sha256)}</p></div>`).join("")}`;
    } catch (error) {
      if (token !== serial || error.name === "AbortError") return;
      status.textContent = "Assets unavailable";
      root.querySelector(".crystal-body").innerHTML =
        `<p class="media-empty">${esc(error.message)}</p><button class="button media-retry">Retry assets</button>`;
      root.querySelector(".figure-body").innerHTML =
        '<p class="media-empty">The scheme will load when this paper’s archive can be read.</p>';
      root.querySelector(".media-retry").onclick = () =>
        mount(root, paper, ref);
    }
  }
  function renderCrystal(state) {
    const host = state.root.querySelector(".crystal-body"),
      files = state.data.cifs;
    if (!files.length) {
      host.innerHTML =
        '<p class="media-empty">No coordinate-bearing CIF was found in this saved package.</p>';
      return;
    }
    host.innerHTML = `<label class="figure-select">CIF file<select class="cif-file">${files.map((f, i) => `<option value="${i}">${esc(f.name)}</option>`).join("")}</select></label><iframe class="crystal-frame" title="Interactive publisher CIF crystal viewer"></iframe><div class="crystal-downloads"></div><p class="media-hint">Paper-level CIF. Choose the appropriate structure block when the file contains multiple compounds or forms. Displayed bonds are inferred from coordinates.</p>`;
    const choice = host.querySelector(".cif-file");
    choice.value = Math.min(
      selections.get(state.paper.pmcid) || 0,
      files.length - 1,
    );
    state.frame = host.querySelector("iframe");
    function show() {
      const i = Number(choice.value),
        f = files[i],
        query = new URLSearchParams({
          pmcid: state.paper.pmcid,
          file: f.cache_name,
        });
      state.frame.style.height = "640px";
      state.frame.src = "/crystal-frame.html?" + query;
      selections.set(state.paper.pmcid, i);
      host.querySelector(".crystal-downloads").innerHTML =
        `<a class="button" href="${esc(f.local_url)}" download="${esc(f.name)}">↓ Original publisher CIF</a><span>${(f.bytes / 1000).toFixed(1)} kB</span>`;
    }
    choice.onchange = show;
    show();
  }
  function renderScheme(state) {
    const host = state.root.querySelector(".figure-body"),
      figs = state.schemes;
    if (!figs.length) {
      host.innerHTML =
        '<p class="media-empty">No publisher chemical scheme was found in this saved package.</p>';
      return;
    }
    host.innerHTML = `${figs.length > 1 ? `<label class="figure-select">Chemical scheme<select>${figs.map((f, i) => `<option value="${i}">${esc(f.name)}</option>`).join("")}</select></label>` : ""}<figure class="publisher-figure"></figure>`;
    const choice = host.querySelector("select");
    function show() {
      const f = figs[choice ? Number(choice.value) : 0];
      host.querySelector(".publisher-figure").innerHTML =
        `<a href="${esc(f.local_url)}" target="_blank" rel="noopener" title="Open original chemical scheme"><img src="${esc(f.local_url)}" alt="Publisher chemical scheme"></a><figcaption><span>${esc(f.name)}</span></figcaption><a class="button" href="${esc(f.local_url)}" download="${esc(f.name)}">↓ Original chemical scheme</a>`;
    }
    if (choice) choice.onchange = show;
    show();
  }
  window.addEventListener("message", (event) => {
    if (
      event.origin !== location.origin ||
      !current?.frame ||
      event.source !== current.frame.contentWindow
    )
      return;
    if (event.data?.type === "crystal-frame-size") {
      const height = Number(event.data.height);
      if (Number.isFinite(height))
        current.frame.style.height =
          Math.max(480, Math.min(height, 1000)) + "px";
    }
  });
  return { mount, dispose };
})();
