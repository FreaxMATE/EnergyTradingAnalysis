# Energy Trading Analysis

![Dashboard Screenshot](screenshot.png)

Download, analyze, and publish ENTSO-E day-ahead spot prices (and generation mix) per bidding zone/country, with computed features (moving average + Holt‑Winters forecasts) and static HTML dashboards.

Core entry points:
- CLI: [`main.main`](src/main.py) in [src/main.py](src/main.py)
- Data pipeline: [`datamanager.DataManager`](src/datamanager.py) in [src/datamanager.py](src/datamanager.py)
- Analyses: [`analysis.MovingAverageAnalyzer`](src/analysis.py), [`analysis.ForecastAnalyzer`](src/analysis.py), orchestrated by [`analysis.AnalysisRunner`](src/analysis.py) in [src/analysis.py](src/analysis.py)
- Static reporting: [`plot_bokeh.create_static_dashboard`](src/plot_bokeh.py) + [`plot_bokeh.generate_index_html`](src/plot_bokeh.py) in [src/plot_bokeh.py](src/plot_bokeh.py)

---

## What it does

1. **Downloads data from ENTSO-E**
   - Spot prices per country code via `EntsoePandasClient` inside [`datamanager.DataManager.download`](src/datamanager.py) → [`datamanager.DataManager.download_by_country_code`](src/datamanager.py).
   - Generation mix per country code via [`datamanager.DataManager.download_generation_by_country_code`](src/datamanager.py).

2. **Stores data on disk**
   - Price data is loaded with CSV schema `time, price` by [`datamanager.DataManager.__read_data`](src/datamanager.py).
   - Features are saved as `{country}_{feature}.csv` by [`datamanager.DataManager.save_analysis`](src/datamanager.py) and discovered via [`datamanager.DataManager.__read_features`](src/datamanager.py).
   - `data/features.csv` is (re)generated with `ma` and `forecast` columns by [`datamanager.DataManager.__update_features_file`](src/datamanager.py).

3. **Runs analyses**
   - Moving average feature `ma` via [`analysis.MovingAverageAnalyzer.analyze`](src/analysis.py).
   - Forecast feature(s) via Holt‑Winters exponential smoothing in [`analysis.ForecastAnalyzer.analyze`](src/analysis.py).

4. **Generates static HTML reports**
   - Per-country report: [`plot_bokeh.create_static_dashboard`](src/plot_bokeh.py) (Bokeh, WebGL, downsampling).
   - Dashboard index that links all reports: [`plot_bokeh.generate_index_html`](src/plot_bokeh.py).

---

## Repository layout (high-level)

- Source code: [src/](src/)
  - Data pipeline: [src/datamanager.py](src/datamanager.py)
  - Analysis: [src/analysis.py](src/analysis.py)
  - Static reporting: [src/plot_bokeh.py](src/plot_bokeh.py)
  - Config: [src/config.py](src/config.py)
  - Utilities: [src/utils.py](src/utils.py)
  - Logging: [src/logger.py](src/logger.py)
  - Exceptions: [src/exceptions.py](src/exceptions.py)
- Data (CSV): [data/](data/)
- Generated static site output directory (configured): [doc/](doc/) via `OUTPUT_DIR` in [src/config.py](src/config.py)
- Prebuilt/served static site directory (also present): [docs/](docs/) and [Dockerfile](Dockerfile)

Note: both [doc/](doc/) and [docs/](docs/) exist. `OUTPUT_DIR` is set to `doc/` in [src/config.py](src/config.py), while the [Dockerfile](Dockerfile) copies `docs/` into nginx. If you want Docker to serve newly generated reports, ensure the generated output ends up in the directory being served.

---

## Requirements

- Python **3.8+** (setup script enforces this) — see [scripts/setup.sh](scripts/setup.sh) and [scripts/setup.bat](scripts/setup.bat)
- An **ENTSOE API key** (see configuration below)
- Python dependencies in [requirements.txt](requirements.txt) (also Nix dev shell in [flake.nix](flake.nix))

---

## Configuration

This project expects an ENTSO-E API key via environment variables.

