// The server searches and paginates. The static export renders every entry on this page and
// marks the form with `data-static`, so the search runs here instead.
const form = document.querySelector("form.tools");
const hasCif = form.querySelector("[data-cif]");
const updateCifButton = () => {
  const pressed = form.cif.value === "1";
  hasCif.classList.toggle("on", pressed);
  hasCif.setAttribute("aria-pressed", String(pressed));
};
let controller, requestId = 0;
const cancelPending = () => {
  requestId++;
  controller?.abort();
  form.removeAttribute("aria-busy");
};
async function updateResults() {
  cancelPending();
  const id = requestId;
  controller = new AbortController();
  const url = new URL(form.action, location.href);
  url.search = new URLSearchParams(new FormData(form));
  form.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw Error("Could not filter entries");
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    if (id !== requestId) return;
    for (const selector of [".results-line", ".publisher-tiles", ".empty-state"])
      document.querySelector(selector).replaceWith(page.querySelector(selector));
    document.querySelector(".pagination")?.remove();
    const pagination = page.querySelector(".pagination");
    if (pagination) document.querySelector(".empty-state").after(pagination);
    history.replaceState(null, "", url);
  } catch (error) {
    if (id !== requestId || error.name === "AbortError") return;
    document.querySelector(".results-line").textContent =
      "Could not update results. Change a filter or press Enter to try again.";
  } finally {
    if (id === requestId) form.removeAttribute("aria-busy");
  }
}
hasCif.addEventListener("click", () => {
  form.cif.value = form.cif.value === "1" ? "0" : "1";
  updateCifButton();
  form.requestSubmit();
});
window.addEventListener("popstate", () => location.reload());
if (form.hasAttribute("data-static")) {
  const tiles = [...document.querySelectorAll(".tile")];
  const grid = tiles[0]?.parentElement;
  const line = document.querySelector(".results-line");
  const empty = document.querySelector(".empty-state");
  const apply = () => {
    const words = form.q.value.toLowerCase().split(/\s+/).filter(Boolean);
    const journal = form.journal.value, status = form.status.value;
    const shown = tiles.filter(
      (t) =>
        words.every((w) => t.dataset.search.includes(w)) &&
        (!status || t.dataset.status === status) &&
        (!journal || t.dataset.journal === journal) &&
        (form.cif.value === "0" || t.dataset.cif === "1"),
    );
    const byId = (a, b) => a.dataset.id.localeCompare(b.dataset.id);
    if (form.sort.value === "year")
      shown.sort((a, b) => b.dataset.year - a.dataset.year || byId(a, b));
    else shown.sort(byId);
    for (const t of tiles) t.style.display = "none";
    for (const t of shown) {
      t.style.display = "";
      grid.append(t);
    }
    line.textContent = `${shown.length.toLocaleString()} matching entries`;
    empty.hidden = shown.length > 0;
    updateCifButton();
  };
  const params = new URLSearchParams(location.search);
  for (const k of ["q", "journal", "status", "sort"])
    if (params.has(k)) form[k].value = params.get(k);
  // The page is exported with every entry (cif=0), but the filter is on by default.
  form.cif.value = params.get("cif") ?? "1";
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    history.replaceState(null, "", "?" + new URLSearchParams(new FormData(form)));
    apply();
  });
  apply();
}

else {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    updateResults();
  });
}
form.addEventListener("change", (event) => {
  if (event.target.tagName === "SELECT") form.requestSubmit();
});
