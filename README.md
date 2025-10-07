# Energy Trading Day-Ahead Price Analysis

A Python-based tool for optimizing energy procurement strategies using Danish day-ahead electricity prices (DK2). Analyzes optimal timing and frequency of energy purchases to minimize total procurement costs.

## 📊 Features

- **Historical Price Analysis**: Processes 3 years of hourly electricity price data (2023-2025)
- **Procurement Optimization**: Implements adaptive procurement algorithm with configurable parameters
- **Cost Analysis**: Compares total costs across different procurement frequencies (1-24 times per year)
- **Visualization**: Generates comprehensive charts showing price trends and optimal purchase points

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ (Windows, macOS, Linux)
- Git (optional)

### Installation

**Simple Setup:**
```bash
git clone <repository-url>
cd EnergyTradingAnalysis
pip install -r requirements.txt
```

**Alternative Methods:**
- **Automated**: Run `./scripts/setup.sh` (Linux/macOS) or `scripts\setup.bat` (Windows)
- **Conda**: `conda env create -f environment.yml && conda activate energy-trading-analysis`
- **Docker**: `docker-compose up --build`
- **Nix**: `nix develop` (Linux/macOS)

### Running the Analysis

Run the analysis scripts from the `src/` directory (they use relative paths to `../data` and `../output`):

```bash
cd src
python scheduled_procurement.py    # scheduling analysis + day-ahead trend plot
python day_prices.py               # hourly profile (price by hour) plot
```

**Generated Output:**
- `output/dayaheadprices.png`: Price trends with optimal purchase points (produced by `scheduled_procurement.py`)
- `output/total_cost_vs_nproc.png`: Total cost vs number of procurements (produced by `scheduled_procurement.py`)
- `output/price_by_hour.png`: Average price by hour with error bars (produced by `day_prices.py`)

## 📁 Project Structure

```
├── src/                     # Analysis scripts
│   ├── scheduled_procurement.py  # scheduling analysis + main price trend plot
│   └── day_prices.py             # hourly price profile and plot
├── data/                    # CSV price data files (2023-2025)
├── output/                  # Generated visualizations (PNG files)
├── scripts/                 # Setup scripts for different platforms
├── requirements.txt         # Python dependencies
└── environment.yml          # Conda environment
```

## 🔬 Algorithm Overview

**Data Source**: [ENTSO-E Transparency Platform](https://newtransparency.entsoe.eu/)
- Market: DK2 (Denmark Eastern) day-ahead prices
- Resolution: Hourly data, converted to daily averages
- Period: 2023-2025

**Procurement Strategy (`sched_proc` function):**
1. **Time Partitioning**: Divides the year into `n_parts` equal segments
2. **Reference Tracking**: Maintains reference price that updates to lower values
3. **Purchase Trigger**: Buys energy when price exceeds `reference + limit` (default: €10/MWh)
4. **Cost Calculation**: Computes total cost for specified energy volume (default: 1000 MWh)

**Parameters:**
- `mwhs`: Total energy to procure (default: 1000 MWh)
- `n_parts`: Number of procurement periods (tested: 1, 2, 3, 4, 6, 12, 24)
- `limit`: Price increase threshold (default: €10/MWh)

## 📈 Key Results

- **Optimal Frequency**: Usually 3-6 procurements per year minimize total costs
- **Cost Savings**: Significant reduction compared to single annual purchase
- **Seasonal Patterns**: Purchase timing typically aligns with seasonal price cycles
- **Diminishing Returns**: Increased procurement frequency shows diminishing cost benefits

## 🛠️ Usage Examples

**Basic Analysis:**
```python
buy_indices, total_cost = sched_proc(price_avg)
```

**Custom Parameters:**
```python
buy_indices, total_cost = sched_proc(
    price=price_avg, 
    mwhs=2000,      # 2000 MWh total
    n_parts=6,      # 6 procurements per year
    limit=15        # €15/MWh threshold
)
```

## 🔧 Troubleshooting

**Common Issues:**
- Ensure Python 3.8+ is installed
- Activate virtual environment before running
- Use `python3` if `python` points to Python 2.x
- On Linux/macOS: `chmod +x scripts/setup.sh` if permission denied

## 📄 License

Educational and research use. Price data from ENTSO-E under their terms of use.

## 📸 Plots (output/)

The repository includes example generated visualizations in the `output/` directory. If you run the scripts above they will be (re)created.

- dayaheadprices.png

![Day-ahead prices with procurement points](output/dayaheadprices.png)

Caption: Daily-averaged day-ahead prices with procurement markers for different numbers of procurements (N_proc). Each marker shows the time and price where the algorithm decided to buy — useful to inspect timing and clustering of purchase points.

- total_cost_vs_nproc.png

![Total cost vs number of procurements](output/total_cost_vs_nproc.png)

Caption: Total procurement cost (€) as a function of the number of procurements per year. Use this to identify the procurement frequency that minimizes total cost.

- price_by_hour.png

![Average price by hour](output/price_by_hour.png)

Caption: Average day-ahead price by hour-of-day with error bars (standard deviation). Highlights intraday patterns and hours with highest/lowest average prices.