- `.env.example` shows the expected shape: [.env.example](.env.example)
- Local overrides: `.env` (not committed) — [.env](.env)
- Config validation happens in [src/config.py](src/config.py). Missing key raises [`exceptions.ConfigException`](src/exceptions.py).

Required:
- `ENTSOE_API_KEY`: ENTSO-E Transparency Platform API key (used by `EntsoePandasClient` inside [`datamanager.DataManager.download`](src/datamanager.py)).

---

## Quickstart (venv)

### 1) Create and install
Use the provided scripts:

```sh
./scripts/setup.sh
```

Windows:

```bat
scripts\setup.bat
```

(They create `venv/` and install from [requirements.txt](requirements.txt).)

### 2) Set your ENTSO-E key
Create `.env` at repo root (or export env var):

```sh
export ENTSOE_API_KEY="your_key_here"
```

### 3) Download data
Runs ENTSO-E pulls for all configured country codes:

```sh
python src/main.py download
```

This calls [`datamanager.DataManager.download`](src/datamanager.py), which iterates `country_codes.csv` (see `COUNTRY_CODES_FILE` in [src/config.py](src/config.py)).

### 4) Analyze data
Computes moving average + forecasts per country:

```sh
python src/main.py analyze
```

This calls [`datamanager.DataManager.analysis`](src/datamanager.py) → [`datamanager.DataManager.analysis_by_country_code`](src/datamanager.py), using [`analysis.AnalysisRunner`](src/analysis.py) with [`analysis.MovingAverageAnalyzer`](src/analysis.py) and [`analysis.ForecastAnalyzer`](src/analysis.py).

### 5) Generate static dashboards
Generate per-country reports and the index dashboard:

```sh
python src/plot_bokeh.py
```

Outputs:
- `report_{COUNTRY}.html` files into `OUTPUT_DIR` (configured as `doc/`) in [src/config.py](src/config.py)
- `index.html` dashboard via [`plot_bokeh.generate_index_html`](src/plot_bokeh.py)

Open in a browser:
- [doc/index.html](doc/index.html)

---

## Data & file conventions

### Prices
- Loaded by [`datamanager.DataManager.__read_data`](src/datamanager.py) as:
  - `time` (UTC parsed), `price`

### Features
- Written by [`datamanager.DataManager.save_analysis`](src/datamanager.py) to per-country files:
  - `{country}_ma.csv` (moving average output includes `ma`)
  - `{country}_forecast.csv` (forecast output contains multiple forecast columns)
- Registry file: `data/features.csv` maintained by [`datamanager.DataManager.__update_features_file`](src/datamanager.py)

### Utilities used by the pipeline
- Efficient incremental download uses [`utils.read_last_csv_line`](src/utils.py) (reads last CSV line) in [`datamanager.DataManager.download_by_country_code`](src/datamanager.py).
- Time-window extraction helper: [`utils.extract_last`](src/utils.py) in [src/utils.py](src/utils.py).

---

## Development environments

### Nix dev shell
A ready dev shell is defined in [flake.nix](flake.nix) (includes `entsoe-py`, pandas, statsmodels, bokeh, etc.).

### Docker (static site)
The provided [Dockerfile](Dockerfile) serves static files through nginx and copies [docs/](docs/) into the container. If you want to serve the freshly generated content from [doc/](doc/), align the directories (either generate into `docs/` or serve `doc/`).

See also: [docker-compose.yml](docker-compose.yml).

---

## Logging & troubleshooting

- Logging is configured by [`logger.setup_logger`](src/logger.py) in [src/logger.py](src/logger.py) to both console and rotating files under [logs/](logs/).
- Common failures:
  - Missing `ENTSOE_API_KEY` → [`exceptions.ConfigException`](src/exceptions.py) raised by [src/config.py](src/config.py).
  - Empty/malformed CSV → [`exceptions.DataException`](src/exceptions.py) used by [`utils.read_last_csv_line`](src/utils.py) and [`utils.extract_last`](src/utils.py).

---

## License

Licensed under **GNU GPL v3.0** — see [LICENSE](LICENSE).