import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, f1_score,
                             log_loss, mean_absolute_error,
                             mean_absolute_percentage_error,
                             mean_squared_error, mean_squared_log_error,
                             precision_score, r2_score, roc_auc_score)


class QualityMetric:
    def __init__(self, target,
                 predicted_labels,
                 predicted_probs=None,
                 metric_list: list = ('f1', 'roc_auc', 'accuracy', 'logloss', 'precision'),
                 default_value: float = 0.0):
        self.predicted_probs = predicted_probs
        self.predicted_labels = predicted_labels.reshape(-1)
        self.target = target.reshape(-1)
        self.metric_list = metric_list
        self.default_value = default_value

    def metric(self) -> float:
        pass


class RMSE(QualityMetric):
    def metric(self) -> float:
        return mean_squared_error(y_true=self.target, y_pred=self.predicted_labels, squared=False)


class MSE(QualityMetric):
    def metric(self) -> float:
        return mean_squared_error(y_true=self.target, y_pred=self.predicted_labels, squared=True)


class MSLE(QualityMetric):
    def metric(self) -> float:
        return mean_squared_log_error(y_true=self.target, y_pred=self.predicted_labels)


class MAPE(QualityMetric):
    def metric(self) -> float:
        return mean_absolute_percentage_error(y_true=self.target, y_pred=self.predicted_labels)


class F1(QualityMetric):
    def metric(self) -> float:
        target = self.target
        prediction = self.predicted_labels

        self.default_value = 0
        n_classes = np.unique(target)
        n_classes_pred = np.unique(prediction)
        if n_classes.shape[0] > 2 or n_classes_pred.shape[0] > 2:
            additional_params = {'average': 'weighted'}
        else:
            additional_params = {'average': 'binary'}
        return f1_score(y_true=target, y_pred=prediction,
                        **additional_params)


class MAE(QualityMetric):
    def metric(self) -> float:
        return mean_absolute_error(y_true=self.target, y_pred=self.predicted_labels)


class R2(QualityMetric):
    def metric(self) -> float:
        return r2_score(y_true=self.target, y_pred=self.predicted_labels)


class ROCAUC(QualityMetric):
    def metric(self) -> float:
        n_classes = len(np.unique(self.target))

        self.default_value = 0.5
        if n_classes > 2:
            target = pd.get_dummies(self.target)
            additional_params = {'multi_class': 'ovr', 'average': 'macro'}
            prediction = self.predicted_probs
        else:
            target = self.target
            additional_params = {}
            prediction = self.predicted_labels

        score = roc_auc_score(y_score=prediction, y_true=target, **additional_params)
        score = round(score, 3)

        return score


class Precision(QualityMetric):
    def metric(self) -> float:
        target = self.target
        prediction = self.predicted_labels

        n_classes = np.unique(target)
        if n_classes.shape[0] >= 2:
            additional_params = {'average': 'macro'}
        else:
            additional_params = {}

        score = precision_score(y_pred=prediction, y_true=target, **additional_params)
        score = round(score, 3)
        return score


class Logloss(QualityMetric):
    def metric(self) -> float:
        target = self.target
        prediction = self.predicted_probs
        return log_loss(y_true=target, y_pred=prediction)


class Accuracy(QualityMetric):
    def metric(self) -> float:
        target = self.target
        prediction = self.predicted_labels
        return accuracy_score(y_true=target, y_pred=prediction)
