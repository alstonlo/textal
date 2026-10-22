const cards = [...document.querySelectorAll(".tile")];
const grid = document.getElementById("cards");
const q = document.getElementById("q");
const sort = document.getElementById("sort");
const count = document.getElementById("count");
let form = document.querySelector(".chip.on").dataset.form;

function apply() {
  const needle = q.value.trim().toLowerCase();
  let shown = 0;
  for (const c of cards) {
    const ok = (!needle || c.dataset.search.includes(needle)) && (!form || c.dataset.forms.split(" ").includes(form));
    c.classList.toggle("hide", !ok);
    shown += ok;
  }
  count.textContent = shown === cards.length ? `${shown} entries` : `${shown} of ${cards.length} entries`;
  const key = sort.value;
  cards.sort((a, b) =>
    key === "year" ? b.dataset.year - a.dataset.year : a.dataset[key].localeCompare(b.dataset[key])
  );
  grid.append(...cards);
}

q.addEventListener("input", apply);
sort.addEventListener("change", apply);
document.getElementById("toggles").addEventListener("click", (ev) => {
  const t = ev.target.closest(".chip");
  if (!t) return;
  form = t.dataset.form;
  for (const c of t.parentElement.children) c.classList.toggle("on", c === t);
  history.replaceState(null, "", form ? `?form=${form}` : location.pathname);
  apply();
});
apply();
