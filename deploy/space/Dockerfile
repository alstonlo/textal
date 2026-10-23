FROM python:3.12-slim

# Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

RUN pip install --no-cache-dir --user \
    fastapi==0.156.4 \
    uvicorn==0.54.0 \
    jinja2==3.1.6 \
    plotly==7.1.0 \
    gemmi==0.7.5 \
    numpy==2.3.5 \
    py3Dmol==2.5.4 \
    polars==2.0.0 \
    huggingface_hub==2.2.0
ENV PYTHONPATH=/home/user/app/src TEXTAL_DATA=/home/user/data

# Keep downloads and extraction out of container startup. Pin a dataset commit
# with this build argument when publishing a new data release.
ARG DATASET_REVISION=main
RUN hf download alstonlo/textal-data \
        entries.parquet papers.parquet snapshot.json texts.tar files.tar \
        --repo-type dataset --revision "$DATASET_REVISION" --local-dir "$TEXTAL_DATA" \
    && cd "$TEXTAL_DATA" && tar -xf texts.tar && tar -xf files.tar && rm texts.tar files.tar

COPY --chown=user src/viz src/viz
# Bake the CIF index and first-page previews into the image, too.
RUN python -m viz.prewarm

CMD ["uvicorn", "viz.app:app", "--host", "0.0.0.0", "--port", "7860"]
