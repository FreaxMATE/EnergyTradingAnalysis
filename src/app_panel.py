import panel as pn
import pandas as pd
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.palettes import Category20, Viridis256
import datamanager as dmng
from logger import setup_logger

# Initialize Panel extension
pn.extension(sizing_mode="stretch_width")

logger = setup_logger(__name__)

# 1. Initialize DataManager
try:
    dm = dmng.DataManager(read_mode='feature')
    available_countries = sorted(list(dm.data.keys()))
except Exception as e:
    logger.error(f"Failed to init DataManager: {e}")
    available_countries = []
    dm = None

# 2. Widgets
country_select = pn.widgets.Select(name='Country', options=available_countries)

# 3. Callbacks
@pn.depends(country_code=country_select)
def create_plots(country_code):
    if not country_code or not dm:
        return pn.pane.Markdown("### No Data Available")
    
    # Filter Data
    df_price = dm.data.get(country_code)
    if df_price is None:
        return pn.pane.Markdown(f"### No price data for {country_code}")
        
    # Ensure time column is datetime
    if not pd.api.types.is_datetime64_any_dtype(df_price['time']):
        df_price['time'] = pd.to_datetime(df_price['time'], utc=True)

    df_price_view = df_price
    
    if df_price_view.empty:
        return pn.pane.Markdown("### No data available")

    # Get other data
    df_forecast = None
    if country_code in dm.features and 'forecast' in dm.features[country_code]:
        df_forecast = dm.features[country_code]['forecast']
        
    df_gen = None
    if country_code in dm.generation_data:
        df_gen = dm.generation_data[country_code]

    # --- Plot 1: Price & Forecast ---
    tools = "pan,wheel_zoom,box_zoom,reset,save,hover"
    p_price = figure(
        title=f"{country_code} - Price History",
        x_axis_type="datetime",
        height=400,
        sizing_mode="stretch_width",
        tools=tools,
        active_scroll="wheel_zoom"
    )
    
    p_price.line(df_price_view['time'], df_price_view['price'], line_width=2, color="#1f77b4", legend_label="Price")
    
    # Add Forecasts if available
    if df_forecast is not None:
        if not pd.api.types.is_datetime64_any_dtype(df_forecast['time']):
            df_forecast['time'] = pd.to_datetime(df_forecast['time'], utc=True)
            
        df_forecast_view = df_forecast
        
        if not df_forecast_view.empty:
            f_cols = [c for c in df_forecast.columns if c.startswith('forecast_') or c.endswith('_forecast')]
            f_cols.sort()
            f_cols = f_cols[-5:] # Limit to 5 recent
            
            for i, col in enumerate(f_cols):
                color = Viridis256[int(i / max(1, len(f_cols)-1) * 200)]
                p_price.line(df_forecast_view['time'], df_forecast_view[col], line_width=1, color=color, alpha=0.6, legend_label="Forecast")

    p_price.legend.click_policy = "hide"
    p_price.yaxis.axis_label = "Price (EUR/MWh)"

    # --- Plot 2: Generation Mix ---
    p_gen = None
    if df_gen is not None:
        if not pd.api.types.is_datetime64_any_dtype(df_gen['time']):
            df_gen['time'] = pd.to_datetime(df_gen['time'], utc=True)
            
        df_gen_view = df_gen.copy()
        
        if not df_gen_view.empty:
            p_gen = figure(
                title=f"{country_code} - Generation Mix",
                x_axis_type="datetime",
                height=300,
                sizing_mode="stretch_width",
                x_range=p_price.x_range, # Link axes
                tools=tools
            )
            
            gen_cols = [c for c in df_gen.columns if c != 'time']
            num_cats = len(gen_cols)
            if num_cats < 3:
                colors = ["#1f77b4", "#ff7f0e"][:num_cats]
            elif num_cats > 20:
                colors = (Category20[20] * (num_cats // 20 + 1))[:num_cats]
            else:
                colors = Category20[num_cats]

            p_gen.varea_stack(
                stackers=gen_cols,
                x='time',
                source=ColumnDataSource(df_gen_view),
                color=colors,
                legend_label=gen_cols
            )
            p_gen.legend.items = list(reversed(p_gen.legend.items))
            p_gen.legend.click_policy = "hide"
            p_gen.yaxis.axis_label = "Generation (MW)"

    plots = [p_price]
    if p_gen:
        plots.append(p_gen)
        
    return pn.Column(*plots, sizing_mode="stretch_width")

# 4. Layout
template = pn.template.FastListTemplate(
    title='Energy Trading Analysis Dashboard',
    sidebar=[
        pn.pane.Markdown("## Settings"),
        country_select
    ],
    main=[create_plots],
    accent_base_color="#1f77b4",
    header_background="#1f77b4",
)

template.servable()

if __name__ == "__main__":
    # For local testing
    template.show()
