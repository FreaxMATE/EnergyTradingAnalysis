# Energy Trading Day-Ahead Price Analysis & Procurement Optimization

A Python-based analysis tool for modeling energy procurement strategies using day-ahead electricity prices from the Danish market (DK2 - Eastern Denmark). This project analyzes optimal timing and frequency of energy purchases to minimize total costs.

## 📊 Project Overview

This project implements and visualizes different energy procurement strategies by analyzing historical day-ahead electricity prices from the ENTSO-E Transparency Platform. The main focus is on optimizing the number and timing of energy purchases throughout the year to minimize total procurement costs.

### Key Features

- **Historical Price Analysis**: Processes 3 years of hourly electricity price data (2023-2025)
- **Procurement Strategy Optimization**: Implements an adaptive procurement algorithm
- **Cost Analysis**: Compares total costs across different procurement frequencies
- **Data Visualization**: Generates comprehensive charts showing price trends and optimal purchase points

## 🚀 Quick Start

### Prerequisites

- Python 3.8+ (any platform: Windows, macOS, Linux)
- Git (optional, for cloning)

### Installation Options

#### Option 1: Automated Setup (Recommended)

**Linux/macOS:**
```bash
git clone <repository-url>
cd EnergyTradingAnalysis
./scripts/setup.sh
```

**Windows:**
```cmd
git clone <repository-url>
cd EnergyTradingAnalysis
scripts\setup.bat
```

#### Option 2: Manual Setup

1. **Clone or download** this repository
2. **Create virtual environment:**
   ```bash
   python -m venv venv
   ```
3. **Activate virtual environment:**
   - Linux/macOS: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate` (or `venv\Scripts\activate.bat`)
4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

#### Option 3: Using Conda

```bash
conda env create -f environment.yml
conda activate energy-trading-analysis
```

#### Option 4: Using Nix (Linux/macOS)

```bash
nix develop  # or nix-shell if using legacy Nix
```

#### Option 5: Using Docker (All platforms)

```bash
# Build and run
docker build -t energy-analysis .
docker run -v $(pwd):/app energy-analysis

# Or use Docker Compose
docker-compose up --build
```

### Running the Analysis

**After setup:**
```bash
# Run the analysis
cd src && python modelling.py
```

**Output:**
- Load and process the price data from CSV files
- Run procurement optimization for different strategies
- Generate two visualization files:
  - `dayaheadprices.png`: Price trends with optimal purchase points
  - `total_cost_vs_nproc.png`: Cost comparison across procurement frequencies

## 📁 Project Structure

```
├── src/                     # Source code
│   └── modelling.py         # Main analysis script
├── data/                    # Data files
│   ├── price_dk_2023.csv    # 2023 price data
│   ├── price_dk_2024.csv    # 2024 price data
│   ├── price_dk_2025.csv    # 2025 price data
│   └── spotprice_2024_2025.csv
├── output/                  # Generated outputs
│   ├── dayaheadprices.png   # Price trends visualization
│   └── total_cost_vs_nproc.png # Cost analysis chart
├── scripts/                 # Setup and utility scripts
│   ├── setup.sh            # Linux/macOS setup script
│   └── setup.bat           # Windows setup script
├── requirements.txt         # Python dependencies
├── environment.yml          # Conda environment specification
├── pyproject.toml          # Modern Python project configuration
├── Dockerfile             # Docker container configuration
├── docker-compose.yml     # Docker Compose configuration
├── flake.nix              # Nix development environment
├── flake.lock             # Nix lock file
├── .gitignore             # Git ignore rules
├── dayaheadprices.png     # Generated: Price analysis chart
├── total_cost_vs_nproc.png # Generated: Cost optimization chart
└── README.md              # This file
```

## 📈 Data Source

**Data Provider**: [ENTSO-E Transparency Platform](https://newtransparency.entsoe.eu/)

**Market Details**:
- **Market**: Day-ahead Prices (DAM)
- **Bidding Zone**: DK2 (Denmark - Eastern)  
- **Time Zone**: CET/CEST
- **Resolution**: Hourly data
- **Period**: 2023-2025

## 🔬 Algorithm Description

### Procurement Strategy (`sched_proc` function)

The core algorithm implements an adaptive procurement strategy:

1. **Time Partitioning**: Divides the time period into `n_parts` equal segments
2. **Reference Tracking**: Maintains a reference price that updates to lower values
3. **Trigger Logic**: Purchases energy when price exceeds `reference + limit`
4. **Cost Calculation**: Computes total cost for the specified energy volume (default: 1000 MWh)

**Parameters**:
- `mwhs`: Total energy to procure (default: 1000 MWh)
- `n_parts`: Number of procurement periods (tested: 1, 2, 3, 4, 6, 12, 24)
- `limit`: Price increase threshold for triggering purchases (default: €10/MWh)

### Analysis Features

- **Daily Averaging**: Converts hourly data to daily averages using 24-hour moving window
- **Multi-Strategy Comparison**: Tests procurement frequencies from 1 to 24 times per year
- **Cost Optimization**: Identifies optimal procurement frequency to minimize total costs

## 📊 Generated Visualizations

### 1. Day-Ahead Price Analysis (`dayaheadprices.png`)
- Time series of daily average electricity prices
- Optimal purchase points for different procurement strategies
- Color-coded markers showing purchase timing for each strategy

### 2. Cost Optimization Chart (`total_cost_vs_nproc.png`)
- Total procurement costs vs. number of procurement periods
- Helps identify the optimal procurement frequency
- Shows diminishing returns of increased procurement frequency

## 🛠️ Cross-Platform Compatibility

### Supported Platforms
- ✅ **Linux** (Ubuntu, Debian, RHEL, etc.)
- ✅ **macOS** (Intel & Apple Silicon)
- ✅ **Windows** (10/11, WSL)

### Development Environments

**Virtual Environment (All platforms):**
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

**Conda (All platforms):**
```bash
conda env create -f environment.yml
conda activate energy-trading-analysis
```

**Nix (Linux/macOS):**
```bash
nix develop  # Modern Nix with flakes
# or
nix-shell    # Legacy Nix
```

**Docker (All platforms):**
```bash
# Build and run with Docker
docker build -t energy-analysis .
docker run -v $(pwd)/output:/app/output energy-analysis

