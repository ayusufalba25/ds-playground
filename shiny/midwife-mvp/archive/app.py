import sqlite3
import pandas as pd
from datetime import datetime, timedelta, date
from shiny import App, render, ui, reactive, req
import faicons as fa
import random

# ==========================================
# 1. DATABASE SETUP (OLTP)
# ==========================================
# We use SQLite to simulate a production database.
# In a real deployment, this would be PostgreSQL.

DB_NAME = "midwife.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Midwives Table
    c.execute('''CREATE TABLE midwives 
                 (id INTEGER PRIMARY KEY, name TEXT, email TEXT, phone TEXT, specialty TEXT)''')
    
    # Customers Table
    c.execute('''CREATE TABLE customers 
                 (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT)''')
    
    # Bookings Table (The Core OLTP Table)
    c.execute('''CREATE TABLE bookings 
                 (id INTEGER PRIMARY KEY, customer_id INTEGER, midwife_id INTEGER, 
                  start_time TIMESTAMP, end_time TIMESTAMP, status TEXT, 
                  created_at TIMESTAMP,
                  FOREIGN KEY(customer_id) REFERENCES customers(id),
                  FOREIGN KEY(midwife_id) REFERENCES midwives(id))''')
    
    # Seed Data
    midwives_data = [
        ('Sarah Jones', 'sarah@example.com', '+123456789', 'Postpartum Care'),
        ('Emily Blunt', 'emily@example.com', '+987654321', 'Lactation Consultant'),
        ('Jessica Wong', 'jess@example.com', '+112233445', 'Newborn Care')
    ]
    c.executemany("INSERT INTO midwives (name, email, phone, specialty) VALUES (?,?,?,?)", midwives_data)
    
    # Seed some past bookings for Analytics (OLAP)
    # Creating dummy data for last 30 days
    past_bookings = []
    for _ in range(20):
        m_id = random.randint(1, 3)
        c_id = random.randint(1, 50) # Dummy customer IDs
        days_ago = random.randint(1, 30)
        start = datetime.now() - timedelta(days=days_ago)
        end = start + timedelta(hours=4)
        past_bookings.append((c_id, m_id, start, end, 'Completed', datetime.now()))
        
    c.executemany("INSERT INTO bookings (customer_id, midwife_id, start_time, end_time, status, created_at) VALUES (?,?,?,?,?,?)", past_bookings)
    
    conn.commit()
    return conn

# Initialize DB connection globally for this single-file app
db_conn = init_db()

# Helper Functions
def get_midwives_df():
    return pd.read_sql("SELECT * FROM midwives", db_conn)

def get_bookings_df():
    query = """
    SELECT 
        b.id, c.name as customer_name, m.name as midwife_name, 
        b.start_time, b.end_time, b.status, m.email as midwife_email, c.phone as customer_phone
    FROM bookings b
    LEFT JOIN midwives m ON b.midwife_id = m.id
    LEFT JOIN customers c ON b.customer_id = c.id
    ORDER BY b.start_time DESC
    """
    df = pd.read_sql(query, db_conn)
    # Ensure datetime conversion
    df['start_time'] = pd.to_datetime(df['start_time'])
    df['end_time'] = pd.to_datetime(df['end_time'])
    return df

def check_overlap(midwife_id, start, end):
    # Logic to prevent double booking
    query = """
    SELECT count(*) FROM bookings 
    WHERE midwife_id = ? 
    AND status != 'Cancelled'
    AND (
        (start_time < ? AND end_time > ?) OR
        (start_time >= ? AND end_time <= ?)
    )
    """
    cursor = db_conn.cursor()
    # Note: sqlite requires string formatting for dates usually, but pandas handles it mostly. 
    # For raw SQL, we pass strings.
    cursor.execute(query, (midwife_id, end, start, start, end))
    count = cursor.fetchone()[0]
    return count > 0

# ==========================================
# 2. UI DEFINITION
# ==========================================

