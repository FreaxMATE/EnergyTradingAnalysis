import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates

# Data source: ENTSO-E Transparency Platform
# URL: https://newtransparency.entsoe.eu/market/energyPrices?appState=%7B%22sa%22%3A%5B%22BZN%7C10YDK-2--------M%22%5D%2C%22st%22%3A%22BZN%22%2C%22mm%22%3Atrue%2C%22ma%22%3Afalse%2C%22sp%22%3A%22HALF%22%2C%22dt%22%3A%22TABLE%22%2C%22df%22%3A%222025-09-27%22%2C%22tz%22%3A%22CET%22%7D
# Market: Day-ahead Prices (DAM)
# Bidding Zone: DK2 (Denmark - Eastern)
# Time Zone: CET
# Data Format: Half-hourly (HALF)

data_df_2023 = pd.read_csv("price_dk_2023.csv", sep=',')
data_df_2024 = pd.read_csv("price_dk_2024.csv", sep=',')
data_df_2025 = pd.read_csv("price_dk_2025.csv", sep=',')

# Date format: 01/01/2025 00:00:00 - 01/01/2025 01:00:00
# This should be like 01/01/2025 00:00:00

# print(price.dtypes)
data_df = pd.concat([data_df_2023, data_df_2024, data_df_2025], axis=0, join='outer', ignore_index=False, keys=None)
#data_df = data_df_2023

data = data_df.to_numpy()

time = np.array([pd.to_datetime(t.split(' - ')[0], dayfirst=True) for t in data[:, 0]])
time_int = np.arange(len(time))
price = data[:, 3].astype(float)

ma_window_size = 24
time_avg = time[::ma_window_size][:-1]
time_avg_int = len(time_avg)
price_avg = np.convolve(price, np.ones(ma_window_size)/ma_window_size, mode='valid')[::ma_window_size]

print(len(time_avg))
print(len(price_avg))
print(len(price))


def sched_proc(price, mwhs=1000, n_parts=4, limit=10):
    parts = [int(n/n_parts * len(price)) for n in range(n_parts+1)]

    buy_indic = []
    for p in range(len(parts)-1):
        ref = price[parts[p]]
        i = parts[p]
        while (i < parts[p+1]):
            if price[i] > (ref + limit):
                # print('Price: ', price[i], ' is > ', (ref + limit), ' (ref + limit) ')
                # print('Buy at price ', price[i])
                buy_indic.append(i)
                break
            if price[i] < ref:
                # print('Price: ', price[i], ' is < ', ref, ' (ref) ')
                # print('Set new ref to price ', price[i])
                ref = price[i]
            i += 1
    total_price = np.sum(price[buy_indic]*(mwhs/n_parts))
    return buy_indic, total_price

figsize = (25,15)
size = 20
msize = 40
ticksize = 20
lwsize = 1

fig, ax = plt.subplots(figsize=figsize)


ax.plot(time_avg, price_avg, lw=lwsize, label=r'Day-Ahead Price Daily Average')

# Format x-axis to show year and month
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

fig.autofmt_xdate()  # Auto-rotate date labels

n_parts_list = [1, 2, 3, 4, 6, 12, 24]

for n_parts in reversed(n_parts_list):
    buy_indic, total_price = sched_proc(price=price_avg, n_parts=n_parts)
    time_buy = time_avg[buy_indic]
    price_buy = price_avg[buy_indic]
    ax.plot(time_buy, price_buy, '.', ms=msize, label=f'N$_{{proc}}$ = {n_parts}')

# Plot total_price vs n_parts
total_prices = []
for n_parts in n_parts_list:
    _, total_price = sched_proc(price=price_avg, n_parts=n_parts)
    total_prices.append(total_price)

ax.legend(fontsize=size)
plt.xticks(fontsize=ticksize)
plt.yticks(fontsize=ticksize)
plt.xlabel('Time', fontsize=size)
plt.ylabel(r'Day Ahead Price / €', fontsize=size)
plt.tight_layout()
plt.savefig('dayaheadprices.png', dpi=150)

# Plot total_price vs n_parts
fig2, ax2 = plt.subplots(figsize=figsize)
plt.xticks(fontsize=ticksize)
plt.yticks(fontsize=ticksize)
ax2.plot(n_parts_list, total_prices, marker='o', ms=msize/2, lw=5)
ax2.legend(fontsize=size)
ax2.set_xlabel('Number of Procurements (N$_{proc}$)', fontsize=size)
ax2.set_ylabel('Total Cost (€)', fontsize=size)
ax2.set_title('Total Cost vs Number of Procurements', fontsize=size)
ax2.grid(True)
#ax2.set_xticks(n_parts_list)
plt.tight_layout()
plt.savefig('total_cost_vs_nproc.png', dpi=150)
plt.show()