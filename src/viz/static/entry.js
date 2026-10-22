"use strict";
const media = document.getElementById("publisher-media");
if (media)
  PaperMedia.mount(
    media,
    { pmcid: media.dataset.pmcid, doi: media.dataset.doi },
    media.dataset.ref,
  );
window.addEventListener("pagehide", () => PaperMedia.dispose());
