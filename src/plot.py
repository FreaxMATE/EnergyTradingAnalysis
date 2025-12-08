import pandas as pd
import numpy as np
import plotly.express as px
import plotly
from dash import Dash, html, dcc, callback, Output, Input
import datamanager as dmng
import logging
import utils

plotly.io.templates.default = "plotly_white"

def create_dash_app():
    dm = dmng.DataManager(read_mode='feature')
    app = Dash(__name__)
    app.layout = [
        html.H1(children='Energy Trading Analysis', style={'textAlign':'center'}),
        dcc.Dropdown(dm.country_codes.tolist(), 'DK_2', id='dropdown-selection'),
        html.H2(children='Last 24 Hours'),
        dcc.Graph(id='graph-content-24h'),
        dcc.Graph(id='graph-content')
    ]
    server = app.server

    @app.callback(
        [Output('graph-content', 'figure'), Output('graph-content-24h', 'figure')],
        [Input('dropdown-selection', 'value')]
    )
    def update_graphs(value):
        df = dm.data[value]
        # Try to get moving average from features
        ma_df = None
        try:
            ma_df = dm.features[value]['ma']
        except Exception:
            print('Could not find MA')
            pass

        # Full range plot
        fig = px.line()
        fig.add_scatter(x=df['time'], y=df['price'], mode='lines', name='Price')
        if ma_df is not None:
            fig.add_scatter(x=ma_df['time'], y=ma_df['ma'], mode='lines', name='Moving Average')
        fig.update_layout(title=f'Price and Moving Average for {value}', xaxis_title='time', yaxis_title='Price')

        # Last 24 hours plot
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

        df_24h = utils.extract_last(df, pd.Timedelta(hours=24))
        fig_24h = px.line()
        if ma_df is not None:
            ma_df_24h = utils.extract_last(ma_df, pd.Timedelta(hours=24))
            fig_24h.add_scatter(x=ma_df_24h['time'], y=ma_df_24h['ma'], mode='lines', name='Moving Average')
        fig_24h.add_scatter(x=df_24h['time'], y=df_24h['price'], mode='lines', name='Price')
        fig_24h.update_layout(title=f'Last 24 Hours for {value}', xaxis_title='time', yaxis_title='Price')
        return fig, fig_24h

    return app

def run_dash_app():
    app = create_dash_app()
    app.run(debug=True)