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
COPY --chown=user src/viz src/viz

ENV PYTHONPATH=/home/user/app/src TEXTAL_DATA=/home/user/data

# The dataset (3.3 GB) is downloaded at startup, not at build time, to keep the image small.
CMD hf download alstonlo/textal-data --repo-type dataset --local-dir "$TEXTAL_DATA" \
    && cd "$TEXTAL_DATA" && tar -xf texts.tar && tar -xf files.tar && rm texts.tar files.tar \
    && cd /home/user/app && exec uvicorn viz.app:app --host 0.0.0.0 --port 7860
