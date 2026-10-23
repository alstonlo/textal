---
title: TEXtal
emoji: 🧪
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
short_description: Crystal structures and their crystallization procedures
---

The website of the TEXtal dataset
([alstonlo/textal-data](https://huggingface.co/datasets/alstonlo/textal-data)).

The Docker build downloads and unpacks the dataset, indexes CIF availability, and renders
first-page previews. Container startup only starts the web server. Generated previews are
also cached on disk and in the browser; thumbnail work has a separate concurrency limit
so it does not occupy the worker pool used by pages and filters.

For a dataset update, set `DATASET_REVISION` in the Dockerfile to the dataset commit you want
to publish (or rebuild without the Docker cache when using `main`). Restarting an existing
image keeps its bundled dataset. Builds take longer and images are larger, but visitors no
longer wait for the dataset download and unpacking on each fresh container start.
