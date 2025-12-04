from shiny import ui
from shinywidgets import output_widget

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h3("IDX Swing Strategist"),
        ui.hr(),
        ui.input_text("ticker", "Stock Ticker (e.g., BBCA, TLKM)", value="BBRI"),
        ui.input_select("period", "Data Period", choices=["6mo", "1y", "2y", "5y"], selected="2y"),
        ui.hr(),
        ui.h5("Strategy Params"),
        ui.input_slider("short_ma", "Short EMA (Fast)", min=5, max=50, value=20),
        ui.input_slider("long_ma", "Long EMA (Slow)", min=20, max=200, value=50),
        ui.input_numeric("capital", "Initial Capital (IDR)", value=10000000),
        ui.hr(),
        ui.input_action_button("run_scan", "Run Market Scan (LQ45 Top)", class_="btn-primary"),
        ui.markdown("_Scan checks top stocks for current crossover signals._")
    ),
    ui.page_fillable(
        ui.navset_card_tab(
            # Tab 1: Forecasting & Charts
            ui.nav_panel(
                "Forecasting & Analysis",
                ui.layout_columns(
                    ui.value_box(
                        "Current Price",
                        ui.output_ui("current_price_ui"),
                        theme="bg-gradient-blue-indigo"
                    ),
                    ui.value_box(
                        "Trend Signal",
                        ui.output_ui("signal_ui"),
                        theme="bg-gradient-indigo-purple"
                    ),
                    ui.value_box(
                        "Volatility (30D)",
                        ui.output_ui("volatility_ui"),
                        theme="bg-gradient-purple-pink"
                    ),
                ),
                output_widget("price_chart"),
                ui.markdown("For swing trading, look for crossovers where the Fast EMA (Green) crosses above the Slow EMA (Red).")
            ),
            
            # Tab 2: Screening
            ui.nav_panel(
                "Market Screener",
                ui.h4("LQ45 Sample Scanner"),
                ui.output_text("scan_status"),
                ui.output_data_frame("screener_table")
            ),
            
            # Tab 3: Backtesting
            ui.nav_panel(
                "Backtesting",
                ui.layout_columns(
                    ui.card(output_widget("backtest_chart")),
                    ui.card(
                        ui.h5("Performance Metrics"),
                        ui.output_table("backtest_metrics")
                    )
                )
            ),
            
            # Tab 4: Portfolio Expectation
            ui.nav_panel(
                "Portfolio Simulation",
                ui.layout_columns(
                    ui.card(
                         ui.h5("Monte Carlo Simulation (Next 90 Days)"),
                         ui.markdown("Simulating 500 possible future price paths based on historical volatility."),
                         output_widget("monte_carlo_chart")
                    ),
                    ui.card(
                        ui.h5("Expected Returns Distribution"),
                        output_widget("distribution_chart")
                    )
                )
            )
        )
    )
)