from entsoe import EntsoePandasClient
import pandas as pd
import os
import utils
import numpy as np
import inspect
import dataanalysis
from dotenv import load_dotenv

# Directly import variables from config
from config import DEBUG, START_OF_15_MIN_SPOT_PRICE

# Load environment variables from .env file
load_dotenv()

class DataManager():
    def __init__(self, read_mode: str = '') -> None:
        self.__directory = 'data'
        self.__country_codes_full = pd.read_csv('src/country_codes.csv', dtype=str, delimiter=',', comment='#')
        self.__country_codes = self.__country_codes_full['code']
        # {country_code: price_data([time, price])}
        self.__data = self.__read_data() if read_mode == 'data' or read_mode == 'feature' else None
        self.__features = self.__read_features() if read_mode == 'feature' else None 

    @property
    def data(self):
        return self.__data

    @property
    def features(self):
        return self.__features

    @property
    def country_codes(self):
        return self.__country_codes

    def __read_data(self):
        return {country_code: pd.DataFrame(pd.read_csv('data/'+country_code+'/'+country_code+'.csv', delimiter=',', names=['time', 'price'], skiprows=1, comment='#')) for country_code in self.__country_codes}

    def __read_features(self):
        directory = f"{self.__directory}/"
        filename = f"features.csv"   
        filepath = os.path.join(directory, filename)
        features = pd.read_csv(filepath, header=0)
        feature_names = features.columns.tolist()
        return {country_code: {feature: pd.DataFrame(pd.read_csv('data/'+country_code+'/'+country_code+'_'+feature+'.csv', delimiter=',', comment='#')) for feature in feature_names} for country_code in self.__country_codes}

    def analysis_by_country_code(self, country_code: str):
        self.save_analysis(country_code=country_code, df=dataanalysis.ma(df=self.__data[country_code]), feature='ma')

    def analysis(self):
        for country_code in self.country_codes:
            self.analysis_by_country_code(country_code=country_code)

        directory = f"{self.__directory}/"
        filename = f"features.csv"   
        filepath = os.path.join(directory, filename)
        with open(filepath, 'a') as f:
            f.write('ma\n')


    def save_analysis(self, country_code: str, df: pd.DataFrame, feature: str = 'ma'):
        """
        Save analysis DataFrame (e.g., moving average) to CSV in the country's data directory.
        Args:
            country_code (str): Country code (e.g., 'FR')
            df (pd.DataFrame): DataFrame to save
            feature (str): Analysis feature, also the suffix for the filename (default: 'ma')
        """

        directory = f"{self.__directory}/{country_code}/"
        filename = f"{country_code}_{feature}.csv"
        filepath = os.path.join(directory, filename)
        df.to_csv(filepath, index=False)
        print(f"Saved analysis to {filepath}")

    def download_by_country_code(self, client, country_code, start_date, end_date):
        print('Start Downloading: ', country_code)
        directory = self.__directory+'/'+country_code+'/'
        filepath = directory+country_code+'.csv'
        append = False
        try:
            if os.path.exists(filepath):
                print('  Evaluating Existing File...', end='', flush=True)
                last_line = utils.read_last_csv_line(filepath)
                last_saved_time = pd.Timestamp(last_line.strip().split(',')[0], tz='Europe/Brussels')
                if last_saved_time > START_OF_15_MIN_SPOT_PRICE:
                    start_date = last_saved_time + pd.Timedelta(minutes=15)
                else:
                    start_date = last_saved_time + pd.Timedelta(hours=1)
                append = True
                print('  ✓')
        except Exception as e:
            print(f"Exception: {e}")
        print('  Start Fetching Data... ', end='', flush=True)
        day_ahead_prices = client.query_day_ahead_prices(country_code, start_date, end_date)
        print('  ✓')
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
            if append == False:
                day_ahead_prices.to_csv(filepath)
            else:
                day_ahead_prices.to_csv(filepath, mode='a', header=False)
        except Exception as e:
            print(f"Exception: {e}")
        print('Finished Downloading: ', country_code)

    def download(self):
        api_key = os.getenv('ENTSOE_API_KEY')
        if not api_key:
            raise ValueError("ENTSOE_API_KEY not found in environment variables. Please set it in .env file")
        client = EntsoePandasClient(api_key=api_key)
        start_date = pd.Timestamp('20250101', tz='Europe/Brussels')
        end_date = pd.Timestamp.today(tz='Europe/Brussels').round(freq='h')
        for i, country_code in enumerate(self.__country_codes):
            self.download_by_country_code(client, country_code, start_date, end_date)

if __name__ == '__main__':
    data_manager = DataManager()
    data_manager.download()
