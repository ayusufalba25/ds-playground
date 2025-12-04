from shiny import render, reactive, ui
from shinywidgets import render_widget
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import timedelta

# Import our custom utilities
import utils

def server(input, output, session):
    
    # 1. Reactive Data Fetching
    @reactive.calc
    def get_data():
        ticker = input.ticker().upper().strip()
        if not ticker:
            return None
        return utils.fetch_stock_data(ticker, period=input.period())

    # 2. Reactive Indicators
    @reactive.calc
    def get_analyzed_data():
        df = get_data()
        if df is None:
            return None
        return utils.calculate_indicators(df, input.short_ma(), input.long_ma())

    # --- Tab 1: Forecasting UI ---
    
    @render.ui
    def current_price_ui():
        df = get_data()
        if df is None: return "N/A"
        price = df['Close'].iloc[-1]
        change = df['Close'].iloc[-1] - df['Close'].iloc[-2]
        color = "text-success" if change >= 0 else "text-danger"
        return ui.HTML(f"Rp {price:,.0f} <span class='{color}'>({change:+,.0f})</span>")

    @render.ui
    def signal_ui():
        df = get_analyzed_data()
        if df is None: return "N/A"
        
        last_short = df['EMA_Short'].iloc[-1]
        last_long = df['EMA_Long'].iloc[-1]
        
        if last_short > last_long:
            return ui.span("BULLISH (Buy Zone)", style="color: #4caf50; font-weight: bold;")
        else:
            return ui.span("BEARISH (Sell/Wait)", style="color: #f44336; font-weight: bold;")

    @render.ui
    def volatility_ui():
        df = get_data()
        if df is None: return "N/A"
        # Calculate annualized volatility based on 30 day window
        returns = df['Close'].pct_change()
        vol = returns.rolling(window=30).std().iloc[-1] * np.sqrt(252) * 100
        return f"{vol:.2f}%"

    @render_widget
    def price_chart():
        df = get_analyzed_data()
        if df is None: return go.Figure()

        fig = go.Figure()
        
        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df['Date'], open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'], name='Price'
        ))
        
        # EMAs
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA_Short'], line=dict(color='green', width=1.5), name=f'EMA {input.short_ma()}'))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA_Long'], line=dict(color='red', width=1.5), name=f'EMA {input.long_ma()}'))

        # Simple Linear Forecast (Projection)
        last_30 = df.tail(30).reset_index(drop=True)
        x = np.arange(len(last_30))
        y = last_30['Close'].values
        slope, intercept = np.polyfit(x, y, 1)
        
        future_days = 14
        future_x = np.arange(len(last_30), len(last_30) + future_days)
        future_y = slope * future_x + intercept
        
        last_date = df['Date'].iloc[-1]
        future_dates = [last_date + timedelta(days=i) for i in range(1, future_days + 1)]
        
        fig.add_trace(go.Scatter(
            x=future_dates, y=future_y, 
            line=dict(color='blue', dash='dot'), 
            name='Linear Trend (14d Forecast)'
        ))

        fig.update_layout(
            title=f"{input.ticker().upper()} Price Action",
            yaxis_title="Price (IDR)",
            xaxis_rangeslider_visible=False,
            template="plotly_white",
            height=500,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        return fig

    # --- Tab 2: Screener ---
    
    @render.text
    def scan_status():
        if input.run_scan() == 0:
            return "Press 'Run Market Scan' to check top stocks."
        return "Scan complete."

    @render.data_frame
    def screener_table():
        if input.run_scan() == 0:
            return pd.DataFrame(columns=["Ticker", "Price", "Trend", "Action"])
        
        watchlist = ["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "UNTR", "ICBP", "GOTO", "ADRO"]
        results = []
        
        with ui.Progress(min=0, max=len(watchlist)) as p:
            p.set(message="Scanning market...", detail="Fetching data")
            
            for i, ticker in enumerate(watchlist):
                p.set(i, message=f"Scanning {ticker}...")
                data = utils.fetch_stock_data(ticker, period="6mo")
                
                if data is not None and len(data) > 50:
                    short_ema = data['Close'].ewm(span=input.short_ma(), adjust=False).mean().iloc[-1]
                    long_ema = data['Close'].ewm(span=input.long_ma(), adjust=False).mean().iloc[-1]
                    price = data['Close'].iloc[-1]
                    
                    trend = "Bullish" if short_ema > long_ema else "Bearish"
                    
                    prev_short = data['Close'].ewm(span=input.short_ma(), adjust=False).mean().iloc[-2]
                    prev_long = data['Close'].ewm(span=input.long_ma(), adjust=False).mean().iloc[-2]
                    
                    action = "Hold"
                    if short_ema > long_ema and prev_short <= prev_long:
                        action = "GOLDEN CROSS (Buy)"
                    elif short_ema < long_ema and prev_short >= prev_long:
                        action = "DEATH CROSS (Sell)"
                    
                    results.append({
                        "Ticker": ticker,
                        "Price": f"{price:,.0f}",
                        "Trend": trend,
                        "Action": action,
                        "EMA_Gap": f"{(short_ema - long_ema):.2f}"
                    })
        
        return pd.DataFrame(results)

    # --- Tab 3: Backtesting ---
    
    @reactive.calc
    def run_backtest_calc():
        df = get_analyzed_data()
        if df is None: return None
        return utils.calculate_backtest(df, input.capital())

    @render_widget
    def backtest_chart():
        df = run_backtest_calc()
        if df is None: return go.Figure()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Equity_Strategy'], name='Swing Strategy', line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Equity_Benchmark'], name='Buy & Hold', line=dict(color='gray', dash='dot')))
        
        fig.update_layout(
            title="Equity Curve: Strategy vs Benchmark",
            yaxis_title="Portfolio Value (IDR)",
            template="plotly_white",
            height=400
        )
        return fig

    @render.table
    def backtest_metrics():
        df = run_backtest_calc()
        if df is None: return pd.DataFrame()
        return utils.calculate_metrics(df, input.capital())

    # --- Tab 4: Portfolio Expectation (Monte Carlo) ---
    
    @render_widget
    def monte_carlo_chart():
        df = get_data()
        if df is None: return go.Figure()
        
        simulations = 500
        dates, paths, _ = utils.run_monte_carlo_simulation(df, simulations=simulations)
        
        fig = go.Figure()
        
        # Plot only first 50 paths to keep chart clean
        for i in range(min(50, simulations)):
            fig.add_trace(go.Scatter(
                x=dates, y=paths[:, i], 
                mode='lines', 
                line=dict(width=1, color='rgba(0,100,255,0.1)'),
                showlegend=False, hoverinfo='skip'
            ))
            
        # Add mean path
        mean_path = np.mean(paths, axis=1)
        fig.add_trace(go.Scatter(
            x=dates, y=mean_path,
            mode='lines',
            line=dict(width=3, color='orange'),
            name='Expected Path (Mean)'
        ))
            
        fig.update_layout(
            title=f"Projected Price Paths (90 Days)",
            yaxis_title="Price (IDR)",
            template="plotly_white"
        )
        return fig

    @render_widget
    def distribution_chart():
        df = get_data()
        if df is None: return go.Figure()
        
        # Run sim just to get final prices
        _, _, final_prices = utils.run_monte_carlo_simulation(df, simulations=1000)
        start_price = df['Close'].iloc[-1]
        
        fig = px.histogram(
            x=final_prices, 
            nbins=50, 
            title="Distribution of Expected Prices (Day 90)",
            labels={'x': 'Price (IDR)', 'y': 'Count'}
        )
        
        fig.add_vline(x=start_price, line_dash="dash", line_color="black", annotation_text="Current Price")
        
        var_95 = np.percentile(final_prices, 5)
        fig.add_vline(x=var_95, line_dash="dot", line_color="red", annotation_text="95% Risk (VaR)")

        fig.update_layout(template="plotly_white")
        return fig