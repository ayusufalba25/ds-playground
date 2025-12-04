from shiny import App, ui, render, reactive, req
import sqlite3
import pandas as pd
from datetime import datetime
import io

# ==========================================
# 1. DATABASE SETUP & HELPERS
# ==========================================
DB_NAME = "shop.db"

def init_db():
    """Initialize the database with a Star Schema-ish structure for OLAP."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Auth: Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            role TEXT -- 'admin', 'inventory', 'sales' (Admin Team)
        )
    ''')

    # Dimension: Products (Inventory)
    c.execute('''
        CREATE TABLE IF NOT EXISTS dim_laptops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT,
            model TEXT,
            specs TEXT,
            purchase_price REAL,
            status TEXT DEFAULT 'Available', -- Available, Sold
            date_added TEXT
        )
    ''')
    
    # Dimension: Customers/Leads
    c.execute('''
        CREATE TABLE IF NOT EXISTS dim_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            interest_level TEXT, -- High, Medium, Low
            status TEXT DEFAULT 'New', -- New, Contacted, Converted, Lost
            created_at TEXT
        )
    ''')
    
    # Fact: Sales
    c.execute('''
        CREATE TABLE IF NOT EXISTS fact_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laptop_id INTEGER,
            lead_id INTEGER,
            sale_date TEXT,
            sale_price REAL,
            margin REAL,
            FOREIGN KEY(laptop_id) REFERENCES dim_laptops(id),
            FOREIGN KEY(lead_id) REFERENCES dim_leads(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def seed_data():
    """Add dummy data if empty."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Seed Users
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        users = [
            ('admin', 'admin123', 'admin'),
            ('inv', 'inv123', 'inventory'),
            ('sales', 'sales123', 'sales') # Represents "Admin Team"
        ]
        c.executemany("INSERT INTO users VALUES (?,?,?)", users)

    # Seed Laptops
    c.execute("SELECT count(*) FROM dim_laptops")
    if c.fetchone()[0] == 0:
        laptops = [
            ('Dell', 'XPS 13', 'i7, 16GB RAM', 800, 'Available', '2023-01-10'),
            ('Lenovo', 'ThinkPad T14', 'i5, 8GB RAM', 600, 'Available', '2023-01-12'),
            ('Apple', 'MacBook Air M1', '8GB RAM, 256GB SSD', 750, 'Available', '2023-01-15'),
            ('HP', 'Spectre x360', 'i7, 512GB SSD', 900, 'Available', '2023-01-20'),
            ('Asus', 'ZenBook', 'i5, 16GB', 650, 'Sold', '2023-01-05')
        ]
        c.executemany("INSERT INTO dim_laptops (brand, model, specs, purchase_price, status, date_added) VALUES (?,?,?,?,?,?)", laptops)
        
        # Seed Leads
        leads = [
            ('Alice Smith', '555-0101', 'High', 'New', '2023-01-10'),
            ('Bob Jones', '555-0102', 'Medium', 'Contacted', '2023-01-11'),
            ('Charlie Day', '555-0103', 'High', 'Converted', '2023-01-12')
        ]
        c.executemany("INSERT INTO dim_leads (name, phone, interest_level, status, created_at) VALUES (?,?,?,?,?)", leads)
        
        # Seed Sales
        c.execute("INSERT INTO fact_sales (laptop_id, lead_id, sale_date, sale_price, margin) VALUES (5, 3, '2023-01-25', 850, 200)")
    
    # FIXED: Commit happens regardless of whether laptops existed or not
    conn.commit()
    conn.close()

# Run DB init on import
init_db()
seed_data()

def run_query(query, params=(), fetch=True):
    conn = sqlite3.connect(DB_NAME)
    df = None
    try:
        if fetch:
            df = pd.read_sql_query(query, conn, params=params)
        else:
            c = conn.cursor()
            c.execute(query, params)
            conn.commit()
    finally:
        conn.close()
    return df