# Or use Docker Compose
docker-compose up --build
```

### Platform-Specific Notes

**Windows:**
- Use Command Prompt, PowerShell, or Git Bash
- WSL (Windows Subsystem for Linux) fully supported
- Python from Microsoft Store or python.org both work

**macOS:**
- Works with system Python or Homebrew Python
- Both Intel and Apple Silicon Macs supported
- Xcode Command Line Tools may be required

**Linux:**
- Most distributions supported
- Use system package manager for Python if needed
- Virtual environments recommended for isolation

## 📋 Usage Examples

### Basic Analysis
```python
# Run with default parameters (1000 MWh, 4 procurements, €10 limit)
buy_indices, total_cost = sched_proc(price_avg)
```

### Custom Parameters
```python
# Custom energy volume and procurement frequency
buy_indices, total_cost = sched_proc(
    price=price_avg, 
    mwhs=2000,      # 2000 MWh total
    n_parts=6,      # 6 procurements per year
    limit=15        # €15/MWh price increase limit
)
```

## 📊 Sample Results

The analysis typically shows:
- **Optimal Procurement Frequency**: Usually 3-6 times per year
- **Cost Savings**: Significant reduction compared to single annual purchase
- **Seasonal Patterns**: Purchase timing often aligns with seasonal price cycles

## 🔧 Troubleshooting

### Common Issues

**Import Errors:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

**Python Version Issues:**
- Ensure Python 3.8+ is installed
- Use `python3` command if `python` points to Python 2.x

**Permission Issues (Linux/macOS):**
```bash
chmod +x setup.sh
```

**Windows Path Issues:**
- Use Git Bash for Unix-like commands
- Or use the provided `.bat` script for native Windows

### Platform-Specific Installation

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

**macOS (with Homebrew):**
```bash
brew install python
```

**Windows:**
- Download from [python.org](https://www.python.org/downloads/)
- Or install via Microsoft Store
- Or use Anaconda/Miniconda

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Additional procurement strategies
- Risk analysis and volatility metrics  
- Integration with other European bidding zones
- Real-time data integration
- Machine learning price prediction

### Development Setup
1. Fork the repository
2. Run setup script for your platform
3. Make changes and test across platforms
4. Submit a pull request

## 📄 License

This project is provided as-is for educational and research purposes. Price data is sourced from ENTSO-E under their terms of use.

## 🚀 Deployment

### Package Installation
```bash
pip install -e .  # Development installation
# or
pip install .     # Regular installation
```

### Distribution
```bash
python -m build  # Create distribution packages
```

## 📞 Contact

For questions or suggestions regarding this energy trading analysis, please open an issue or submit a pull request.

---

*This project demonstrates quantitative analysis techniques for energy market optimization and serves as a foundation for more sophisticated trading algorithms.*