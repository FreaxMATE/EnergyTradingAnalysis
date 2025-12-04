import pandas as pd
import numpy as np
import plotly.express as px
import plotly
from dash import Dash, html, dcc, callback, Output, Input
import datamanager as dmng

plotly.io.templates.default = "plotly_white"

dm = dmng.DataManager()
app = Dash(__name__)
app.layout = [
    html.H1(children='Energy Trading Analysis', style={'textAlign':'center'}),
    dcc.Dropdown(dm.country_codes.tolist(), 'DK_2', id='dropdown-selection'),
    dcc.Graph(id='graph-content')
]
server = app.server

@callback(
    Output('graph-content', 'figure'),
    Input('dropdown-selection', 'value')
)
def update_graph(value):
    return px.line(dm.data[value], x='time', y='price')

if __name__ == '__main__':
    app.run(debug=True)