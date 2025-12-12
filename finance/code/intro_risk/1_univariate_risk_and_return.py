import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

FILE_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(os.path.dirname(FILE_DIR))
os.chdir(PROJECT_DIR)
print(f"Working directory set to: {PROJECT_DIR}")

# Download the data
df = pd.read_csv("https://assets.datacamp.com/production/course_6836/datasets/MSFTPrices.csv")
df.to_csv("./data/intro_risk/stock.csv", index=False)
df.info()

# Adjust data type
df["Date"] = pd.to_datetime(df["Date"])

# Set index
df = df.sort_values("Date")
df = df.set_index("Date")

# Read CSV data into DataFrame
# df = pd.read_csv("/data/intro_risk/stock.csv", parse_dates=['Date'])
# df.set_index("Date", inplace=True)

# Calculate daily returns
daily_returns = df['Adjusted'].pct_change().dropna()

# Plot histogram of daily returns
plt.hist(daily_returns, bins=50, density=False)
plt.xlabel('Daily Returns')
plt.ylabel('Frequency')
plt.title('Histogram of Daily Returns')
plt.show()