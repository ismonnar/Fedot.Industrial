from multiprocessing.dummy import Pool

import pandas as pd
from sklearn.metrics import f1_score
from fedot.api.main import Fedot

from core.models.signal.wavelet import WaveletExtractor
from core.models.statistical.Stat_features import AggregationFeatures
from cases.run.ExperimentRunner import ExperimentRunner
from core.operation.utils.utils import *
import timeit


class SignalRunner(ExperimentRunner):
    def __init__(self,
                 feature_generanor_dict: dict,
                 list_of_dataset: list = None,
                 launches: int = 3,
                 metrics_name: list = ['f1', 'roc_auc', 'accuracy', 'logloss', 'precision'],
                 fedot_params: dict = None
                 ):

        super().__init__(feature_generanor_dict, list_of_dataset, launches, metrics_name, fedot_params)
        self.aggregator = AggregationFeatures()
        self.wavelet_extractor = WaveletExtractor
        self.wavelet_list = feature_generanor_dict
        self.vis_flag = False
        self.train_feats = None
        self.test_feats = None

        self.n_components = None

    def _ts_chunk_function(self, ts):

        self.logger.info(f'8 CPU on working. '
                         f'Total ts samples - {self.ts_samples_count}. '
                         f'Current sample - {self.count}')

        ts = self.check_Nan(ts)

        threshold_range = [1, 3, 5, 7, 9]

        spectr = self.wavelet_extractor(time_series=ts, wavelet_name=self.wavelet)
        high_freq, low_freq = spectr.decompose_signal()

        hf_lambda_peaks = lambda x: len(spectr.detect_peaks(high_freq, mph=x + 1))
        hf_lambda_names = lambda x: 'HF_peaks_higher_than_{}'.format(x + 1)
        hf_lambda_KNN = lambda x: len(spectr.detect_peaks(high_freq, mpd=x))
        hf_lambda_KNN_names = lambda x: 'HF_nearest_peaks_at_distance_{}'.format(x)

        LF_lambda_peaks = lambda x: len(spectr.detect_peaks(high_freq, mph=x + 1, valley=True))
        LF_lambda_names = lambda x: 'LF_peaks_higher_than_{}'.format(x + 1)
        LF_lambda_KNN = lambda x: len(spectr.detect_peaks(high_freq, mpd=x))
        LF_lambda_KNN_names = lambda x: 'LF_nearest_peaks_at_distance_{}'.format(x)

        lambda_list = [
            hf_lambda_KNN,
            LF_lambda_peaks,
            LF_lambda_KNN]

        lambda_list_names = [
            hf_lambda_KNN_names,
            LF_lambda_names,
            LF_lambda_KNN_names]

        features = list(map(hf_lambda_peaks, threshold_range))
        features_names = list(map(hf_lambda_names, threshold_range))
        for lambda_method, lambda_name in zip(lambda_list, lambda_list_names):
            features.extend(list(map(lambda_method, threshold_range)))
            features_names.extend(list(map(lambda_name, threshold_range)))

        self.count += 1
        feature_df = pd.DataFrame(data=features)
        feature_df = feature_df.T
        feature_df.columns = features_names
        return feature_df

    def generate_vector_from_ts(self, ts_frame):
        start = timeit.default_timer()
        self.ts_samples_count = ts_frame.shape[0]
        components_and_vectors = list(map(self._ts_chunk_function, ts_frame.values))
        self.logger.info(f'Time spent on wavelet extraction - {timeit.default_timer() - start}')
        return components_and_vectors

    def generate_features_from_ts(self, ts_frame, window_length=None):
        pass

    def extract_features(self, ts_data):

        if self.train_feats is None:
            self.train_feats = self._choose_best_wavelet(ts_data)
        else:
            if self.test_feats is None:
                self.test_feats = self.generate_vector_from_ts(ts_data)
                self.test_feats = pd.concat(self.test_feats)
                self.test_feats = delete_col_by_var(self.test_feats)

        return

    def _choose_best_wavelet(self, X_train, y_train):

        metric_list = []
        feature_list = []

        for wavelet in self.wavelet_list:
            self.logger.info(f'Generate features for window length - {wavelet}')
            self.wavelet = wavelet

            train_feats = self.generate_vector_from_ts(X_train)
            train_feats = pd.concat(train_feats)

            self.logger.info(f'Validate model for wavelet  - {wavelet}')

            score_f1, score_roc_auc = self._validate_window_length(features=train_feats, target=y_train)

            self.logger.info(f'Obtained metric for wavelet {wavelet}  - F1, ROC_AUC - {score_f1, score_roc_auc}')

            metric_list.append((score_f1, score_roc_auc))
            feature_list.append(train_feats)
            self.count = 0

        max_score = [sum(x) for x in metric_list]
        index_of_window = int(max_score.index(max(max_score)))
        train_feats = feature_list[index_of_window]

        self.wavelet = self.wavelet_list[index_of_window]
        self.logger.info(f'Was choosen wavelet -  {self.wavelet} ')

        train_feats = delete_col_by_var(train_feats)

        return train_feats
