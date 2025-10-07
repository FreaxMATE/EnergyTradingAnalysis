import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates
import time as timer

# Data source: ENTSO-E Transparency Platform
# URL: https://newtransparency.entsoe.eu/market/energyPrices?appState=%7B%22sa%22%3A%5B%22BZN%7C10YDK-2--------M%22%5D%2C%22st%22%3A%22BZN%22%2C%22mm%22%3Atrue%2C%22ma%22%3Afalse%2C%22sp%22%3A%22HALF%22%2C%22dt%22%3A%22TABLE%22%2C%22df%22%3A%222025-09-27%22%2C%22tz%22%3A%22CET%22%7D
# Market: Day-ahead Prices (DAM)
# Bidding Zone: DK2 (Denmark - Eastern)
# Time Zone: CET
# Data Format: Half-hourly (HALF)

# Use relative paths from src/ directory
print("Loading CSV files...")
start_time = timer.time()

# Read CSVs with optimized parameters for better performance
csv_files = ["../data/price_dk_2023.csv", "../data/price_dk_2024.csv", "../data/price_dk_2025.csv"]
dataframes = []
for file in csv_files:
    df = pd.read_csv(file, sep=',', engine='c')  # Use C engine for faster parsing
    dataframes.append(df)

data_df_2023, data_df_2024, data_df_2025 = dataframes
print(f"CSV loading completed in {timer.time() - start_time:.2f} seconds")

# Date format: 01/01/2025 00:00:00 - 01/01/2025 01:00:00
# This should be like 01/01/2025 00:00:00

print("Processing data...")
processing_start = timer.time()

# print(price.dtypes)
data_df = pd.concat([data_df_2023, data_df_2024, data_df_2025], axis=0, join='outer', ignore_index=False, keys=None)
#data_df = data_df_2023

# Optimize datetime parsing by vectorizing the operation
time_strings = data_df.iloc[:, 0].str.split(' - ').str[0]
time = pd.to_datetime(time_strings, dayfirst=True).values
time_int = np.arange(len(time))
price = data_df.iloc[:, 3].astype(float).values

print(f"Data processing completed in {timer.time() - processing_start:.2f} seconds")

ma_window_size = 24
# Use pandas rolling mean for better performance
price_series = pd.Series(price)
price_avg_full = price_series.rolling(window=ma_window_size, center=False).mean().values
# Sample every ma_window_size points, starting from the first valid average
price_avg = price_avg_full[ma_window_size-1::ma_window_size]
time_avg = time[ma_window_size-1::ma_window_size]
time_avg_int = len(time_avg)

def sched_proc(price, mwhs=1000, n_parts=4, limit=10):
    # Pre-calculate partition indices for better performance
    price_len = len(price)
    parts = np.linspace(0, price_len, n_parts + 1, dtype=int)

    buy_indic = []
    for p in range(n_parts):
        start_idx = parts[p]
        end_idx = parts[p + 1]
        
        if start_idx >= end_idx:
            continue
            
        ref = price[start_idx]
        
        # Vectorized approach for finding the buy point
        segment = price[start_idx:end_idx]
        
        for i, current_price in enumerate(segment):
            actual_idx = start_idx + i
            if current_price > (ref + limit):
                buy_indic.append(actual_idx)
                break
            if current_price < ref:
                ref = current_price
    
    # Vectorized calculation of total price
    if buy_indic:
        total_price = np.sum(price[buy_indic] * (mwhs / n_parts))
    else:
        total_price = 0.0
    
    return buy_indic, total_price

figsize = (25,15)
size = 20
msize = 40
ticksize = 20
lwsize = 1

fig, ax = plt.subplots(figsize=figsize)


ax.plot(time_avg, price_avg, lw=3, label=r'Day-Ahead Price Daily Average')

# Format x-axis to show year and month
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

fig.autofmt_xdate()  # Auto-rotate date labels

n_parts_list = [1, 2, 3, 4, 6, 12, 24]

print("Running scheduling analysis...")
sched_start = timer.time()

# Pre-calculate all results to avoid duplicate sched_proc calls
mwhs = 1000

results_cache = {}
for n_parts in n_parts_list:
    buy_indic, total_price = sched_proc(price=price_avg, mwhs=mwhs, n_parts=n_parts)
    results_cache[n_parts] = (buy_indic, total_price)

print(f"Scheduling analysis completed in {timer.time() - sched_start:.2f} seconds")

# Plot using cached results
for n_parts in reversed(n_parts_list):
    buy_indic, total_price = results_cache[n_parts]
    time_buy = time_avg[buy_indic]
    price_buy = price_avg[buy_indic]
    ax.plot(time_buy, price_buy, '.', ms=msize, label=f'N$_{{proc}}$ = {n_parts}')

# Extract total prices from cache
total_prices = [results_cache[n_parts][1] for n_parts in n_parts_list]

ax.legend(fontsize=size)
plt.xticks(fontsize=ticksize)
plt.yticks(fontsize=ticksize)
plt.xlabel('Date', fontsize=size)
plt.ylabel(r'Day Ahead Price / (EUR/MWh)', fontsize=size)
plt.tight_layout()
plt.savefig('../output/dayaheadprices.png', dpi=150)

# Plot total_price vs n_parts
fig2, ax2 = plt.subplots(figsize=figsize)
plt.xticks(fontsize=ticksize)
plt.yticks(fontsize=ticksize)
ax2.plot(n_parts_list, total_prices, marker='o', ms=msize/2, lw=5)
# ax2.legend(fontsize=size)
ax2.set_xlabel('Number of Procurements (N$_{proc}$)', fontsize=size)
ax2.set_ylabel('Total Cost (€)', fontsize=size)
ax2.set_title('Total Cost vs Number of Procurements', fontsize=size)
ax2.grid(True)
#ax2.set_xticks(n_parts_list)
plt.tight_layout()
plt.savefig('../output/total_cost_vs_nproc.png', dpi=150)
plt.show()