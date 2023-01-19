import gc
import sys

from gtda.time_series import takens_embedding_optimal_parameters
from scipy import stats
from tqdm import tqdm

from core.architecture.abstraction.Decorators import time_it
from core.models.ExperimentRunner import ExperimentRunner
from core.operation.transformation.extraction.topological import *

sys.setrecursionlimit(1000000000)

PERSISTENCE_DIAGRAM_FEATURES = {'HolesNumberFeature': HolesNumberFeature(),
                                'MaxHoleLifeTimeFeature': MaxHoleLifeTimeFeature(),
                                'RelevantHolesNumber': RelevantHolesNumber(),
                                'AverageHoleLifetimeFeature': AverageHoleLifetimeFeature(),
                                'SumHoleLifetimeFeature': SumHoleLifetimeFeature(),
                                'PersistenceEntropyFeature': PersistenceEntropyFeature(),
                                'SimultaneousAliveHolesFeature': SimultaneousAliveHolesFeature(),
                                'AveragePersistenceLandscapeFeature': AveragePersistenceLandscapeFeature(),
                                'BettiNumbersSumFeature': BettiNumbersSumFeature(),
                                'RadiusAtMaxBNFeature': RadiusAtMaxBNFeature()}


class TopologicalRunner(ExperimentRunner):
    """Class for extracting topological features from time series data.

    Args:
        use_cache: flag for using cache

    Attributes:
        filtered_features: list of filtered features
        feature_extractor: feature extractor object

    """

    def __init__(self, use_cache: bool = False):
        super().__init__()
        self.use_cache = use_cache
        self.filtered_features = None
        self.feature_extractor = None

    def generate_topological_features(self, ts_data: pd.DataFrame) -> pd.DataFrame:

        if self.feature_extractor is None:
            te_dimension, te_time_delay = self.get_embedding_params_from_batch(ts_data=ts_data)

            persistence_diagram_extractor = PersistenceDiagramsExtractor(takens_embedding_dim=te_dimension,
                                                                         takens_embedding_delay=te_time_delay,
                                                                         homology_dimensions=(0, 1),
                                                                         parallel=True)

            self.feature_extractor = TopologicalFeaturesExtractor(
                persistence_diagram_extractor=persistence_diagram_extractor,
                persistence_diagram_features=PERSISTENCE_DIAGRAM_FEATURES)

        ts_data_transformed = self.feature_extractor.fit_transform(ts_data.values)

        if self.filtered_features is None:
            ts_data_transformed = self.delete_col_by_var(ts_data_transformed)
            self.filtered_features = ts_data_transformed.columns.tolist()
        gc.collect()
        return ts_data_transformed[self.filtered_features]

    @time_it
    def get_features(self, ts_data: pd.DataFrame, dataset_name: str = None):
        return self.generate_topological_features(ts_data=ts_data)

    def get_embedding_params_from_batch(self, ts_data: pd.DataFrame, method: str = 'mean') -> tuple:
        """Method for getting optimal Takens embedding parameters.

        Args:
            ts_data: dataframe with time series data
            method: method for getting optimal parameters

        Returns:
            Optimal Takens embedding parameters

        """
        methods = {'mode': self._mode,
                   'mean': np.mean,
                   'median': np.median}

        self.logger.info('Start searching optimal TE parameters')
        dim_list, delay_list = list(), list()

        for _ in tqdm(range(len(ts_data)),
                      initial=0,
                      desc='Time series processed: ',
                      unit='ts', colour='black'):
            single_time_series = ts_data.sample(1, replace=False, axis=0).squeeze()
            delay, dim = takens_embedding_optimal_parameters(X=single_time_series.values,
                                                             max_time_delay=5,
                                                             max_dimension=5,
                                                             n_jobs=-1)
            delay_list.append(delay)
            dim_list.append(dim)

        dimension = int(methods[method](dim_list))
        delay = int(methods[method](delay_list))
        self.logger.info(f'Optimal TE parameters: dimension = {dimension}, time_delay = {delay}')

        return dimension, delay

    @staticmethod
    def _mode(arr: list) -> int:
        return int(stats.mode(arr)[0][0])
