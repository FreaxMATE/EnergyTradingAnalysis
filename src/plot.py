"""Plotting and visualization module for the Energy Trading Analysis application."""

from typing import Tuple
import pandas as pd
import plotly
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, html, dcc, callback, Output, Input

import datamanager as dmng
import utils
from logger import setup_logger
from config import DASH_HOST, DASH_PORT, DASH_DEBUG
from exceptions import DataException

logger = setup_logger(__name__)
plotly.io.templates.default = "plotly_white"


def create_dash_app() -> Dash:
    """
    Create and configure the Dash application.
    
    Returns:
        Dash: Configured Dash application instance
    
    Raises:
        DataException: If data cannot be loaded
    """
    try:
        dm = dmng.DataManager(read_mode='feature')
        logger.info("DataManager initialized for Dash app")
    except Exception as e:
        logger.error(f"Failed to initialize DataManager: {e}")
        raise DataException(f"Failed to initialize DataManager: {e}")

    app = Dash(__name__)
    
    # Set app title and layout
    app.title = 'Energy Trading Analysis'
    app.layout = html.Div([
        html.H1(
            children='Energy Trading Analysis',
            style={'textAlign': 'center', 'marginBottom': 30}
        ),
        dcc.Dropdown(
            dm.country_codes.tolist(),
            'DK_2',
            id='dropdown-selection',
            style={'marginBottom': 20}
        ),
        html.Div([
            html.Div([
                html.H2(children='Last 48 Hours Price'),
                dcc.Graph(id='graph-content-24h', style={'width': '100%', 'height': '400px'})
            ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            html.Div([
                html.H2(children='Generation Mix'),
                dcc.Graph(id='graph-content-generation', style={'width': '100%', 'height': '400px'})
            ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'})
        ], style={'width': '100%', 'display': 'flex'}),
        html.H2(children='Full Range Price'),
        dcc.Graph(id='graph-content', style={'width': '100%', 'height': '400px'})
    ], style={'width': '100%'})
    
    server = app.server

    @app.callback(
        [Output('graph-content', 'figure'), Output('graph-content-24h', 'figure'), Output('graph-content-generation', 'figure')],
        [Input('dropdown-selection', 'value')]
    )
    def update_graphs(selected_country: str) -> Tuple[go.Figure, go.Figure, go.Figure]:
        """
        Update graphs based on selected country.
        
        Args:
            selected_country (str): Selected country code
        
        Returns:
            Tuple[go.Figure, go.Figure, go.Figure]: Full range figure, 24h figure, and generation figure
        """
        try:
            df = dm.data[selected_country]
            logger.debug(f"Loaded data for {selected_country}")
            
            # Try to get moving average from features
            ma_df = None
            try:
                ma_df = dm.features[selected_country]['ma']
                if ma_df is not None and 'time' in ma_df.columns:
                    ma_df['time'] = pd.to_datetime(ma_df['time'], utc=True)
                logger.debug(f"Loaded moving average for {selected_country}")
            except (KeyError, Exception) as e:
                logger.debug(f"Moving average not available for {selected_country}: {e}")

            # Try to get forecast from features
            forecast_df = None
            try:
                forecast_df = dm.features[selected_country]['forecast']
                if forecast_df is not None and 'time' in forecast_df.columns:
                    forecast_df['time'] = pd.to_datetime(forecast_df['time'], utc=True)
                logger.debug(f"Loaded forecast for {selected_country}")
            except (KeyError, Exception) as e:
                logger.debug(f"Forecast not available for {selected_country}: {e}")

            # Full range plot
            fig = px.line(
                title=f'Price and Moving Average for {selected_country}',
                labels={'time': 'Time', 'price': 'Price (EUR/MWh)'}
            )
            fig.add_scatter(
                x=df['time'],
                y=df['price'],
                mode='lines',
                name='Price',
                line=dict(color='#1f77b4')
            )
            if ma_df is not None:
                fig.add_scatter(
                    x=ma_df['time'],
                    y=ma_df['ma'],
                    mode='lines',
                    name='Moving Average (24h)',
                    line=dict(color='#ff7f0e')
                )
            if forecast_df is not None:
                # Find all forecast columns
                forecast_cols = [col for col in forecast_df.columns if col.startswith('forecast_')]
                
                # Fallback for backward compatibility
                if not forecast_cols:
                     forecast_cols = [col for col in forecast_df.columns if col.endswith('_forecast')]

                # Sort columns to ensure consistent coloring/ordering if needed
                forecast_cols.sort()
                
                # Take every 2nd forecast to reduce clutter
                forecast_cols = forecast_cols[::2]
                
                num_forecasts = len(forecast_cols)
                for i, col in enumerate(forecast_cols):
                    name = f'Forecast {i+1}'
                    if col.startswith('forecast_'):
                        ts_str = col.replace('forecast_', '')
                        # Try to format timestamp nicely
                        try:
                            dt = pd.to_datetime(ts_str, format='%Y%m%d%H%M')
                            name = f'Fcst {dt.strftime("%m-%d %H:%M")}'
                        except:
                            pass
                    
                    # Calculate opacity: newer forecasts (higher i) are darker
                    opacity = 0.3 + 0.7 * (i / max(1, num_forecasts - 1))
                    
                    # Use Viridis colorscale
                    sample_val = i / max(1, num_forecasts - 1)
                    rgb_color = px.colors.sample_colorscale('Viridis', [sample_val])[0]
                    
                    if rgb_color.startswith('rgb('):
                        color = rgb_color.replace('rgb(', 'rgba(').replace(')', f', {opacity:.2f})')
                    else:
                        color = rgb_color

                    fig.add_scatter(
                        x=forecast_df['time'],
                        y=forecast_df[col],
                        mode='lines',
                        name=name,
                        line=dict(color=color)
                    )

            fig.update_xaxes(title_text='Time')
            fig.update_yaxes(title_text='Price (EUR/MWh)')

            # Zoomed plot (Last 2 days + 2 days future)
            last_time = df['time'].max()
            start_zoom = last_time - pd.Timedelta(days=2)
            end_zoom = last_time + pd.Timedelta(days=2)

            fig_24h = px.line(
                title=f'Zoomed View: Last 2 Days & Forecast for {selected_country}',
                labels={'time': 'Time', 'price': 'Price (EUR/MWh)'}
            )
            
            if ma_df is not None:
                fig_24h.add_scatter(
                    x=ma_df['time'],
                    y=ma_df['ma'],
                    mode='lines',
                    name='Moving Average (24h)',
                    line=dict(color='#ff7f0e')
                )
            
            # Add Price
            fig_24h.add_scatter(
                x=df['time'],
                y=df['price'],
                mode='lines',
                name='Price',
                line=dict(color='#1f77b4')
            )

            if forecast_df is not None:
                # Use the same forecast_cols as main plot (already sliced)
                num_forecasts = len(forecast_cols)
                for i, col in enumerate(forecast_cols):
                    name = f'Forecast {i+1}'
                    if col.startswith('forecast_'):
                        ts_str = col.replace('forecast_', '')
                        try:
                            dt = pd.to_datetime(ts_str, format='%Y%m%d%H%M')
                            name = f'Fcst {dt.strftime("%m-%d %H:%M")}'
                        except:
                            pass
                    
                    # Calculate opacity: newer forecasts (higher i) are darker
                    opacity = 0.3 + 0.7 * (i / max(1, num_forecasts - 1))
                    
                    # Use Viridis colorscale
                    sample_val = i / max(1, num_forecasts - 1)
                    rgb_color = px.colors.sample_colorscale('Viridis', [sample_val])[0]
                    
                    if rgb_color.startswith('rgb('):
                        color = rgb_color.replace('rgb(', 'rgba(').replace(')', f', {opacity:.2f})')
                    else:
                        color = rgb_color

                    fig_24h.add_scatter(
                        x=forecast_df['time'],
                        y=forecast_df[col],
                        mode='lines',
                        name=name,
                        line=dict(color=color)
                    )

            # Calculate Y-axis range for zoomed plot
            y_values = []
            
            # Check Price
            mask_price = (df['time'] >= start_zoom) & (df['time'] <= end_zoom)
            if mask_price.any():
                y_values.append(df.loc[mask_price, 'price'])
            
            # Check MA
            if ma_df is not None:
                mask_ma = (ma_df['time'] >= start_zoom) & (ma_df['time'] <= end_zoom)
                if mask_ma.any():
                    y_values.append(ma_df.loc[mask_ma, 'ma'])
            
            # Check Forecasts
            if forecast_df is not None:
                mask_forecast = (forecast_df['time'] >= start_zoom) & (forecast_df['time'] <= end_zoom)
                if mask_forecast.any():
                    for col in forecast_cols:
                        if col in forecast_df.columns:
                             y_values.append(forecast_df.loc[mask_forecast, col])

            fig_24h.update_xaxes(range=[start_zoom, end_zoom], title_text='Time')
            
            if y_values:
                combined_y = pd.concat(y_values)
                y_min = combined_y.min()
                y_max = combined_y.max()
                
                if pd.notna(y_min) and pd.notna(y_max):
                    padding = (y_max - y_min) * 0.05
                    if padding == 0: padding = 1.0
                    fig_24h.update_yaxes(range=[y_min - padding, y_max + padding], title_text='Price (EUR/MWh)')
                else:
                    fig_24h.update_yaxes(title_text='Price (EUR/MWh)')
            else:
                fig_24h.update_yaxes(title_text='Price (EUR/MWh)')
            
            # Generation Plot
            fig_gen = go.Figure()
            try:
                gen_data = dm.generation_data.get(selected_country)
                if gen_data is not None and not gen_data.empty:
                    gen_cols = [c for c in gen_data.columns if c != 'time']
                    fig_gen = px.area(
                        gen_data,
                        x='time',
                        y=gen_cols,
                        title=f'Generation Mix - {selected_country}'
                    )
                    fig_gen.update_xaxes(title_text='Time')
                    fig_gen.update_yaxes(title_text='MW')
                else:
                    fig_gen.add_annotation(text="No generation data available", showarrow=False)
                    fig_gen.update_layout(title=f'Generation Mix - {selected_country}')
            except Exception as e:
                logger.error(f"Error plotting generation for {selected_country}: {e}")
                fig_gen.add_annotation(text=f"Error: {e}", showarrow=False)

            logger.info(f"Graphs updated for {selected_country}")
            return fig, fig_24h, fig_gen
        
        except KeyError:
            logger.error(f"Data not available for {selected_country}")
            empty_fig = px.line(title=f'No data available for {selected_country}')
            return empty_fig, empty_fig, empty_fig
        except Exception as e:
            logger.error(f"Error updating graphs: {e}")
            empty_fig = px.line(title=f'Error loading data: {str(e)}')
            return empty_fig, empty_fig, empty_fig

    return app


def run_dash_app(host: str = DASH_HOST, port: int = DASH_PORT, debug: bool = DASH_DEBUG) -> None:
    """
    Run the Dash application.
    
    Args:
        host (str): Host to run the app on
        port (int): Port to run the app on
        debug (bool): Whether to run in debug mode
    """
    try:
        logger.info(f"Starting Dash app on {host}:{port}")
        app = create_dash_app()
        app.run(host=host, port=port, debug=debug)
    except Exception as e:
        logger.error(f"Failed to run Dash app: {e}")
        raise