app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.style("""
            .card { margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .status-confirmed { color: green; font-weight: bold; }
            .status-pending { color: orange; font-weight: bold; }
            .status-completed { color: blue; }
            .metric-box { text-align: center; padding: 20px; background: #f8f9fa; border-radius: 8px; }
            .metric-value { font-size: 2em; font-weight: bold; color: #0d6efd; }
        """)
    ),
    ui.page_navbar(
        ui.nav_panel(
            "Operations Dashboard",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.h4("New Booking Order"),
                    ui.hr(),
                    ui.input_text("cust_name", "Customer Name", placeholder="e.g. Jane Doe"),
                    ui.input_text("cust_phone", "WhatsApp Number", placeholder="+62..."),
                    ui.input_text("cust_email", "Customer Email", placeholder="jane@email.com"),
                    ui.hr(),
                    ui.input_select("midwife_select", "Select Midwife", choices={}),
                    ui.input_date("booking_date", "Date"),
                    ui.input_select("booking_time", "Start Time", 
                                    choices=["08:00", "09:00", "10:00", "13:00", "14:00", "15:00"]),
                    ui.input_numeric("duration", "Duration (Hours)", value=2, min=1, max=8),
                    ui.input_action_button("submit_booking", "Create Booking", class_="btn-primary w-100"),
                    width=350
                ),
                ui.row(
                    ui.column(4, 
                        ui.div(
                            ui.h5("Today's Bookings"),
                            ui.div(ui.output_text("today_count"), class_="metric-value"),
                            class_="metric-box"
                        )
                    ),
                    ui.column(4, 
                         ui.div(
                            ui.h5("Active Midwives"),
                            ui.div(ui.output_text("active_midwives_count"), class_="metric-value"),
                            class_="metric-box"
                        )
                    ),
                    ui.column(4, 
                         ui.div(
                            ui.h5("Reminders Needed (D-1/D0)"),
                            ui.div(ui.output_text("reminder_count"), class_="metric-value", style="color: #dc3545;"),
                            class_="metric-box"
                        )
                    ),
                ),
                ui.br(),
                ui.card(
                    ui.card_header(ui.h4("Current Schedule & Order Status")),
                    ui.output_data_frame("bookings_table")
                ),
                ui.card(
                    ui.card_header("Manual Action Center"),
                    ui.layout_columns(
                         ui.input_text("manual_order_id", "Enter Booking ID for Reminder"),
                         ui.input_action_button("send_reminder_manual", "Send WhatsApp + Email Reminder", class_="btn-warning")
                    ),
                    ui.output_text_verbatim("reminder_log")
                )
            )
        ),
        ui.nav_panel(
            "Midwife Availability",
            ui.row(
                ui.column(4, ui.input_date("check_date", "Check Date", value=datetime.now().date())),
            ),
            ui.card(
                ui.card_header("Daily Schedule View"),
                ui.output_data_frame("availability_table")
            )
        ),
        ui.nav_panel(
            "Analytics (OLAP)",
            ui.row(
                ui.column(6,
                    ui.card(
                        ui.card_header("Bookings by Midwife (Performance)"),
                        ui.output_plot("plot_midwife_stats")
                    )
                ),
                ui.column(6,
                    ui.card(
                        ui.card_header("Booking Status Distribution"),
                        ui.output_plot("plot_status_dist")
                    )
                )
            )
        ),
        title=ui.row(
            ui.span(fa.icon_svg("baby-carriage"), " Midwife Connect", style="margin-right: 10px")
        ),
        id="main_nav"
    )
)

# ==========================================
# 3. SERVER LOGIC
# ==========================================

