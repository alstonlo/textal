var ROOT = document.querySelector('meta[name="root"]').content;
/* Each iframe owns its 3Dmol instance, canvas and observers; removal destroys them together. */
"use strict";
(() => {
  const root = document.querySelector(".frame-root"),
    q = new URLSearchParams(location.search),
    esc = (v) =>
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
  const palette = {
    C: "#8C8C88",
    H: "#E4E4E0",
    N: "#3B4BC9",
    O: "#D9405C",
    S: "#F2B400",
    P: "#EB7A24",
    F: "#34B868",
    Cl: "#25A443",
    Br: "#9B2235",
    I: "#7A3BD0",
  };
  let data,
    viewer,
    model,
    active = true;
  const el = (c) => root.querySelector("." + c),
    on = (c) => el(c).getAttribute("aria-pressed") === "true";
  function frameSize() {
    parent.postMessage(
      { type: "crystal-frame-size", height: Math.ceil(root.scrollHeight + 5) },
      location.origin,
    );
  }
  function style() {
    if (!viewer) return;
    const colours = data.blocks[Number(el("cif-block").value)].viewer.colours,
      scheme = { prop: "elem", map: colours };
    for (let i = 0; i < 2; i++) {
      const opacity = i === 0 ? 1 : 0.4,
        visible = i === 0 || on("crystal-shell");
      viewer.setStyle(
        { model: i },
        visible
          ? {
              stick: { radius: 0.2, colorscheme: scheme, opacity },
              sphere: { scale: 0.2, colorscheme: scheme, opacity },
            }
          : {},
      );
    }
    if (!on("crystal-h")) viewer.setStyle({ elem: "H" }, {});
    viewer.render();
  }
  function draw() {
    try {
      const block = data.blocks[Number(el("cif-block").value)],
        g = block.viewer,
        packing = el("crystal-mode").value === "cell";
      viewer.spin(false);
      el("crystal-spin").textContent = "Rotate";
      el("crystal-spin").setAttribute("aria-pressed", "false");
      viewer.clear();
      viewer.removeAllShapes();
      viewer.removeAllLabels();
      model = viewer.addModel(
        packing ? g.xyz : block.text,
        packing ? "xyz" : "cif",
        { doAssembly: false },
      );
      viewer.addModel(packing ? g.shell_xyz : "0\n\n", "xyz");
      const point = (p) => ({ x: p[0], y: p[1], z: p[2] });
      if (on("crystal-cell")) {
        for (const [i, vec] of g.lattice.entries())
          viewer.addArrow({
            start: { x: 0, y: 0, z: 0 },
            end: point(vec),
            radius: 0.2,
            radiusRatio: 2,
            mid: 0.92,
            color: ["red", "green", "blue"][i],
          });
        for (const edge of g.edges)
          viewer.addCylinder({
            start: point(edge[0]),
            end: point(edge[1]),
            radius: 0.05,
            color: "#111111",
          });
      }
      style();
      viewer.zoomTo({ model: 0 });
      viewer.render();
      const count = model.selectedAtoms({}).length;
      el("crystal-info").textContent =
        `data_${block.name} · ${count} atoms · ${packing ? "whole molecules in the unit cell" : "asymmetric unit"}`;
      el("crystal-cell-info").textContent =
        `a ${block.cell[0]}, b ${block.cell[1]}, c ${block.cell[2]} Å; α ${block.cell[3]}, β ${block.cell[4]}, γ ${block.cell[5]}°`;
      parent.postMessage(
        {
          type: "crystal-frame-ready",
          pmcid: q.get("pmcid"),
          block: block.name,
          atoms: count,
        },
        location.origin,
      );
      frameSize();
    } catch (error) {
      el("crystal-info").textContent = "Could not render: " + error.message;
      console.error("Crystal render failed", error);
      frameSize();
    }
  }
  (async () => {
    try {
      const response = await fetch(
        ROOT + "/api/cif-models/" +
          encodeURIComponent(q.get("pmcid")) +
          "/" +
          encodeURIComponent(q.get("file")),
      );
      data = await response.json();
      if (!response.ok) throw Error(data.error || "CIF parsing failed");
      const toggle = (c, label, pressed) =>
        `<button type="button" class="chip ${pressed ? "on " : ""}${c}" aria-pressed="${pressed}">${label}</button>`;
      root.innerHTML = `<div class="tools"><select class="cif-block" aria-label="Structure block"${data.blocks.length > 1 ? "" : " hidden"}>${data.blocks.map((b, i) => `<option value="${i}">data_${esc(b.name)}</option>`).join("")}</select><select class="crystal-mode" aria-label="View"><option value="cell">Unit cell packing</option><option value="asu">Asymmetric unit</option></select><div class="chips">${toggle("crystal-shell", "Surroundings", false)}${toggle("crystal-h", "Hydrogens", true)}${toggle("crystal-cell", "Cell axes", true)}</div><div class="chips count">${toggle("crystal-spin", "Rotate", false)}<button type="button" class="chip crystal-reset">Reset view</button></div></div><div class="crystal-canvas" role="img" aria-label="Interactive crystal model: drag to rotate, scroll to zoom"></div><div class="viewer-foot"><p class="muted small crystal-info" role="status"></p><p class="muted small num crystal-cell-info"></p></div><p class="media-hint">Drag to rotate, scroll to zoom. The cell is drawn with its a, b and c axes in red, green and blue.</p>`;
      viewer = $3Dmol.createViewer(el("crystal-canvas"), {
        backgroundColor: "#ffffff",
        antialias: true,
      });
      for (const c of ["cif-block", "crystal-mode"]) el(c).onchange = draw;
      for (const [c, after] of [
        ["crystal-cell", draw],
        ["crystal-h", style],
        ["crystal-shell", style],
      ])
        el(c).onclick = () => {
          el(c).classList.toggle("on", !on(c));
          el(c).setAttribute("aria-pressed", String(on(c)));
          after();
        };
      el("crystal-reset").onclick = () => {
        viewer.zoomTo({ model: 0 });
        viewer.render();
      };
      el("crystal-spin").onclick = () => {
        const spin = el("crystal-spin").getAttribute("aria-pressed") !== "true";
        el("crystal-spin").setAttribute("aria-pressed", String(spin));
        el("crystal-spin").textContent = spin ? "Stop" : "Rotate";
        el("crystal-spin").classList.toggle("on", spin);
        viewer.spin(spin);
      };
      draw();
      new ResizeObserver(() => {
        if (active) {
          frameSize();
        }
      }).observe(root);
    } catch (error) {
      root.innerHTML = `<p class="media-empty">Could not render this CIF: ${esc(error.message)}. Use the original publisher download to inspect the structure.</p>`;
      console.error("CIF frame failed", error);
      frameSize();
    }
  })();
  window.addEventListener("pagehide", () => {
    active = false;
  });
})();
