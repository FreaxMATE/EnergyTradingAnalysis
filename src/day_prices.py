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

#price = np.array_split(price, len(price)/24)

# time string example: 2023-01-01T00:00:00.000000000
time_str = np.datetime_as_string(time)
time_hour = np.array([int(t[11:13]) for t in time_str])
h = 0
price_by_hour = [price[time_hour == h] for h in range(24)]
min_len = np.min([len(p) for p in price_by_hour])
price_by_hour = np.array([pbh[:min_len] for pbh in price_by_hour])

price_by_hour_avg = np.mean(price_by_hour, axis=1)
price_by_hour_std = np.std(price_by_hour, axis=1)

price_avg = np.mean(price_by_hour_avg)
price_std = np.mean(price_by_hour_avg)

figsize = (25,15)
size = 20
msize = 40
ticksize = 20
lwsize = 1


fig, ax = plt.subplots(figsize=figsize)

# Plot horizontal line for average price
ax.axhline(price_avg, color='tab:orange', linestyle='--', linewidth=3, label=r'Average price')
ax.axhspan(price_avg - price_std, price_avg + price_std, color='tab:orange', alpha=0.2, label=r'Average price standard deviation')

ax.plot(range(24), price_by_hour, 'x', ms=10, color='black')
ax.errorbar(range(24), price_by_hour_avg, yerr=price_by_hour_std, lw=3, color='tab:blue', capsize=size, capthick=3, label=r'Average price by hour')
ax.plot(range(24), price_by_hour_avg, '.', ms=15, color='tab:blue')

ax.legend(fontsize=size)
plt.xticks(fontsize=ticksize)
plt.yticks(fontsize=ticksize)
plt.xlabel('Time / h', fontsize=size)
plt.ylabel(r'Day Ahead Price / (EUR/MWh)', fontsize=size)
# plt.tight_layout()
plt.savefig('../output/price_by_hour.png', dpi=150)
plt.show()