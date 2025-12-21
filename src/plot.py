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
    app.layout = [
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
        html.H2(children='Last 24 Hours'),
        dcc.Graph(id='graph-content-24h'),
        html.H2(children='Full Range'),
        dcc.Graph(id='graph-content')
    ]
    
    server = app.server

    @app.callback(
        [Output('graph-content', 'figure'), Output('graph-content-24h', 'figure')],
        [Input('dropdown-selection', 'value')]
    )
    def update_graphs(selected_country: str) -> Tuple[go.Figure, go.Figure]:
        """
        Update graphs based on selected country.
        
        Args:
            selected_country (str): Selected country code
        
        Returns:
            Tuple[go.Figure, go.Figure]: Full range figure and 24h figure
        """
        try:
            df = dm.data[selected_country]
            logger.debug(f"Loaded data for {selected_country}")
            
            # Try to get moving average from features
            ma_df = None
            try:
                ma_df = dm.features[selected_country]['ma']
                logger.debug(f"Loaded moving average for {selected_country}")
            except (KeyError, Exception) as e:
                logger.debug(f"Moving average not available for {selected_country}: {e}")

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
                    line=dict(color='#ff7f0e', dash='dash')
                )
            fig.update_xaxes(title_text='Time')
            fig.update_yaxes(title_text='Price (EUR/MWh)')

            # Last 24 hours plot
            df_24h = utils.extract_last(df, pd.Timedelta(hours=24))
            fig_24h = px.line(
                title=f'Last 24 Hours for {selected_country}',
                labels={'time': 'Time', 'price': 'Price (EUR/MWh)'}
            )
            
            if ma_df is not None:
                ma_df_24h = utils.extract_last(ma_df, pd.Timedelta(hours=24))
                fig_24h.add_scatter(
                    x=ma_df_24h['time'],
                    y=ma_df_24h['ma'],
                    mode='lines',
                    name='Moving Average (24h)',
                    line=dict(color='#ff7f0e', dash='dash')
                )
            
            fig_24h.add_scatter(
                x=df_24h['time'],
                y=df_24h['price'],
                mode='lines',
                name='Price',
                line=dict(color='#1f77b4')
            )
            fig_24h.update_xaxes(title_text='Time')
            fig_24h.update_yaxes(title_text='Price (EUR/MWh)')
            
            logger.info(f"Graphs updated for {selected_country}")
            return fig, fig_24h
        
        except KeyError:
            logger.error(f"Data not available for {selected_country}")
            empty_fig = px.line(title=f'No data available for {selected_country}')
            return empty_fig, empty_fig
        except Exception as e:
            logger.error(f"Error updating graphs: {e}")
            empty_fig = px.line(title=f'Error loading data: {str(e)}')
            return empty_fig, empty_fig

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