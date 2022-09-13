import math

import numpy as np
from sklearn.metrics import f1_score

from cases.anomaly_detection.clear_architecture.utils.get_time import time_now as time_now
from cases.anomaly_detection.clear_architecture.utils.settings_args import SettingsArgs


class AbstractDetector:
    args: SettingsArgs
    data: list = []
    output_list: list = []
    windowed_data: list = []
    filtering: bool = False

    def __init__(self, operation='detection', name: str = 'Unknown Detector'):
        self.name = name
        self.operation = operation

        self.win_len = None
        self.labels = None
        self.len = None
        self.step = None
        self.input_dict = None

    def set_settings(self, args: SettingsArgs):
        self.args = args
        self._print_logs(f"{time_now()} {self.name}: settings was set.")
        self._print_logs(f"{time_now()} {self.name}: Visualize = {self.args.visualize}")
        self._print_logs(f"{time_now()} {self.name}: Print logs = {self.args.print_logs}")

    def input_data(self, dictionary: dict) -> None:
        self._print_logs(f"{time_now()} {self.name}: Data read!")
        self.input_dict = dictionary
        self.windowed_data = self.input_dict["data_body"]["windows_list"]
        self.step = self.input_dict["data_body"]["window_step"]
        self.len = self.input_dict["data_body"]["window_len"]
        self.data = self.input_dict["data_body"]["elected_data"]
        self.labels = self.input_dict["data_body"]["raw_labels"]
        self.win_len = self.input_dict["data_body"]["window_len"]

    def run(self) -> None:
        self._print_logs(f"{time_now()} {self.name}: Start {self.operation}...")
        self._do_analysis()
        self._print_logs(f"{time_now()} {self.name}: {self.operation} finished!")

    def output_data(self) -> dict:
        if "detection" in self.input_dict["data_body"]:
            previous_predict = self.input_dict["data_body"]["detection"]

            for i in range(len(self.output_list)):
                self.output_list[i] = [self.output_list[i]]

            for i in range(len(self.output_list)):
                for j in range(len(previous_predict[i])):
                    self.output_list[i].append(previous_predict[i][j])
        else:
            for i in range(len(self.output_list)):
                self.output_list[i] = [self.output_list[i]]

        self.input_dict["data_body"]["detection"] = self.output_list
        if self.filtering:
            self._do_score()

        return self.input_dict

    def _do_score(self):
        score = []
        for i in range(len(self.output_list)):
            score.append(f1_score(self.labels[i], self.output_list[i], average='macro'))
        print("-------------------------------------")
        main_score = sum(score) / len(score)
        print("Average predict:")
        print(main_score)
        print("-------------------------------------")

    def _print_logs(self, log_message: str) -> None:
        if self.args.print_logs:
            print(log_message)

    def _get_angle_between_vectors(self, vector1, vector2):
        sum_of_coordinates = 0
        for i in range(len(vector1)):
            sum_of_coordinates += vector1[i] * vector2[i]
        if self._get_vector_len(vector1) * self._get_vector_len(vector2) == 0:
            return 0
        return math.sin(
            sum_of_coordinates /
            (self._get_vector_len(vector1) * self._get_vector_len(vector2)))

    def _do_analysis(self) -> None:
        """Abstract method for analysis"""
        raise NotImplementedError()

    @staticmethod
    def _make_vector(point_1: list, point_2: list):
        if len(point_1) != len(point_2):
            raise ValueError("Vectors has to be the same len!")
        vector = []
        for i in range(len(point_1)):
            vector.append(point_2[i] - point_1[i])
        return vector

    @staticmethod
    def _get_vector_len(vector):
        sum_of_coordinates = 0
        for coordinate in vector:
            sum_of_coordinates += coordinate ** 2
        return math.sqrt(sum_of_coordinates)

    @staticmethod
    def normalize_data(data):
        return (data - np.min(data)) / (np.max(data) - np.min(data))
