// The server searches and paginates. The static export renders every entry on this page and
// marks the form with `data-static`, so the search runs here instead.
const form = document.querySelector("form.tools");
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
        (!journal || t.dataset.journal === journal),
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
  };
  const params = new URLSearchParams(location.search);
  for (const k of ["q", "journal", "status", "sort"])
    if (params.has(k)) form[k].value = params.get(k);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    history.replaceState(null, "", "?" + new URLSearchParams(new FormData(form)));
    apply();
  });
  form.addEventListener("input", apply);
  apply();
}
