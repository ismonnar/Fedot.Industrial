from fedot_ind.api.main import Framework
from fedot_ind.tools.loader import DataLoader

dataset_name = 'Lightning7'
metric_names = ('f1', 'accuracy', 'precision', 'roc_auc')
api_config = dict(problem='classification',
                  metric='f1',
                  timeout=5,
                  n_jobs=2,
                  with_tuning=False,
                  industrial_strategy='kernel_automl',
                  industrial_strategy_params={},
                  logging_level=20)
train_data, test_data = DataLoader(dataset_name).load_data()
industrial = Framework(**api_config)
industrial.fit(train_data)
predict = industrial.predict(test_data, 'ensemble')
predict_proba = industrial.predict_proba(test_data, 'ensemble')
metric = industrial.get_metrics(target=test_data[1],
                                metric_names=metric_names)
_ = 1
