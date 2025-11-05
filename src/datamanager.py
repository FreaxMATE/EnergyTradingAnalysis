from entsoe import EntsoePandasClient
import pandas as pd
import os

class DataManager():
    def __init__(self) -> None:
        self.__directory = 'data'
        self.__country_codes_full = pd.read_csv('src/country_codes.csv', dtype=str, delimiter=',', comment='#')
        self.__country_codes = self.__country_codes_full['code']
        self.__data = self.__read_data()

    @property
    def data(self):
        return self.__data

    @property
    def country_codes(self):
        return self.__country_codes

    def __read_data(self):
        return {country_code: pd.DataFrame(pd.read_csv('data/'+country_code+'/'+country_code+'.csv', delimiter=',', names=['time', 'price'], skiprows=1, comment='#')) for country_code in self.__country_codes}

    def download_by_country_code(self, client, country_code, start_date, end_date):
        day_ahead_prices = client.query_day_ahead_prices(country_code, start_date, end_date)
        try:
            directory = self.__directory+'/'+country_code+'/'
            if not os.path.exists(directory):
                os.makedirs(directory)
            day_ahead_prices.to_csv(directory+country_code+'.csv')
        except Exception as e:
            print(f"Exception: {e}")
        print('Finished download of ', country_code)

    def download(self):
        client = EntsoePandasClient(api_key='682f38f9-67e8-4efb-b482-70f1945ab45e')
        start_date = pd.Timestamp('20250101', tz='Europe/Brussels')
        end_date = pd.Timestamp('20250601', tz='Europe/Brussels')
        for i, country_code in enumerate(self.__country_codes):
            self.download_by_country_code(client, country_code, start_date, end_date)

if __name__ == '__main__':
    data_manager = DataManager()
    data_manager.download()
