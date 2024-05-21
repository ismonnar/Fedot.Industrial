import os
from pathlib import Path
from typing import Union

import pandas as pd
from sklearn.metrics import f1_score, roc_auc_score

from fedot_ind.api.main import Framework
from fedot_ind.api.utils.path_lib import PROJECT_PATH
from fedot_ind.core.architecture.settings.computational import backend_methods as np
from fedot_ind.core.metrics.metrics_implementation import calculate_forecasting_metric
from fedot_ind.tools.loader import DataLoader

ts_datasets = {
    'm4_yearly': Path(PROJECT_PATH, 'examples', 'data', 'ts', 'M4Yearly.csv'),
    'm4_weekly': Path(PROJECT_PATH, 'examples', 'data', 'ts', 'M4Weekly.csv'),
    'm4_daily': Path(PROJECT_PATH, 'examples', 'data', 'ts', 'M4Daily.csv'),
    'm4_monthly': Path(PROJECT_PATH, 'examples', 'data', 'ts', 'M4Monthly.csv'),
    'm4_quarterly': Path(PROJECT_PATH, 'examples', 'data', 'ts', 'M4Quarterly.csv')}


def evaluate_metric(target, prediction):
    try:
        if len(np.unique(target)) > 2:
            metric = f1_score(target, prediction, average='weighted')
        else:
            metric = roc_auc_score(target, prediction, average='weighted')
    except Exception:
        metric = f1_score(target, np.argmax(
            prediction, axis=1), average='weighted')
    return metric


def compare_forecast_with_sota(dataset_name, horizon):
    autogluon = PROJECT_PATH + f'/benchmark/results/benchmark_results/autogluon/' \
                               f'{dataset_name}_{horizon}_forecast_vs_actual.csv'
    n_beats = PROJECT_PATH + f'/benchmark/results/benchmark_results/nbeats/' \
                             f'{dataset_name}_{horizon}_forecast_vs_actual.csv'
    n_beats = pd.read_csv(n_beats)
    autogluon = pd.read_csv(autogluon)

    n_beats_forecast = calculate_forecasting_metric(
        target=n_beats['value'].values,
        labels=n_beats['predict'].values)
    autogluon_forecast = calculate_forecasting_metric(
        target=autogluon['value'].values,
        labels=autogluon['predict'].values)
    return n_beats['predict'].values, n_beats_forecast, autogluon['predict'].values, autogluon_forecast


def industrial_forecasting_modelling_loop(dataset_name: str = None,
                                          benchmark: str = None,
                                          horizon: int = 1,
                                          finetune: bool = False,
                                          api_config: dict = None):
    industrial = Framework(**api_config)
    train_data, _ = DataLoader(
        dataset_name=dataset_name).load_forecast_data(folder=benchmark)
    target = train_data.values[-horizon:].flatten()
    train_data = (train_data, target)
    if finetune:
        industrial.finetune(train_data)
    else:
        industrial.fit(train_data)

    labels = industrial.predict(train_data)
    if isinstance(labels, dict):
        val = 1000000000
        for forecat_model, predict in labels.items():
            industrial.predicted_labels = predict
            best_model = forecat_model
            current_metric = industrial.get_metrics(
                target=target, metric_names=(
                    'smape', 'rmse', 'median_absolute_error'))
            current_rmse = current_metric['rmse'].values[0]

            if current_rmse < val:
                val = current_rmse
                labels = predict
                metrics = current_metric
                best_model = forecat_model

        industrial.solver = industrial.solver[best_model]
    else:
        metrics = industrial.get_metrics(
            target=target, metric_names=(
                'smape', 'rmse', 'median_absolute_error'))
    return industrial, labels, metrics, target


def industrial_common_modelling_loop(
        dataset_name: Union[str, dict] = None,
        finetune: bool = False,
        api_config: dict = None,
        metric_names: tuple = (
            'r2',
            'rmse',
            'mae')):
    industrial = Framework(**api_config)
    if api_config['problem'] == 'ts_forecasting':
        train_data, _ = DataLoader(
            dataset_name=dataset_name['dataset']).load_forecast_data(
            dataset_name['benchmark'])
        target = train_data.values[-api_config['task_params']
                                   ['forecast_length']:].flatten()
        train_data = (train_data, target)
        test_data = train_data
    else:
        train_data, test_data = DataLoader(
            dataset_name=dataset_name).load_data()
    if finetune:
        industrial.finetune(train_data, tuning_params={
            'tuning_timeout': api_config['timeout']})
    else:
        industrial.fit(train_data)

    labels = industrial.predict(test_data)
    if api_config['problem'] != 'ts_forecasting':
        industrial.predict_proba(test_data)

    metrics = industrial.get_metrics(target=test_data[1],
                                     rounding_order=3,
                                     metric_names=metric_names)
    return industrial, labels, metrics


def read_results(forecast_result_path):
    results = os.listdir(forecast_result_path)
    df_forecast = []
    df_metrics = []
    for file in results:
        df = pd.read_csv(f'{forecast_result_path}/{file}')
        name = file.split('_')[0]
        df['dataset_name'] = name
        if file.__contains__('forecast'):
            df_forecast.append(df)
        else:
            df_metrics.append(df)
    return df_forecast, df_metrics


def create_comprasion_df(df, metric: str = 'rmse'):
    df_full = pd.concat(df)
    df_full = df_full[df_full['Unnamed: 0'] == metric]
    df_full = df_full.drop('Unnamed: 0', axis=1)
    df_full['Difference_industrial_All'] = (
        df_full.iloc[:, 1:3].min(axis=1) - df_full['industrial'])
    df_full['Difference_industrial_AG'] = (
        df_full.iloc[:, 1:2].min(axis=1) - df_full['industrial'])
    df_full['Difference_industrial_NBEATS'] = (
        df_full.iloc[:, 2:3].min(axis=1) - df_full['industrial'])
    df_full['industrial_Wins_All'] = df_full.apply(
        lambda row: 'Win' if row.loc['Difference_industrial_All'] > 0 else 'Loose', axis=1)
    df_full['industrial_Wins_AG'] = df_full.apply(
        lambda row: 'Win' if row.loc['Difference_industrial_AG'] > 0 else 'Loose', axis=1)
    df_full['industrial_Wins_NBEATS'] = df_full.apply(
        lambda row: 'Win' if row.loc['Difference_industrial_NBEATS'] > 0 else 'Loose',
        axis=1)
    return df_full
