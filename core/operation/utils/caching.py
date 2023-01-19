import hashlib
import os
import timeit

import pandas as pd
from fedot.core.log import default_log as Logger

from core.architecture.utils.utils import PROJECT_PATH


class DataCacher:
    """Class responsible for caching data of ``pd.DataFrame`` type in pickle format.

    Args:
        data_type_prefix: a string prefix related to the data to be cached. For example, if data is related to
        modelling results, then the prefix can be 'ModellingResults'. Default prefix is 'Data'.
        cache_folder: path to the folder where data is going to be cached.

    Examples:
        >>> your_data = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        >>> data_cacher = DataCacher(data_type_prefix='data', cache_folder='your_path')
        >>> hashed_info = data_cacher.hash_info(dict(name='data', data=your_data))
        >>> data_cacher.cache_data(hashed_info, your_data)
        >>> data_cacher.load_data_from_cache(hashed_info)
    """

    def __init__(self, data_type_prefix: str = 'Data', cache_folder: str = None):
        self.logger = Logger(self.__class__.__name__)
        self.data_type = data_type_prefix
        self.cache_folder = cache_folder
        os.makedirs(cache_folder, exist_ok=True)

    def hash_info(self, **kwargs) -> str:
        """Method responsible for hashing distinct information about the data that is going to be cached.
        It utilizes md5 hashing algorithm.

        Args:
            kwargs: a set of keyword arguments to be used as distinct info about data.

        Returns:
            Hashed string.
        """
        key = ''.join([repr(arg) for arg in kwargs.values()]).encode('utf8')
        hsh = hashlib.md5(key).hexdigest()[:10]
        return hsh

    def load_data_from_cache(self, hashed_info: str):
        """Method responsible for loading cached data.

        Args:
            hashed_info: hashed string of needed info about the data.

        """
        start = timeit.default_timer()
        file_path = os.path.join(self.cache_folder, hashed_info + '.pkl')
        data = pd.read_pickle(file_path)
        elapsed_time = round(timeit.default_timer() - start, 5)
        self.logger.info(f'{self.data_type} of {type(data)} type is loaded from cache in {elapsed_time} sec')
        return data

    def cache_data(self, hashed_info: str, data: pd.DataFrame):
        """Method responsible for saving cached data. It utilizes pickle format for saving data.

        Args:
            hashed_info: hashed string.
            data: pd.DataFrame.

        """
        cache_file = os.path.join(self.cache_folder, hashed_info + '.pkl')

        try:
            data.to_pickle(cache_file)
            self.logger.info(f'{self.data_type} cached with {hashed_info} hash')

        except Exception as ex:
            self.logger.error(f'Data was not cached due to error { ex }')
