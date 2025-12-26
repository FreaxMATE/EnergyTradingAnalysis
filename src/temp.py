import pandas as pd
import matplotlib.pyplot as plt
import os

# Construct the relative path to the data file
file_path = os.path.join(os.path.dirname(__file__), '../data/EE/EE_generation.csv')

# Load the data
df = pd.read_csv(file_path)

# Plot the data
plt.figure(figsize=(12, 6))
# Assuming the first column might be a timestamp, let's try to set it as index if possible, 
# otherwise just plot all numeric columns.
# Based on user input, the first column is the timestamp but might not be named 'timestamp' in the CSV header if it's unnamed.
# Let's assume the first column is the index.
df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0])
df.set_index(df.columns[0], inplace=True)

plt.stackplot(df.index, df.T.values, labels=df.columns)

plt.title('EE Generation Data')
plt.xlabel('Time')
plt.ylabel('Generation')
plt.legend(loc='upper left')
plt.grid(True)
plt.show()
