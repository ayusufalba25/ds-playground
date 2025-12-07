from shiny import App, ui, render

# Define the user interface (UI)
# app_ui = ui.page_fluid(
#     ui.h2("Slider Example"),
#     ui.input_slider("my_slider", "Select a value:", min=0, max=100, value=50),
#     ui.output_text("slider_value"),
# )

def input_data():
    return ui.input_slider("my_slider", "Select a value:", min=0, max=100, value=50)

app_ui = ui.page_fluid(
    ui.h2("Slider example"),
    input_data(),
    ui.output_text("slider_value")
)

# Define the server logic
def server(input, output, session):
    @output
    @render.text
    def slider_value():
        return f"The current slider value is: {input.my_slider()}"

# Create the Shiny app
app = App(app_ui, server)