import pandas as pd
import numpy as np
import plotly.express as px

import datamanager as dmng

class Plot():
    def __init__(self, dm) -> None:
        print(dm.data)
        print(dm.data['DK_2'].price)
        self.price = dm.data['DK_2'].price
        self.time = dm.data['DK_2'].time
        fig = px.line(x=self.time, y=self.price)
        fig.show()



if __name__ == '__main__':
    dm = dmng.DataManager()
    plot = Plot(dm)
