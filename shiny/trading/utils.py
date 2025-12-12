import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def fetch_stock_data(ticker, period="2y", interval="1d"):
    """Fetches stock data from Yahoo Finance."""
    if not ticker.endswith(".JK"):
        ticker = f"{ticker}.JK"
    
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.reset_index(inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_indicators(df, short_window, long_window):
    """Calculates EMA and signals for swing trading."""
    df = df.copy()
    df['EMA_Short'] = df['Close'].ewm(span=short_window, adjust=False).mean()
    df['EMA_Long'] = df['Close'].ewm(span=long_window, adjust=False).mean()
    df['Signal'] = 0.0
    df['Signal'] = np.where(df['EMA_Short'] > df['EMA_Long'], 1.0, 0.0)
    # Position change (1 = Buy, -1 = Sell)
    df['Position'] = df['Signal'].diff()
    return df

def calculate_backtest(df, capital):
    """Runs vectorised backtest on the provided dataframe."""
    df = df.copy()
    # Shift signal by 1 day to avoid lookahead bias
    df['Strategy_Signal'] = df['Signal'].shift(1)
    df['Log_Returns'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Strategy_Returns'] = df['Strategy_Signal'] * df['Log_Returns']
    
    # Cumulative Returns
    df['Cum_Benchmark'] = df['Log_Returns'].cumsum().apply(np.exp)
    df['Cum_Strategy'] = df['Strategy_Returns'].cumsum().apply(np.exp)
    
    # Equity Curves
    df['Equity_Benchmark'] = df['Cum_Benchmark'] * capital
    df['Equity_Strategy'] = df['Cum_Strategy'] * capital
    
    return df

def calculate_metrics(df, capital):
    """Generates performance metrics from a backtested dataframe."""
    total_return = (df['Equity_Strategy'].iloc[-1] / capital) - 1
    bh_return = (df['Equity_Benchmark'].iloc[-1] / capital) - 1
    
    days = (df['Date'].iloc[-1] - df['Date'].iloc[0]).days
    years = max(days / 365.25, 0.01) # Avoid div by zero
    
    cagr = (df['Equity_Strategy'].iloc[-1] / capital) ** (1/years) - 1
    
    # Max Drawdown
    rolling_max = df['Equity_Strategy'].cummax()
    drawdown = df['Equity_Strategy'] / rolling_max - 1
    max_dd = drawdown.min()
    
    metrics = [
        {"Metric": "Initial Capital", "Value": f"Rp {capital:,.0f}"},
        {"Metric": "Final Value", "Value": f"Rp {df['Equity_Strategy'].iloc[-1]:,.0f}"},
        {"Metric": "Total Return", "Value": f"{total_return:.2%}"},
        {"Metric": "Buy & Hold Return", "Value": f"{bh_return:.2%}"},
        {"Metric": "CAGR (Annualized)", "Value": f"{cagr:.2%}"},
        {"Metric": "Max Drawdown", "Value": f"{max_dd:.2%}"},
    ]
    return pd.DataFrame(metrics)

def run_monte_carlo_simulation(df, simulations=500, time_horizon=90):
    """
    Performs Monte Carlo simulation.
    Returns:
        dates (list): Future dates
        paths (np.array): Price paths (time_horizon x simulations)
        final_prices (np.array): Distribution of prices at end of horizon
    """
    returns = df['Close'].pct_change().dropna()
    mu = returns.mean()
    sigma = returns.std()
    start_price = df['Close'].iloc[-1]
    
    # Vectorized Simulation
    random_shocks = np.random.normal(0, 1, (time_horizon, simulations))
    drift = mu - 0.5 * sigma**2
    daily_returns = np.exp(drift + sigma * random_shocks)
    
    price_paths = np.zeros_like(daily_returns)
    price_paths[0] = start_price
    
    for t in range(1, time_horizon):
        price_paths[t] = price_paths[t-1] * daily_returns[t]
        
    dates = [datetime.now() + timedelta(days=i) for i in range(time_horizon)]
    final_prices = price_paths[-1]
    
    return dates, price_paths, final_prices