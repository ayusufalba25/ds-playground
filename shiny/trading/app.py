from shiny import App
from ui import app_ui
from server import server

# This ties the UI and Server logic together
app = App(app_ui, server)