def check_credentials(username, password):
    """Verify user against database."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

# ==========================================
# 2. UI COMPONENTS
# ==========================================

# -- CSS --
custom_css = ui.tags.style("""
    .card { margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: none; }
    .nav-tabs { margin-bottom: 15px; }
    h2 { color: #2c3e50; font-weight: 300; }
    .value-box { padding: 20px; border-radius: 8px; color: white; text-align: center; }
    .bg-primary { background-color: #3498db; }
    .bg-success { background-color: #2ecc71; }
    .bg-warning { background-color: #f1c40f; }
    .login-container { max-width: 400px; margin: 100px auto; padding: 20px; }
    .logout-btn { position: absolute; top: 20px; right: 20px; z-index: 1000; }
""")

# -- LOGIN SCREEN --
def login_ui():
    return ui.div(
        ui.card(
            ui.card_header(ui.h3("Login", class_="text-center")),
            ui.input_text("user_login", "Username", placeholder="admin / inv / sales"),
            ui.input_password("pass_login", "Password", placeholder="...123"),
            ui.input_action_button("btn_login", "Sign In", class_="btn-primary w-100"),
            # Note: Removed broken 'login_error' output text here, handled by notification
        ),
        class_="login-container"
    )

# -- TAB CONTENTS (Helper functions) --

def tab_inventory():
    return ui.nav_panel("Inventory",
        ui.layout_sidebar(
            ui.sidebar(
                ui.h4("Add Laptop"),
                ui.input_text("inv_brand", "Brand", placeholder="e.g. Dell"),
                ui.input_text("inv_model", "Model", placeholder="e.g. XPS 13"),
                ui.input_text("inv_specs", "Specs", placeholder="e.g. i7, 16GB"),
                ui.input_numeric("inv_price", "Purchase Price ($)", value=0),
                ui.input_action_button("btn_add_laptop", "Add to Inventory", class_="btn-primary"),
                ui.hr(),
                ui.input_select("filter_status", "Filter Status", choices=["All", "Available", "Sold"]),
            ),
            ui.h3("Current Stock"),
            ui.output_data_frame("tbl_inventory")
        )
    )

def tab_leads():
    return ui.nav_panel("Leads / CRM",
         ui.layout_sidebar(
            ui.sidebar(
                ui.h4("New Lead"),
                ui.input_text("lead_name", "Customer Name"),
                ui.input_text("lead_phone", "Contact"),
                ui.input_select("lead_interest", "Interest Level", choices=["High", "Medium", "Low"]),
                ui.input_action_button("btn_add_lead", "Create Lead", class_="btn-success"),
            ),
            ui.row(
                ui.column(8, 
                    ui.h3("Lead Directory"),
                    ui.output_data_frame("tbl_leads")
                ),
                ui.column(4,
                    ui.card(
                        ui.card_header("Manage Selected Lead"),
                        ui.input_select("update_lead_id", "Select Lead ID to Update", choices=[]),
                        ui.input_select("update_lead_status", "New Status", choices=["New", "Contacted", "Converted", "Lost"]),
                        ui.input_action_button("btn_update_lead", "Update Status", class_="btn-secondary")
                    )
                )
            )
         )
    )

def tab_sales():
    return ui.nav_panel("Point of Sale",
        ui.row(
            ui.column(4,
                ui.card(
                    ui.card_header("Record New Sale"),
                    ui.input_select("sale_laptop_id", "Select Available Laptop", choices=[]),
                    ui.input_select("sale_lead_id", "Select Customer", choices=[]),
                    ui.input_numeric("sale_price", "Selling Price ($)", value=0),
                    ui.input_date("sale_date", "Date", value=datetime.now().strftime("%Y-%m-%d")),
                    ui.br(),
                    ui.input_action_button("btn_record_sale", "Complete Sale", class_="btn-danger w-100")
                )
            ),
            ui.column(8,
                ui.h3("Sales History"),
                ui.output_data_frame("tbl_sales_history")
            )
        )
    )

def tab_analytics():
    return ui.nav_panel("Analytics (OLAP)",
        ui.row(
            ui.column(3, 
                ui.div(ui.output_text("metric_total_rev"), class_="value-box bg-primary"),
            ),
            ui.column(3, 
                ui.div(ui.output_text("metric_total_profit"), class_="value-box bg-success"),
            ),
            ui.column(3, 
                ui.div(ui.output_text("metric_units_sold"), class_="value-box bg-warning"),
            ),
        ),
        ui.hr(),
        ui.layout_sidebar(
            ui.sidebar(
                ui.h4("Slice & Dice"),
                ui.input_select("olap_dimension", "Group By", 
                                choices={"brand": "Laptop Brand", "interest_level": "Customer Interest", "month": "Sale Month"}),
                ui.input_select("olap_measure", "Measure", 
                                choices={"sale_price": "Revenue", "margin": "Profit", "id": "Count"}),
            ),
            ui.h4("OLAP View"),
            ui.output_data_frame("tbl_olap"),
            ui.output_plot("plot_olap")
        )
    )

# -- MAIN APP WRAPPER --
app_ui = ui.page_fluid(
    custom_css,
    ui.output_ui("main_content")
)


# ==========================================
# 3. SERVER LOGIC
# ==========================================

def server(input, output, session):
    
    # --- AUTHENTICATION STATE ---
    # Stores: {'username': str, 'role': str} or None
    user_session = reactive.Value(None)
    
    # DB Trigger for reactivity
    db_version = reactive.Value(0)

    def trigger_update():
        db_version.set(db_version.get() + 1)

    # --- LOGIN LOGIC ---
    @reactive.Effect
    @reactive.event(input.btn_login)
    def _():
        u = input.user_login()
        p = input.pass_login()
        role = check_credentials(u, p)
        if role:
            user_session.set({'username': u, 'role': role})
        else:
            ui.notification_show("Invalid username or password", type="error")

    @reactive.Effect
    @reactive.event(input.btn_logout)
    def _():
        user_session.set(None)

    # --- DYNAMIC UI ROUTER ---
    @render.ui
    def main_content():
        user = user_session.get()
        
        # 1. Not Logged In -> Show Login
        if user is None:
            return login_ui()
        
        # 2. Logged In -> Determine Tabs based on Role
        role = user['role']
        tabs = []
        
        # Determine available tabs
        if role == 'admin':
            tabs = [tab_inventory(), tab_leads(), tab_sales(), tab_analytics()]
        elif role == 'inventory':
            tabs = [tab_inventory()]
        elif role == 'sales': # Admin Team
            tabs = [tab_leads(), tab_sales()]
        
        # Render Dashboard
        return ui.div(
            ui.input_action_button("btn_logout", "Logout", class_="btn-sm btn-outline-danger logout-btn"),
            ui.panel_title(f"💻 Laptop Shop Manager ({role.upper()})"),
            ui.navset_card_tab(*tabs)
        )

    # ==========================
    # BUSINESS LOGIC (Protected)
    # ==========================
    
    # Helper to check permissions within effects if strictly necessary,
    # though UI hiding prevents most unauthorized access.
    
    # --- INVENTORY ---
    @reactive.Effect
    @reactive.event(input.btn_add_laptop)
    def _():
        # Ensure user is logged in
        if not user_session.get(): return
        
        if input.inv_brand() and input.inv_model():
            sql = "INSERT INTO dim_laptops (brand, model, specs, purchase_price, date_added) VALUES (?, ?, ?, ?, ?)"
            params = (input.inv_brand(), input.inv_model(), input.inv_specs(), input.inv_price(), datetime.now().strftime("%Y-%m-%d"))
            run_query(sql, params, fetch=False)
            ui.notification_show("Laptop added!", type="message")
            trigger_update()

    @render.data_frame
    def tbl_inventory():
        db_version.get()
        # Logic runs even if hidden, but UI won't show it.
        # Safe to return data as the view is protected by @render.ui logic above.
        query = "SELECT id, brand, model, specs, purchase_price, status, date_added FROM dim_laptops"
        if input.filter_status() and input.filter_status() != "All":
            query += f" WHERE status = '{input.filter_status()}'"
        return run_query(query)

    # --- LEADS ---
    @reactive.Effect
    @reactive.event(input.btn_add_lead)
    def _():
        if not user_session.get(): return
        if input.lead_name():
            sql = "INSERT INTO dim_leads (name, phone, interest_level, created_at) VALUES (?, ?, ?, ?)"
            params = (input.lead_name(), input.lead_phone(), input.lead_interest(), datetime.now().strftime("%Y-%m-%d"))
            run_query(sql, params, fetch=False)
            ui.notification_show("Lead added!", type="message")
            trigger_update()
            
    @render.data_frame
    def tbl_leads():
        db_version.get()
        return run_query("SELECT * FROM dim_leads ORDER BY id DESC")

    @reactive.Effect
    def _():
        # Update Lead Select (Dropdown)
        db_version.get()
        # This input might not exist if user is Inventory Team.
        # Shiny safely handles this, or we can wrap in try/except if using 'req'
        if "update_lead_id" in input:
            df = run_query("SELECT id, name FROM dim_leads")
            choices = {str(row['id']): f"{row['id']} - {row['name']}" for _, row in df.iterrows()}
            ui.update_select("update_lead_id", choices=choices)

    @reactive.Effect
    @reactive.event(input.btn_update_lead)
    def _():
        lid = input.update_lead_id()
        if lid:
            run_query("UPDATE dim_leads SET status = ? WHERE id = ?", (input.update_lead_status(), lid), fetch=False)
            ui.notification_show("Lead status updated.", type="message")
            trigger_update()

    # --- SALES ---
    @reactive.Effect
    def _():
        # Update Sale Selects
        db_version.get()
        if "sale_laptop_id" in input:
            df_laptops = run_query("SELECT id, brand, model, purchase_price FROM dim_laptops WHERE status = 'Available'")
            l_choices = {str(row['id']): f"{row['brand']} {row['model']} (Buy: ${row['purchase_price']})" for _, row in df_laptops.iterrows()}
            ui.update_select("sale_laptop_id", choices=l_choices)
            
            df_leads = run_query("SELECT id, name FROM dim_leads")
            c_choices = {str(row['id']): row['name'] for _, row in df_leads.iterrows()}
            ui.update_select("sale_lead_id", choices=c_choices)

    @reactive.Effect
    @reactive.event(input.btn_record_sale)
    def _():
        laptop_id = input.sale_laptop_id()
        lead_id = input.sale_lead_id()
        price = input.sale_price()
        date = input.sale_date()
        
        if laptop_id and lead_id and price:
            df_cost = run_query("SELECT purchase_price FROM dim_laptops WHERE id = ?", (laptop_id,))
            if not df_cost.empty:
                cost = df_cost.iloc[0]['purchase_price']
                margin = float(price) - cost
                
                sql_fact = "INSERT INTO fact_sales (laptop_id, lead_id, sale_date, sale_price, margin) VALUES (?, ?, ?, ?, ?)"
                run_query(sql_fact, (laptop_id, lead_id, str(date), price, margin), fetch=False)
                run_query("UPDATE dim_laptops SET status = 'Sold' WHERE id = ?", (laptop_id,), fetch=False)
                run_query("UPDATE dim_leads SET status = 'Converted' WHERE id = ?", (lead_id,), fetch=False)
                
                ui.notification_show("Sale recorded!", type="message")
                trigger_update()

    @render.data_frame
    def tbl_sales_history():
        db_version.get()
        sql = """
            SELECT s.id, s.sale_date, l.brand, l.model, c.name as customer, s.sale_price, s.margin 
            FROM fact_sales s
            JOIN dim_laptops l ON s.laptop_id = l.id
            JOIN dim_leads c ON s.lead_id = c.id
            ORDER BY s.sale_date DESC
        """
        return run_query(sql)

    # --- ANALYTICS ---
    @reactive.Calc
    def olap_data():
        db_version.get()
        sql = """
            SELECT 
                s.sale_date, 
                strftime('%Y-%m', s.sale_date) as month,
                l.brand, 
                l.model, 
                c.interest_level,
                s.sale_price, 
                s.margin,
                s.id
            FROM fact_sales s
            JOIN dim_laptops l ON s.laptop_id = l.id
            JOIN dim_leads c ON s.lead_id = c.id
        """
        return run_query(sql)

    @render.text
    def metric_total_rev():
        df = olap_data()
        val = df['sale_price'].sum() if not df.empty else 0
        return f"Revenue: ${val:,.0f}"

    @render.text
    def metric_total_profit():
        df = olap_data()
        val = df['margin'].sum() if not df.empty else 0
        return f"Profit: ${val:,.0f}"
        
    @render.text
    def metric_units_sold():
        df = olap_data()
        return f"Units Sold: {len(df)}"

    @render.data_frame
    def tbl_olap():
        df = olap_data()
        if df.empty: return df
        group_col = input.olap_dimension()
        measure_col = input.olap_measure()
        if measure_col == 'id':
            res = df.groupby(group_col)[measure_col].count().reset_index(name='Count')
        else:
            res = df.groupby(group_col)[measure_col].sum().reset_index()
        return res

    @render.plot
    def plot_olap():
        import matplotlib.pyplot as plt
        import seaborn as sns
        df = olap_data()
        if df.empty: 
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "No Data", ha='center')
            return fig
        group_col = input.olap_dimension()
        measure_col = input.olap_measure()
        fig, ax = plt.subplots(figsize=(10, 5))
        if measure_col == 'id':
            plot_data = df.groupby(group_col)[measure_col].count().reset_index()
            y_label = "Count"
        else:
            plot_data = df.groupby(group_col)[measure_col].sum().reset_index()
            y_label = f"Total {measure_col.replace('_', ' ').title()}"
        sns.barplot(data=plot_data, x=group_col, y=measure_col, ax=ax, palette="viridis")
        ax.set_title(f"{y_label} by {group_col.title()}")
        ax.set_ylabel(y_label)
        ax.set_xlabel(group_col.title())
        return fig

app = App(app_ui, server)