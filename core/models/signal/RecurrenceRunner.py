from multiprocessing import Pool

from tqdm import tqdm

from core.architecture.abstraction.Decorators import time_it
from core.metrics.metrics_implementation import *
from core.models.ExperimentRunner import ExperimentRunner
from core.operation.transformation.DataTransformer import TSTransformer
from core.operation.transformation.extraction.sequences import ReccurenceExtractor


class RecurrenceRunner(ExperimentRunner):
    """Class responsible for wavelet feature generator experiment.

    Args:
        window_mode: boolean flag - if True, window mode is used. Defaults to False.
        use_cache: boolean flag - if True, cache is used. Defaults to False.

    Attributes:
        transformer: TSTransformer object.
        self.extractor: RecurrenceExtractor object.
        train_feats: train features.
        test_feats: test features.
    """

    def __init__(self, image_mode: bool = False, window_mode: bool = False, use_cache: bool = False):

        super().__init__()
        self.image_mode = image_mode
        self.window_mode = window_mode
        self.use_cache = use_cache
        self.transformer = TSTransformer
        self.extractor = ReccurenceExtractor
        self.train_feats = None
        self.test_feats = None

    def _ts_chunk_function(self, ts):

        ts = self.check_for_nan(ts)
        specter = self.transformer(time_series=ts)
        feature_df = specter.ts_to_recurrence_matrix()
        if not self.image_mode:
            feature_df = pd.Series(self.extractor(recurrence_matrix=feature_df).recurrence_quantification_analysis())
        return feature_df

    def generate_vector_from_ts(self, ts_frame: pd.DataFrame) -> pd.DataFrame:
        """Generate vector from time series.

        Args:
            ts_frame: time series frame

        Returns:
            Feature vector
        """
        ts_samples_count = ts_frame.shape[0]
        n_processes = self.n_processes

        with Pool(n_processes) as p:
            components_and_vectors = list(tqdm(p.imap(self._ts_chunk_function,
                                                      ts_frame.values),
                                               total=ts_samples_count,
                                               desc='Feature Generation. TS processed',
                                               unit=' ts',
                                               colour='black'
                                               )
                                          )
        if self.image_mode:
            components_and_vectors = np.asarray(components_and_vectors)
            components_and_vectors = components_and_vectors[:, np.newaxis, :, :]
        else:
            components_and_vectors = pd.concat(components_and_vectors, axis=1).T
        return components_and_vectors

    @time_it
    def get_features(self,
                     ts_data: pd.DataFrame,
                     dataset_name: str = None,
                     target: np.ndarray = None) -> pd.DataFrame:
        self.logger.info('Recurrence feature extraction started')

        if self.train_feats is None:
            train_feats = self.generate_vector_from_ts(ts_data)
            self.train_feats = train_feats
            return self.train_feats
        else:
            test_feats = self.generate_vector_from_ts(ts_data)
            if self.image_mode:
                self.test_feats = test_feats
            else:
                self.test_feats = test_feats[self.train_feats.columns]
            return self.test_feats
