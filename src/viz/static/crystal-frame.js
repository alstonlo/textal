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
  const el = (c) => root.querySelector("." + c);
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
        visible = i === 0 || el("crystal-shell").checked;
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
    if (!el("crystal-h").checked) viewer.setStyle({ elem: "H" }, {});
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
      if (el("crystal-cell").checked) {
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
        `data_${block.name} · ${count} parsed atoms · ${packing ? "whole molecules in unit cell" : "asymmetric unit"}`;
      el("crystal-cell-info").textContent =
        `a ${block.cell[0]}, b ${block.cell[1]}, c ${block.cell[2]} Å · α ${block.cell[3]}, β ${block.cell[4]}, γ ${block.cell[5]}°`;
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
        "/api/cif-models/" +
          encodeURIComponent(q.get("pmcid")) +
          "/" +
          encodeURIComponent(q.get("file")),
      );
      data = await response.json();
      if (!response.ok) throw Error(data.error || "CIF parsing failed");
      root.innerHTML = `<label class="figure-select">Structure block<select class="cif-block">${data.blocks.map((b, i) => `<option value="${i}">data_${esc(b.name)}</option>`).join("")}</select></label><div class="crystal-controls"><label>View<select class="crystal-mode"><option value="cell">Crystal packing · unit cell</option><option value="asu">Asymmetric unit</option></select></label><label><input type="checkbox" class="crystal-shell"> Surroundings</label><label><input type="checkbox" class="crystal-h" checked> Hydrogens</label><label><input type="checkbox" class="crystal-cell" checked> Cell axes</label><button class="button crystal-reset">Reset</button><button class="button crystal-spin" aria-pressed="false">Rotate</button></div><div class="crystal-canvas" role="img" aria-label="Interactive crystal model: drag to rotate, scroll to zoom"></div><p class="crystal-info" role="status"></p><p class="crystal-cell-info"></p><p class="media-hint">Drag to rotate · scroll to zoom. Axes: a red, b green, c blue.</p>`;
      viewer = $3Dmol.createViewer(el("crystal-canvas"), {
        backgroundColor: "#ffffff",
        antialias: true,
      });
      for (const c of ["cif-block", "crystal-mode", "crystal-cell"])
        el(c).onchange = draw;
      el("crystal-h").onchange = style;
      el("crystal-shell").onchange = style;
      el("crystal-reset").onclick = () => {
        viewer.zoomTo({ model: 0 });
        viewer.render();
      };
      el("crystal-spin").onclick = () => {
        const spin = el("crystal-spin").getAttribute("aria-pressed") !== "true";
        el("crystal-spin").setAttribute("aria-pressed", String(spin));
        el("crystal-spin").textContent = spin ? "Stop rotation" : "Rotate";
        viewer.spin(spin);
      };
      draw();
      new ResizeObserver(() => {
        if (active) {
          frameSize();
        }
      }).observe(root);
    } catch (error) {
      root.innerHTML = `<p class="media-empty">Could not render: ${esc(error.message)}</p><p>Use the original CIF download to inspect this structure.</p>`;
      console.error("CIF frame failed", error);
      frameSize();
    }
  })();
  window.addEventListener("pagehide", () => {
    active = false;
  });
})();
