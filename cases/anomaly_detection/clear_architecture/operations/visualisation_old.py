from typing import Union

import numpy as np
from matplotlib import pyplot as plt

from cases.anomaly_detection.clear_architecture.operations.AbstractDataOperation import AbstractDataOperation
from cases.anomaly_detection.clear_architecture.utils.get_time import time_now


class DataVisualizer(AbstractDataOperation):
    """
    Visualizes data obtained from anomaly detection experiment
    """

    def __init__(self):
        super().__init__(name="Visualizer", operation="visualization")
        self.window = None
        self.predicts = None
        self.labels = None
        self.data = None
        self.input_dict = None
        self.transformed_data = list()

    def input_data(self, dictionary: dict) -> None:
        self._print_logs(f"{time_now()} {self.name}: Data read!")
        self.input_dict = dictionary
        self.data = self.input_dict["data_body"]["elected_data"]
        self.labels = self.input_dict["data_body"]["labels_for_show"]
        self.predicts = self.input_dict["data_body"]["detection"]
        self.window = self.input_dict["data_body"]["window_len"]

    def output_data(self) -> dict:
        self.input_dict["data_body"]["transformed_data"] = self.transformed_data
        return self.input_dict

    def _do_analysis(self) -> None:
        """
        Visualize data
        :return: None
        """
        x_labels = []
        y_data = []

        f, ax = plt.subplots(len(self.data) * 2, 1, figsize=(20, 10))
        counter = 0
        for i in range(0, len(self.data)):
            y_data = []
            for j in range(len(self.data[i][0])):
                temp_list = []
                for t in range(len(self.data[i])):
                    temp_list.append(self.data[i][t][j])
                y_data.append(temp_list)
            true_labels = []
            index = []
            """
            for j in range(0, len(self.predicts[i])):
                index.append(pd.to_timedelta(j))
                value = 0
                real_value = j * (len(self.labels[i])//len(self.predicts[i]))
                for n in range(real_value, real_value+self.window):
                    if n < len(self.labels[i]):
                        if self.labels[i][n] == 1:
                            value = 1
                            break
                true_labels.append(value)
            """
            combined_predict = []
            united_predict = [0] * len(self.predicts[i][0])
            for j in range(len(self.predicts[i])):
                for t, pred in enumerate(self.predicts[i][j]):
                    if pred == 1:
                        united_predict[t] = 1
            unite_win_len = 1500
            # combined_predict = self._win_unite(united_predict, 100)
            # combined_predict = self._win_filter(combined_predict, 400)
            combined_predict = self._win_unite_by_density(united_predict, 400, 50)
            score_diff = np.diff(self.predicts[i][0])
            q_95 = np.quantile(self.predicts[i][0], 0.95)
            max_val = max(self.predicts[i][0]) + max(self.predicts[i][0]) / 10
            odd_new_predicts_1 = list(map(lambda x: max_val if x > q_95 else 0, score_diff))
            ax[counter].plot(y_data)
            ax[counter].plot(self.labels[i], "g")
            # ax[counter].set_title(f"raw data {self.new_labels }")
            counter += 1
            # ax[counter].plot(self.labels[i], "r")
            for predict in self.predicts[i]:
                ax[counter].plot(predict)
                score_diff = np.diff(predict)
                q_95 = np.quantile(predict, 0.98)
                predict_1 = list(map(lambda x: 1 if x > q_95 else 0, predict))
                ax[counter].plot(predict_1, "r")
            ax[counter].plot(self.predicts[i][0], "b")
            # ax[counter].plot(odd_new_predicts_1, "r")
            # ax[counter].set_title("labels")
            counter += 1
        plt.show()

        # ax[2].plot(true_labels, "r")
        # ax[2].set_title("labels")

    @staticmethod
    def _win_unite_by_density(predict, distance: int, thresh: int = 5) -> list:
        def _fill_gap(predict, segment):
            for i in range(segment[0], segment[1]):
                predict[i] = 0.7
            return predict

        def _check_intersection(segment_one: list, segment_two: list) -> Union[bool, list]:
            if segment_two[0] <= segment_one[0] <= segment_two[1] or \
                    segment_two[0] <= segment_one[1] <= segment_two[1] or \
                    segment_one[0] <= segment_two[0] <= segment_one[1] or \
                    segment_one[0] <= segment_two[1] <= segment_one[1]:
                start = min(segment_two[0], segment_one[0])
                end = max(segment_two[1], segment_one[1])
                return [start, end]
            return False

        line_segments = []
        number_of_predicts_in_line_segment = []
        i = distance // 2 - 1
        while i <= len(predict) - distance // 2:
            i += 1
            if predict[i] == 1:
                counter = 0
                start = len(predict)
                end = 0
                for j in range(i - distance // 2, i + distance // 2):
                    if predict[j] == 1 and i != j:
                        counter += 1
                        if j > end:
                            end = j
                        if j < start:
                            start = j
                if counter >= thresh:
                    line_segments.append([start, end])
                    i = end

        # clean intersected segments
        clear_segments = []
        flag = True
        while flag:
            flag = False
            for i in range(len(line_segments)):
                filtration_flag = True
                for j in range(len(line_segments)):
                    if i != j:
                        result = _check_intersection(line_segments[j], line_segments[i])
                        if result:
                            clear_segments.append(result)
                            flag = True
                            filtration_flag = False
                            line_segments[j] = [0, 0]
                if filtration_flag:
                    clear_segments.append(line_segments[i])
            line_segments = []
            for segment in clear_segments:
                if segment[0] != 0 and segment[1] != 0:
                    line_segments.append(segment)
            if flag:
                clear_segments = []
        out_predict = [0] * len(predict)
        for segment in line_segments:
            out_predict = _fill_gap(out_predict, segment)

        return out_predict

    @staticmethod
    def _win_unite(predict, distance: int) -> list:
        def _fill_gap(predict, start, end):
            for i in range(start, end):
                predict[i] = 1
            return predict

        last_point = 0
        i = 0
        while i < len(predict) - distance:
            i += 1
            if predict[i] == 1:
                for j in range(i + 1, i + distance):
                    if predict[j] == 1:
                        last_point = j
                        predict = _fill_gap(predict, i, last_point)
                        i = last_point - 1
        # for i in range(len(predict)-30, len(predict)):
        #    predict[i] = 0
        return predict

    @staticmethod
    def _win_filter(predict, distance: int):
        def _clear_gap(predict, start, end):
            for i in range(start, end):
                predict[i] = 0
            return predict

        predicted_zone_found: bool = False
        for i in range(len(predict)):
            if predict[i] == 1 and not predicted_zone_found:
                start = i
                end = i
                predicted_zone_found = True
            if predict[i] == 0 and predicted_zone_found:
                end = i
                if end - start < distance:
                    predict = _clear_gap(predict, start, end)
                predicted_zone_found = False
        return predict
