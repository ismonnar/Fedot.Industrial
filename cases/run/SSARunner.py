from collections import Counter
import pandas as pd
from sklearn.metrics import f1_score
from fedot.api.main import Fedot
from core.models.spectral.SSA import Spectrum
from core.models.statistical.Stat_features import AggregationFeatures
from cases.run.ExperimentRunner import ExperimentRunner
from core.operation.utils.utils import *
import matplotlib.pyplot as plt
import timeit


class SSARunner(ExperimentRunner):
    def __init__(self,
                 feature_generanor_dict: dict = None,
                 list_of_dataset: list = None,
                 launches: int = 3,
                 metrics_name: list = ['f1', 'roc_auc', 'accuracy', 'logloss', 'precision'],
                 fedot_params: dict = None,
                 window_mode: bool = True
                 ):

        super().__init__(feature_generanor_dict,list_of_dataset, launches, metrics_name, fedot_params)
        self.aggregator = AggregationFeatures()
        self.spectrum_extractor = Spectrum
        self.window_length_list = feature_generanor_dict
        self.vis_flag = False
        self.rank_hyper = None
        self.train_feats = None
        self.test_feats = None
        self.n_components = None
        self.window_mode = window_mode

    def __vis_and_save_components(self, Components_df):

        n_rows = round(Components_df[0].shape[1] / 5)

        if n_rows < 4:
            plot_area = 'small'
        elif 5 < n_rows < 9:
            plot_area = 'mid'
        else:
            plot_area = 'big'

        plot_dict = {'small': (20, 10),
                     'mid': (20, 10),
                     'big': (40, 20)}

        figsize = plot_dict[plot_area]
        layout = (n_rows + 1, 5)

        for idx, df in enumerate(Components_df):
            df.plot(subplots=True,
                    figsize=figsize,
                    legend=None,
                    layout=(n_rows + 1, 5))

            plt.tight_layout()
            plt.savefig(os.path.join(self.path_to_save_png, f'components_for_ts_class_{idx}.png'))

    def _ts_chunk_function(self, ts):

        self.logger.info(f'8 CPU on working. '
                         f'Total ts samples - {self.ts_samples_count}. '
                         f'Current sample - {self.count}')

        ts = self.check_Nan(ts)

        spectr = self.spectrum_extractor(time_series=ts,
                                         window_length=self.window_length)
        TS_comps, X_elem, V, Components_df, _, n_components, explained_dispersion = spectr.decompose(
            rank_hyper=self.rank_hyper)

        self.count += 1
        return [Components_df, n_components, explained_dispersion]

    def generate_vector_from_ts(self, ts_frame):
        start = timeit.default_timer()
        self.ts_samples_count = ts_frame.shape[0]
        components_and_vectors = threading_operation(ts_frame=ts_frame.values,
                                                     function_for_feature_exctraction=self._ts_chunk_function)
        self.logger.info(f'Time spent on eigenvectors extraction - {timeit.default_timer() - start}')
        return components_and_vectors

    def generate_features_from_ts(self, eigenvectors_list, window_mode: bool = False):
        start = timeit.default_timer()

        if window_mode:
            lambda_function_for_stat_features = lambda x: apply_window_for_statistical_feature(x.T,
                                                                                               feature_generator=self.aggregator.create_baseline_features)
            lambda_function_for_concat = lambda x: pd.concat(x, axis=1)

            list_with_stat_features_on_interval = list(map(lambda_function_for_stat_features, eigenvectors_list))
            aggregation_df = list(map(lambda_function_for_concat, list_with_stat_features_on_interval))
        else:
            aggregation_df = list(map(lambda x: self.aggregator.create_baseline_features(x.T), eigenvectors_list))

        components_names = aggregation_df[0].index.values
        columns_names = aggregation_df[0].columns.values

        aggregation_df = pd.concat([pd.DataFrame(x.values.ravel()) for x in aggregation_df], axis=1)
        aggregation_df = aggregation_df.T

        new_column_names = []
        for number_of_component in components_names:
            new_column_names.extend([f'{x}_for_component: {number_of_component}' for x in columns_names])

        aggregation_df.columns = new_column_names

        self.logger.info(f'Time spent on feature generation - {timeit.default_timer() - start}')
        return aggregation_df

    def _choose_best_window_size(self, X_train, y_train, window_length_list):

        metric_list = []
        n_comp_list = []
        disp_list = []
        eigen_list = []

        if type(window_length_list) == int:
            window_length_list = [window_length_list]

        for window_length in window_length_list:
            self.logger.info(f'Generate features for window length - {window_length}')
            self.window_length = window_length

            eigenvectors_and_rank = self.generate_vector_from_ts(X_train)

            rank_list = [x[1] for x in eigenvectors_and_rank]
            explained_dispersion = [x[2] for x in eigenvectors_and_rank]

            self.explained_dispersion = round(np.mean(explained_dispersion))

            self.n_components = Counter(rank_list).most_common(n=1)[0][0]

            eigenvectors_list = [x[0].iloc[:, :self.n_components] for x in eigenvectors_and_rank]

            self.logger.info(f'Every eigenvector with impact less then 1 % percent was eliminated. '
                             f'{self.explained_dispersion} % of explained dispersion '
                             f'obtained by first - {self.n_components} components.')

            metrics = self.explained_dispersion #/ self.n_components
            metric_list.append(metrics)

            # self.logger.info(f'Validate model for window length  - {window_length}')
            # metrics = self._validate_window_length(features=train_feats, target=y_train)
            # self.logger.info(f'Obtained metric for window length {window_length}  - F1, ROC_AUC - {metrics}')
            # feature_list.append(train_feats)
            # disp_list.append(self.explained_dispersion)

            eigen_list.append(eigenvectors_list)
            n_comp_list.append(self.n_components)
            self.count = 0

        # max_score = [max(metric_list) for x in metric_list]
        # index_of_window = int(metric_list.index(max(metric_list)))

        index_of_window = int(metric_list.index(max(metric_list)))

        self.logger.info(f'Was choosen window length -  {window_length_list[index_of_window]}')

        eigenvectors_list = eigen_list[index_of_window]
        self.min_rank = np.min([x.shape[1] for x in eigenvectors_list])
        eigenvectors_list = [x.iloc[:, :self.min_rank] for x in eigenvectors_list]
        train_feats = self.generate_features_from_ts(eigenvectors_list, window_mode=self.window_mode)

        for col in train_feats.columns:
            train_feats[col].fillna(value=train_feats[col].mean(), inplace=True)

        self.vis_flag = False
        eigenvectors_list_filtred = []

        for class_n in np.unique(y_train):
            clas_idx = np.where(y_train == class_n)[0][:2]
            for idx in clas_idx:
                eigenvectors_list_filtred.append(eigenvectors_list[idx])

        if self.vis_flag:
            try:
                self.__vis_and_save_components(Components_df=eigenvectors_list_filtred)
            except Exception:
                self.logger.info('Vis problem')

        self.window_length = window_length_list[index_of_window]
        self.n_components = n_comp_list[index_of_window]

        return train_feats

    def fit(self, X_train: pd.DataFrame, y_train: np.ndarray, window_length_list: object = None):

        self.logger.info('Generating features for fit model')

        if self.train_feats is None:
            self.train_feats = self._choose_best_window_size(X_train, y_train, window_length_list)
            self.train_feats = delete_col_by_var(self.train_feats)

        self.logger.info('Start fitting FEDOT model')
        predictor = Fedot(**self.fedot_params)

        if self.fedot_params['composer_params']['metric'] == 'f1':
            predictor.params.api_params['tuner_metric'] = f1_score

        predictor.fit(features=self.train_feats, target=y_train)

        return predictor

    def predict(self, predictor, X_test: pd.DataFrame, window_length: int = None, y_test=None):

        self.logger.info('Generating features for prediction')

        if self.test_feats is None:
            eigenvectors_and_rank = self.generate_vector_from_ts(X_test)
            eigenvectors_list = [x[0].iloc[:, :self.min_rank] for x in eigenvectors_and_rank]
            self.test_feats = self.generate_features_from_ts(eigenvectors_list, window_mode=self.window_mode)

            for col in self.test_feats.columns:
                self.test_feats[col].fillna(value=self.test_feats[col].mean(), inplace=True)
            self.test_feats = self.test_feats[self.train_feats.columns]

        start_time = timeit.default_timer()
        predictions = predictor.predict(features=self.test_feats)
        inference = timeit.default_timer() - start_time
        predictions_proba = predictor.predict_proba(features=self.test_feats)

        return predictions, predictions_proba, inference
