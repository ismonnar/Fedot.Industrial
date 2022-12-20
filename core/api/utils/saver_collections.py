import os

import pandas as pd

from core.architecture.abstraction.LoggerSingleton import Logger


class ResultSaver:
    def __init__(self):

        self.logger = Logger().get_logger()
        self.save_method_dict = {'ECM': self.save_boosting_results,
                                 'Ensemble': self.save_ensemble_results,
                                 'Original': self.save_results}

    def save_results(self,
                     prediction: dict
                     ):
        for launch in prediction:
            result_at_launch = prediction[launch]
            feature_target_dict = {'train_features.csv': result_at_launch['train_features'],
                                   'train_target.csv': result_at_launch['train_target'],
                                   'test_features.csv': result_at_launch['test_features'],
                                   'test_target.csv': result_at_launch['test_target']}
            path_results = os.path.join(result_at_launch['path_to_save'], 'test_results')
            os.makedirs(path_results, exist_ok=True)

            try:
                result_at_launch['fitted_predictor'].current_pipeline.save(path_results)
            except Exception as ex:
                self.logger.error(f'Can not save pipeline: {ex}')

            for name, features in feature_target_dict.items():
                pd.DataFrame(features).to_csv(os.path.join(result_at_launch['path_to_save'], name))

            if not isinstance(result_at_launch['class_probability'], pd.DataFrame):
                df_preds = pd.DataFrame(result_at_launch['class_probability'].round(3), dtype=float)
                df_preds.columns = [f'Class_{x+1}' for x in df_preds.columns]
                df_preds['Target'] = result_at_launch['test_target']
                df_preds['Predicted_labels'] = result_at_launch['label']
            else:
                df_preds = result_at_launch['class_probability']
                df_preds['Target'] = result_at_launch['test_target'].values

            if isinstance(result_at_launch['metrics'], str):
                df_metrics = pd.DataFrame()
            else:
                df_metrics = pd.DataFrame.from_records(data=[x for x in result_at_launch['metrics'].items()],
                                                       columns=['Metric_name', 'Metric_value']).reset_index()
                del df_metrics['index']
                df_metrics = df_metrics.T
                df_metrics = pd.DataFrame(df_metrics.values[1:], columns=df_metrics.iloc[0])

            for p, d in zip(['probs_preds_target.csv', 'metrics.csv'],
                            [df_preds, df_metrics]):
                full_path = os.path.join(path_results, p)
                d.to_csv(full_path)

    def save_boosting_results(self, prediction):
        for launch in prediction:
            path_to_save = prediction[launch]['path_to_save']
            location = os.path.join(path_to_save, 'boosting')
            if not os.path.exists(location):
                os.makedirs(location)
            prediction[launch]['solution_table'].to_csv(os.path.join(location, 'solution_table.csv'))
            prediction[launch]['metrics_table'].to_csv(os.path.join(location, 'metrics_table.csv'))

            models_path = os.path.join(location, 'boosting_pipelines')
            if not os.path.exists(models_path):
                os.makedirs(models_path)
            for index, model in enumerate(prediction['model_list']):
                try:
                    model.current_pipeline.save(path=os.path.join(models_path, f'boost_{index}'),
                                                datetime_in_path=False)
                except Exception:
                    model.save(path=os.path.join(models_path, f'boost_{index}'),
                               datetime_in_path=False)
            if prediction['ensemble_model'] is not None:
                try:
                    prediction[launch]['ensemble_model'].current_pipeline.save(
                        path=os.path.join(models_path, 'boost_ensemble'),
                        datetime_in_path=False)
                except Exception:
                    prediction[launch]['ensemble_model'].save(path=os.path.join(models_path, 'boost_ensemble'),
                                                              datetime_in_path=False)
            else:
                self.logger.info('Ensemble model cannot be saved due to applied SUM method ')

    def save_ensemble_results(self, prediction: dict):
        for launch in prediction:
            metric_at_launch = prediction[launch]
            metric_df = pd.concat([pd.Series(metric_at_launch[key]).to_frame() for key in metric_at_launch], axis=1)
            metric_df.columns = metric_at_launch.keys()
            path_to_save_launch = os.path.join(prediction['path_to_save'], str(launch))
            if not os.path.exists(path_to_save_launch):
                os.makedirs(path_to_save_launch)
            metric_df.to_csv(os.path.join(path_to_save_launch, 'ensemble_metrics.csv'))