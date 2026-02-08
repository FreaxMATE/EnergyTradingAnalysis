"""
Static plotting module using Bokeh.
"""
import sys
from pathlib import Path
import pandas as pd
from bokeh.plotting import figure, output_file, save
from bokeh.models import ColumnDataSource, HoverTool, Legend
from bokeh.layouts import column, row
from bokeh.palettes import Category20, Viridis256

import datamanager as dmng
from logger import setup_logger
from config import OUTPUT_DIR
logger = setup_logger(__name__)

def prepare_data(df, resample_rule=None):
    if df is None or df.empty: return df
    df = df.copy()
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], utc=True).dt.tz_localize(None)
    if resample_rule and 'time' in df.columns:
        df = df.set_index('time').resample(resample_rule).mean().reset_index()
    return df

def create_static_dashboard(country_code: str, dm=None):
    logger.info(f"Generating Bokeh report for {country_code}...")
    
    if dm is None:
        try: dm = dmng.DataManager(read_mode='feature')
        except Exception: return

    if country_code not in dm.data:
        logger.error(f"No data for {country_code}")
        return

    # 1. Load Data
    df_price = prepare_data(dm.data[country_code])
    
    df_ma = None
    if country_code in dm.features and 'ma' in dm.features[country_code]:
        df_ma = prepare_data(dm.features[country_code]['ma'])

    # Load Combined Forecasts (forecasts.csv)
    df_forecasts = None
    if country_code in dm.features and 'forecasts' in dm.features[country_code]:
        df_forecasts = prepare_data(dm.features[country_code]['forecasts'])
        
    df_gen = None
    if country_code in dm.generation_data:
        df_gen = prepare_data(dm.generation_data[country_code])

    # 2. Setup Output
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_file(filename=OUTPUT_DIR / f"report_{country_code}.html", title=f"Energy Analysis - {country_code}")

    # ---------------------------------------------------------
    # PLOT 1: Zoomed View
    # ---------------------------------------------------------
    last_time = df_price['time'].max()
    start_zoom = last_time - pd.Timedelta(days=3)
    df_price_zoom = df_price[df_price['time'] >= start_zoom]
    
    tools = "pan,wheel_zoom,box_zoom,reset,save,hover"
    p_zoom = figure(
        title=f"{country_code} - Short Term View (Last 3 Days + Forecast)",
        x_axis_type="datetime",
        height=500,
        sizing_mode="stretch_width",
        tools=tools,
        output_backend="webgl"
    )
    
    # Price
    p_zoom.line(df_price_zoom['time'], df_price_zoom['price'], line_width=3, color="#000000", legend_label="Actual Price", alpha=0.7)
    
    # Forecasts (Dynamic)
    if df_forecasts is not None:
        # Style mapping
        styles = {
            'forecast_hw': {'color': '#95a5a6', 'label': 'Holt-Winters', 'dash': 'solid', 'width': 2},
            'forecast_gb': {'color': '#27ae60', 'label': 'Gradient Boosting', 'dash': 'dashed', 'width': 3},
            'forecast_rf': {'color': '#2980b9', 'label': 'Random Forest', 'dash': 'dotted', 'width': 3}
        }
        
        for col in df_forecasts.columns:
            if col == 'time': continue
            
            style = styles.get(col, {'color': 'orange', 'label': col, 'dash': 'dashed', 'width': 1})
            
            p_zoom.line(
                df_forecasts['time'], 
                df_forecasts[col], 
                line_width=style['width'], 
                color=style['color'], 
                legend_label=style['label'], 
                line_dash=style['dash']
            )

    p_zoom.legend.click_policy = "hide"
    p_zoom.legend.location = "top_left"
    p_zoom.yaxis.axis_label = "Price (EUR/MWh)"

    # ---------------------------------------------------------
    # PLOT 2: Generation Mix
    # ---------------------------------------------------------
    p_gen = None
    if df_gen is not None and not df_gen.empty:
        start_gen = last_time - pd.Timedelta(days=90)
        df_gen_zoom = df_gen[df_gen['time'] >= start_gen].copy()
        df_gen_zoom = prepare_data(df_gen_zoom)
        df_gen_zoom = df_gen_zoom.fillna(0)
        num_cols = df_gen_zoom.select_dtypes(include=['number']).columns
        df_gen_zoom[num_cols] = df_gen_zoom[num_cols].clip(lower=0)
        
        if not df_gen_zoom.empty:
            gen_cols = [c for c in df_gen.columns if c != 'time']
            total_gen = df_gen_zoom[gen_cols].sum(axis=1)
            max_gen = total_gen.max() if not total_gen.empty else 0
            y_end = max_gen * 1.5 if max_gen > 0 else 100

            p_gen = figure(title=f"{country_code} - Generation Mix", x_axis_type="datetime", y_range=(0, y_end), height=500, sizing_mode="stretch_width", tools=tools, output_backend="webgl")
            
            num_cats = len(gen_cols)
            colors = Category20[20] * (num_cats // 20 + 1)
            colors = colors[:num_cats]

            p_gen.varea_stack(stackers=gen_cols, x='time', source=ColumnDataSource(df_gen_zoom), color=colors, legend_label=gen_cols)
            p_gen.legend.items = list(reversed(p_gen.legend.items))
            p_gen.legend.click_policy = "hide"
            p_gen.yaxis.axis_label = "Generation (MW)"

    # ---------------------------------------------------------
    # PLOT 3: Long Term
    # ---------------------------------------------------------
    df_price_long = prepare_data(df_price)
    p_long = figure(title=f"{country_code} - Long Term History", x_axis_type="datetime", height=300, sizing_mode="stretch_width", tools=tools, output_backend="webgl")
    p_long.line(df_price_long['time'], df_price_long['price'], color="#1f77b4", legend_label="Price", alpha=0.8)
    
    if df_ma is not None:
        df_ma_long = prepare_data(df_ma, resample_rule='12h')
        p_long.line(df_ma_long['time'], df_ma_long['ma'], color="#ff7f0e", line_width=2, legend_label="Moving Avg")

    p_long.yaxis.axis_label = "Price (EUR/MWh)"

    # Layout
    if p_gen: layout = column(row(p_zoom, p_gen, sizing_mode="stretch_width"), p_long, sizing_mode="stretch_width")
    else: layout = column(p_zoom, p_long, sizing_mode="stretch_width")
    
    save(layout)
    logger.info(f"Report saved to {OUTPUT_DIR / f'report_{country_code}.html'}")

def generate_index_html():
    report_files = list(OUTPUT_DIR.glob("report_*.html"))
    countries = sorted([f.stem.replace("report_", "") for f in report_files])
    if not countries: return

    country_items = ''.join(f'<div class="country-link" onclick="loadReport(\'{c}\', this)">{c}</div>' for c in countries)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <script defer src="http://104.248.29.240:3000/script.js" data-website-id="8ed65337-b55d-454d-92ca-5ca91511810d"></script>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Energy Trading Analysis Dashboard</title>
    <style>
        body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; display: flex; flex-direction: column; height: 100vh; overflow: hidden; background-color: #f8f9fa; }}
        #top-bar {{ height: 48px; background-color: #212529; color: white; display: flex; align-items: center; padding: 0 1rem; font-weight: 600; font-size: 1.1rem; flex-shrink: 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); z-index: 20; justify-content: space-between; }}
        .top-bar-left {{ display: flex; align-items: center; }}
        #sidebar-toggle {{ background: transparent; border: none; color: rgba(255,255,255,0.8); cursor: pointer; margin-right: 1rem; padding: 4px; border-radius: 4px; display: flex; align-items: center; }}
        #sidebar-toggle:hover {{ background-color: rgba(255,255,255,0.1); color: white; }}
        .github-link {{ color: rgba(255,255,255,0.8); display: flex; align-items: center; text-decoration: none; transition: color 0.2s; }}
        .github-link:hover {{ color: white; }}
        #main-layout {{ display: flex; flex: 1; overflow: hidden; }}
        #sidebar {{ width: 260px; min-width: 0; flex-shrink: 0; background-color: #ffffff; border-right: 1px solid #dee2e6; display: flex; flex-direction: column; box-shadow: 2px 0 5px rgba(0,0,0,0.05); z-index: 10; overflow: hidden; white-space: nowrap; }}
        #sidebar.collapsed {{ width: 0; border-right: none; }}
        .sidebar-header {{ padding: 1rem 1.5rem; border-bottom: 1px solid #f0f0f0; background-color: #f8f9fa; }}
        .sidebar-header h3 {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1.2px; margin: 0; color: #6c757d; font-weight: 700; }}
        #country-list {{ flex: 1; overflow-y: auto; padding: 1rem; }}
        .country-link {{ display: block; padding: 0.75rem 1rem; margin-bottom: 0.25rem; color: #495057; text-decoration: none; border-radius: 0.375rem; transition: all 0.2s ease; cursor: pointer; font-size: 0.95rem; border: 1px solid transparent; }}
        .country-link:hover {{ background-color: #f1f3f5; color: #212529; }}
        .country-link.active {{ background-color: #e7f1ff; color: #0d6efd; border-color: #cce5ff; font-weight: 500; }}
        #content {{ flex: 1; display: flex; flex-direction: column; position: relative; }}
        iframe {{ width: 100%; height: 100%; border: none; background: white; }}
        #placeholder {{ display: flex; align-items: center; justify-content: center; height: 100%; color: #adb5bd; font-size: 1.2rem; flex-direction: column; gap: 1rem; }}
    </style>
</head>
<body>
    <div id="top-bar">
        <div class="top-bar-left">
            <button id="sidebar-toggle" onclick="toggleSidebar()" title="Toggle Sidebar">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
            </button>
            Energy Trading Analysis
        </div>
        <a href="https://github.com/FreaxMATE/EnergyTradingAnalysis" target="_blank" class="github-link" title="View on GitHub">
            <svg height="24" width="24" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>
        </a>
    </div>
    <div id="main-layout">
        <div id="sidebar">
            <div class="sidebar-header">
                <h3>Bidding Zone</h3>
            </div>
            <div id="country-list">{country_items}</div>
        </div>
        <div id="content">
            <div id="placeholder"><div>Select a bidding zone to view the report</div></div>
            <iframe id="report-frame" style="display: none;"></iframe>
        </div>
    </div>
    <script>
        function toggleSidebar() {{ document.getElementById('sidebar').classList.toggle('collapsed'); }}
        function loadReport(countryCode, element) {{
            const frame = document.getElementById('report-frame');
            const placeholder = document.getElementById('placeholder');
            frame.src = `report_${{countryCode}}.html`;
            frame.style.display = 'block';
            placeholder.style.display = 'none';
            document.querySelectorAll('.country-link').forEach(el => el.classList.remove('active'));
            if (element) {{ element.classList.add('active'); }}
        }}
        const firstLink = document.querySelector('.country-link');
        if (firstLink) {{ firstLink.click(); }}
    </script>
</body>
</html>"""
    
    index_path = OUTPUT_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Dashboard index generated at {index_path}")

if __name__ == "__main__":
    try: dm_main = dmng.DataManager(read_mode='feature')
    except Exception as e:
        logger.error(f"Failed to init DataManager: {e}")
        sys.exit(1)

    if len(sys.argv) > 1:
        country = sys.argv[1]
        create_static_dashboard(country, dm=dm_main)
    else:
        print("Generating reports for all available countries...")
        for country in dm_main.data.keys():
            create_static_dashboard(country, dm=dm_main)
            
    generate_index_html()