# Development

This file keeps maintainer and local-reference commands used to run, rebuild, measure,
verify, and package the Dash Precompute example. Generated source data and artifact
bundles under `.data/` and `artifacts/` are intentionally ignored by Git.

## Run a local bundle

Install the application and development dependencies:

```shell
uv sync --extra dev
```

Run the application against a locally built bundle:

```shell
uv run dash-precompute-serve --artifacts artifacts
```

Open `http://127.0.0.1:8050`. `DASH_PRECOMPUTE_ARTIFACTS` can supply the artifact
directory instead of the command-line argument.

## Build from prepared tables

Source acquisition is deliberately outside this reference. Build a bundle from tables
that satisfy the validated prepared-data contract:

```shell
uv run dash-precompute-build \
  --profile /path/to/regional_profile.parquet \
  --population-history /path/to/regional_population_history.parquet \
  --unemployment-history /path/to/regional_unemployment_history.parquet \
  --income-history /path/to/regional_income_history.parquet \
  --life-expectancy-history /path/to/regional_life_expectancy_history.parquet \
  --age-structure /path/to/regional_age_structure.parquet \
  --country-density /path/to/country_population_density_distribution.parquet \
  --source-manifest /path/to/oecd-source-manifest.json \
  --source-manifest /path/to/ghsl-source-manifest.json \
  --output artifacts
```

## Measure and verify

```shell
uv run python scripts/benchmark_runtime.py
uv run pytest
uv run ruff check .
```

For changes to callbacks, layout, figures, CSS, or JavaScript, also exercise country and
region selection, reset, all eight charts, expansion, desktop and mobile widths,
version-triggered reload, and the browser console.

## Build a container

The image packages `current.json` and exactly one immutable bundle. Source acquisition
does not occur during container startup. The staging command excludes the build-only
Parquet reader and recreates the ignored `.docker/` directory on each run.

```shell
uv run python scripts/stage_container_build.py
PLACE_TWINS_BUILD=$(uv run python -c \
  'import json; print(json.load(open("artifacts/current.json"))["manifest"].split("/")[1])')
docker build \
  --build-arg PLACE_TWINS_BUILD="$PLACE_TWINS_BUILD" \
  --tag place-twins:local .
docker run --rm --publish 8080:8080 place-twins:local
```