def server(input, output, session):
    
    # Reactive value to trigger updates across the app when data changes
    data_trigger = reactive.Value(0)

    # Populate Midwife Select Dropdown on Load
    @reactive.Effect
    def _update_midwife_choices():
        df = get_midwives_df()
        choices = {str(row['id']): f"{row['name']} ({row['specialty']})" for _, row in df.iterrows()}
        ui.update_select("midwife_select", choices=choices)

    # --- 3a. Booking Logic (Transaction) ---
    @reactive.Effect
    @reactive.event(input.submit_booking)
    def _handle_booking():
        # 1. Validation
        if not input.cust_name() or not input.cust_phone():
            ui.notification_show("Please fill in customer details", type="error")
            return

        # 2. Parse Date/Time
        try:
            date_str = input.booking_date().strftime("%Y-%m-%d")
            start_str = f"{date_str} {input.booking_time()}:00"
            start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            end_dt = start_dt + timedelta(hours=input.duration())
        except Exception as e:
            ui.notification_show("Invalid Date/Time", type="error")
            return

        midwife_id = int(input.midwife_select())

        # 3. Check Availability
        if check_overlap(midwife_id, start_dt, end_dt):
            ui.notification_show("Midwife is already booked for this slot!", type="error")
            return

        # 4. Save to DB (OLTP)
        cursor = db_conn.cursor()
        
        # Insert Customer (Simple upsert logic for demo)
        cursor.execute("INSERT INTO customers (name, phone, email) VALUES (?,?,?)", 
                       (input.cust_name(), input.cust_phone(), input.cust_email()))
        cust_id = cursor.lastrowid
        
        # Insert Booking
        cursor.execute("""
            INSERT INTO bookings (customer_id, midwife_id, start_time, end_time, status, created_at)
            VALUES (?, ?, ?, ?, 'Confirmed', ?)
        """, (cust_id, midwife_id, start_dt, end_dt, datetime.now()))
        
        db_conn.commit()
        
        # 5. Trigger System Updates
        data_trigger.set(data_trigger() + 1)
        
        # 6. Simulate Notifications
        ui.notification_show(f"Booking ID {cursor.lastrowid} Created!", type="message")
        ui.notification_show(f"WhatsApp sent to {input.cust_phone()}", type="success")
        ui.notification_show(f"Email sent to Midwife", type="success")
        ui.notification_show(f"Calendar Invite sent", type="success")

    # --- 3b. Dashboard & Data Tables ---

    @render.text
    def today_count():
        data_trigger() # dependency
        df = get_bookings_df()
        today = pd.Timestamp.now().normalize()
        # Filter for today
        count = len(df[df['start_time'].dt.normalize() == today])
        return str(count)

    @render.text
    def active_midwives_count():
        df = get_midwives_df()
        return str(len(df))

    @render.text
    def reminder_count():
        data_trigger()
        df = get_bookings_df()
        now = pd.Timestamp.now()
        # Filter logic: Start time is within next 24 hours (D-1 or D0) and status is Confirmed
        upcoming = df[
            (df['start_time'] > now) & 
            (df['start_time'] <= now + pd.Timedelta(days=1)) &
            (df['status'] == 'Confirmed')
        ]
        return str(len(upcoming))

    @render.data_frame
    def bookings_table():
        data_trigger()
        df = get_bookings_df()
        
        # Format for display
        display_df = df[['id', 'customer_name', 'midwife_name', 'start_time', 'end_time', 'status']].copy()
        display_df['start_time'] = display_df['start_time'].dt.strftime('%Y-%m-%d %H:%M')
        display_df['end_time'] = display_df['end_time'].dt.strftime('%H:%M')
        
        return render.DataGrid(display_df, selection_mode="row")

    # --- 3c. Manual Reminder System ---
    @render.text
    @reactive.event(input.send_reminder_manual)
    def reminder_log():
        oid = input.manual_order_id()
        if not oid:
            return "Please enter an Order ID."
        
        # Check if ID exists
        df = get_bookings_df()
        booking = df[df['id'] == int(oid)]
        
        if booking.empty:
            return f"Error: Order ID {oid} not found."
        
        row = booking.iloc[0]
        
        # Send Notification (Simulated)
        ui.notification_show(f"Reminder (D-1/D0) sent to {row['customer_name']} (WhatsApp)", duration=5)
        ui.notification_show(f"Reminder sent to {row['midwife_name']} (Email)", duration=5)
        
        return f"Success: Reminder triggered for Order #{oid} at {datetime.now().strftime('%H:%M:%S')}"

    # --- 3d. Availability View ---
    @render.data_frame
    def availability_table():
        data_trigger()
        check_date = pd.Timestamp(input.check_date())
        bookings = get_bookings_df()
        midwives = get_midwives_df()
        
        # Filter bookings for the selected date
        daily_bookings = bookings[bookings['start_time'].dt.normalize() == check_date]
        
        # Create a simple view: Midwife | 08:00 | 09:00 | ...
        # For simplicity in this grid, we just show list of bookings for that day per midwife
        
        availability_data = []
        for _, m in midwives.iterrows():
            m_bookings = daily_bookings[daily_bookings['midwife_name'] == m['name']]
            if m_bookings.empty:
                schedule = "Available all day"
            else:
                times = [f"{r['start_time'].strftime('%H:%M')}-{r['end_time'].strftime('%H:%M')}" for _, r in m_bookings.iterrows()]
                schedule = ", ".join(times)
            
            availability_data.append({
                "Midwife": m['name'],
                "Specialty": m['specialty'],
                "Schedule for " + check_date.strftime('%Y-%m-%d'): schedule
            })
            
        return render.DataGrid(pd.DataFrame(availability_data))

    # --- 3e. Analytics (OLAP) ---
    @render.plot
    def plot_midwife_stats():
        data_trigger()
        df = get_bookings_df()
        import matplotlib.pyplot as plt
        
        counts = df['midwife_name'].value_counts()
        
        fig, ax = plt.subplots(figsize=(8, 5))
        counts.plot(kind='bar', ax=ax, color='#0d6efd')
        ax.set_title("Total Bookings per Midwife")
        ax.set_ylabel("Count")
        plt.xticks(rotation=45)
        plt.tight_layout()
        return fig

    @render.plot
    def plot_status_dist():
        data_trigger()
        df = get_bookings_df()
        import matplotlib.pyplot as plt
        
        counts = df['status'].value_counts()
        
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(counts, labels=counts.index, autopct='%1.1f%%', colors=['#198754', '#ffc107', '#0dcaf0'])
        ax.set_title("Booking Status Distribution")
        return fig

app = App(app_ui, server)