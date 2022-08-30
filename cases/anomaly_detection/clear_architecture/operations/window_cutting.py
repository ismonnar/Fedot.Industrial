from cases.anomaly_detection.clear_architecture.utils.get_time \
    import get_current_time
from cases.anomaly_detection.clear_architecture.utils.settings_args \
    import SettingsArgs

"""
input format:

    dict with "data" and "labels" fields

Output 
    the same dict but with additional windows_list and labels for it
"""


class WindowCut:
    args: SettingsArgs

    def __init__(self, window_len, window_step):
        self.window_len = window_len
        self.window_step = window_step
        self.output_window_list = []

    def set_settings(self, args: SettingsArgs):
        self.args = args
        self._print_logs(f"{get_current_time()} Window cutter: settings was set.")
        self._print_logs(f"{get_current_time()} Window cutter: Visualize = {self.args.visualize}")
        self._print_logs(f"{get_current_time()} Window cutter: Print logs = {self.args.print_logs}")

    def input_data(self, input_dict: dict) -> None:
        self._print_logs(f"{get_current_time()} Window cutter: Data read!")
        self.input_dict = input_dict
        self.data = self.input_dict["data_body"]["elected_data"]

    def run(self) -> None:
        self._print_logs(f"{get_current_time()} Window cutter: Start cutting...")
        self._cut_data_to_windows()
        self._print_logs(f"{get_current_time()} Window cutter: Cutting finished!")

    def output_data(self) -> dict:
        self.input_dict["data_body"]["windows_list"] = self.output_window_list
        self.input_dict["data_body"]["window_len"] = self.window_len
        self.input_dict["data_body"]["window_step"] = self.window_step
        return self.input_dict

    def _cut_data_to_windows(self) -> None:
        for data in self.data:
            windows = self._cut_ts_to_windows(data)
            self.output_window_list.append(windows)

    def _cut_ts_to_windows(self, ts: list) -> list:
        start_idx = 0
        end_idx = len(ts[0]) - self.window_len
        temp_windows_list = []
        for i in range(start_idx, end_idx, self.window_step):
            temp_window = []
            for _ in ts:
                temp_window.append([])
            for j in range(i, i + self.window_len):
                for t in range(len(temp_window)):
                    temp_window[t].append(ts[t][j])
            temp_windows_list.append(temp_window)

        return temp_windows_list

    def _print_logs(self, log_message: str) -> None:
        if self.args.print_logs:
            print(log_message)