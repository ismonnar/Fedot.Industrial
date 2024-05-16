from fedot_ind.core.models.nn.network_impl.base_nn_model import BaseNeuralModel
from typing import Optional, Callable, Any, List, Union, Tuple
from fedot.core.operations.operation_parameters import OperationParameters
from fedot.core.data.data import InputData, OutputData
from fedot_ind.core.repository.constanst_repository import CROSS_ENTROPY
import torch.optim as optim
from torch.nn import LSTM, GRU, Linear, Module, RNN
import torch
from fedot_ind.core.models.nn.network_modules.layers.special import RevIN
from fedot_ind.core.models.nn.network_modules.losses import NormalDistributionLoss
from fedot_ind.core.architecture.settings.computational import backend_methods as np
from fedot_ind.core.architecture.abstraction.decorators import convert_inputdata_to_torch_time_series_dataset
from fedot_ind.core.operation.transformation.window_selector import WindowSizeSelector
import pandas as pd
from fedot.core.repository.tasks import Task, TaskTypesEnum, TsForecastingParams
from fedot_ind.core.models.nn.network_modules.layers.special import adjust_learning_rate, EarlyStopping
from fedot.core.repository.dataset_types import DataTypesEnum
from fedot.core.operations.evaluation.operation_implementations.data_operations.ts_transformations import \
    transform_features_and_target_into_lagged
from fedot_ind.core.operation.transformation.data.hankel import HankelMatrix
from fedot_ind.core.architecture.preprocessing.data_convertor import DataConverter
import torch.utils.data as data
from fedot_ind.core.architecture.settings.computational import default_device
import torch.optim.lr_scheduler as lr_scheduler 
from fedot.core.data.data_split import train_test_data_setup


class _TSScaler(Module):
    def __init__(self):
        super().__init__()
        self.factors = None
        self.eps = 1e-10
    
    def forward(self, x, normalize=True):
        if normalize:
            self.means = x.mean(dim=-1, keepdim=True)
            self.factors = torch.sqrt(x.std(dim=-1, keepdim=True, # True results in really strange behavior of affine transformer
                             unbiased=False)) + self.eps
            return (x - self.means) / self.factors
        else:
            factors, means = self.factors, self.means
            if len(x.size()) == 4:
                factors = factors[..., None]
                means == factors[..., None]
            return x * factors + means
        
    def scale(self, x):
        return (x - self.means) / self.factors

class DeepARModule(Module):
    _loss_fns = {
        'normal': NormalDistributionLoss
    }

    def __init__(self, cell_type: str, input_size: int, hidden_size: int, 
                 rnn_layers: int, dropout: float, distribution: str):
        super().__init__()
        self.rnn = {'LSTM': LSTM, 'GRU': GRU, 'RNN': RNN}[cell_type](
            input_size = input_size,
            hidden_size = hidden_size,
            num_layers = rnn_layers,
            batch_first = True,
            dropout = dropout if rnn_layers > 1 else 0.
        )
        self.hidden_size = hidden_size
        self.scaler = _TSScaler()
        self.distribution = self._loss_fns[distribution]
        if distribution is not None:
            self.projector = Linear(self.hidden_size, len(self.distribution.distribution_arguments))
        else:
            self.projector = Linear(self.hidden_size, 2)
            

    def _encode(self, ts: torch.Tensor):
        """
        Encode sequence into hidden state
        ts.size = (length, hidden)
        """
        _, hidden_state = self.rnn(
            ts,
        )  
        return hidden_state
    
    def _decode_whole_seq(self, ts: torch.Tensor, hidden_state: torch.Tensor):
        """ used for next value predition"""
        output, hidden_state = self.rnn(
            ts, hidden_state
        )
        output = self.projector(output)
        return output, hidden_state

    def forecast(self, prefix: torch.Tensor, horizon: int, 
                 mode: str='lagged', output_mode: str='quantiles', **mode_kw):
        self.eval()
        forecast = []
        if self.rnn.input_size != 1 or mode == 'lagged':
            with torch.no_grad():
                for i in range(horizon):
                    output = self(prefix)[0]
                    forecast.append(self._transform_params(output, mode=output_mode, **mode_kw).detach().cpu())
                    prediction = self._transform_params(output, mode='predictions')
                    prefix = torch.roll(prefix, -1, dims=-1)
                    prefix[..., [-1]] = prediction
            forecast = torch.stack(forecast, dim=1).squeeze(-1)#.squeeze(1).permute(1, 2, 0)
        elif self.rnn.input_size == 1 or mode == 'auto':
            # assert self.rnn.input_size == 1, "autoregressive mode requires the features not to be lagged"
            forecast = self._autoregressive(prefix, horizon, hidden_state=None,
                                            output_mode=output_mode, **mode_kw)
        else:
            raise ValueError('Unknown forecasting type!')

        return forecast
    
    def _autoregressive(self, prefix: torch.Tensor, 
                        horizon: int, hidden_state: torch.Tensor=None, 
                        output_mode: str='quantiles', **mode_kw):
        if hidden_state is None:
            hidden_state = self._encode(prefix)
            # hidden_state = hidden_state[:, [-1], :]
        outputs = [] 
        x = prefix[[-1], ...] # what's the order of rnn processing?
        for i in range(horizon):
            output, hidden_state = self.rnn(x, hidden_state)
            outputs.append(self._transform_params(output, mode=output_mode, **mode_kw).detach().cpu())
            x = self._transform_params(output, mode='predictions')
        outputs = torch.stack(outputs, dim=1)
        return outputs 


    def forward(self, x: torch.Tensor,
                   mode='raw', **mode_kw) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass
        x.size == (nseries, length)
        """
        # encode
        x = self.scaler(x, normalize=True)
        hidden_state = self._encode(x)
        # decode
        if self.training:
            assert mode == 'raw', "cannot use another mode, but 'raw' while training"
            return self._decode_whole_seq(x, hidden_state)
        else:
            output, hidden_state = self._decode_whole_seq(x, hidden_state)
            return self._transform_params(output, 
                                          mode=mode, **mode_kw), hidden_state        
    
    def to_quantiles(self, params: torch.Tensor, quantiles=None) -> torch.Tensor:
        if quantiles is None:
            quantiles = self.quantiles
        distr = self.distribution.map_x_to_distribution(params)
        return distr.icdf(quantiles).unsqueeze(1)
    
    def to_samples(self, params: torch.Tensor, n_samples=100) -> torch.Tensor:
        distr = self.distribution.map_x_to_distribution(params)
        return distr.sample((n_samples,)).permute(1, 2, 0) # distr_n x n_samples

    def to_predictions(self, params: torch.Tensor) -> torch.Tensor:
        distr = self.distribution.map_x_to_distribution(params)
        return distr.sample((1,)).permute(1, 2, 0) # distr_n x 1
    
    def _transform_params(self, distr_params, mode='raw', **mode_kw) -> torch.Tensor:
        if mode == 'raw':
            return distr_params
        elif mode == 'quantiles':
            transformed = self.to_quantiles(distr_params, **mode_kw)
        elif mode == 'predictions':
            transformed = self.to_predictions(distr_params, **mode_kw)
        elif mode == 'samples':
            transformed = self.to_samples(distr_params, **mode_kw)
        else:
            raise ValueError('Unexpected forecast mode!')
        transformed = self.scaler(transformed, False)

        return transformed
        

class DeepAR(BaseNeuralModel):
    """No exogenous variable support
    Variational Inference + Probable Anomaly detection"""


    def __init__(self, params: Optional[OperationParameters] = {}):
        super().__init__()

        #INSIDE
        # self.epochs = params.get('epochs', 100)
        # self.batch_size = params.get('batch_size', 16)
        # self.activation = params.get('activation', 'ReLU')
        # self.learning_rate = 0.001
        
        self.cell_type = params.get('cell_type', 'LSTM')
        self.hidden_size = params.get('hidden_size', 10)
        self.rnn_layers = params.get('rnn_layers', 2)
        self.dropout = params.get('dropout', 0.1)
        self.horizon = params.get('horizon', 1)
        self.forecast_length = self.horizon
        self.expected_distribution = params.get('expected_distribution', 'normal')

        ###
        self.preprocess_to_lagged = False
        self.patch_len = params.get('patch_len', None)
        self.forecast_mode = params.get('forecast_mode', 'predictions')
        self.quantiles = params.get('quantiles', None)

        self.test_patch_len = None
    
    def _init_model(self, ts) -> tuple:
        self.loss_fn = DeepARModule._loss_fns[self.expected_distribution]()
        input_size = self.patch_len or ts.features.shape[-1]
        self.patch_len = input_size
        self.model = DeepARModule(input_size=input_size,
                                   hidden_size=self.hidden_size,
                                   cell_type=self.cell_type,
                                   dropout=self.dropout,
                                   rnn_layers=self.rnn_layers,
                                   distribution=self.expected_distribution).to(default_device())
        self.model_for_inference = DeepARModule(input_size=input_size,
                                   hidden_size=self.hidden_size,
                                   cell_type=self.cell_type,
                                   dropout=self.dropout,
                                   rnn_layers=self.rnn_layers,
                                   distribution=self.expected_distribution)
        self._evaluate_num_of_epochs(ts)
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

        return self.loss_fn, self.optimizer

    def fit(self, input_data: InputData, split_data: bool = False):
        train_loader, val_loader = self._prepare_data(input_data, split_data=split_data, horizon=1)
        loss_fn, optimizer = self._init_model(input_data)
        self._train_loop(model=self.model, 
                        train_loader=train_loader,
                        loss_fn=loss_fn, 
                        optimizer=optimizer, 
                        val_loader=val_loader,
                        )
        return self

    def _prepare_data(self, input_data: InputData, split_data, horizon=None):
        val_loader = None
        if self.preprocess_to_lagged:
            self.patch_len = input_data.features.shape[-1]
            train_loader = self.__create_torch_loader(input_data)
        else:
            if self.patch_len is None:
                dominant_window_size = WindowSizeSelector(
                    method='dff').get_window_size(input_data.features)
                self.patch_len = 2 * dominant_window_size
            train_loader, val_loader = self._get_train_val_loaders(
                    input_data.features, self.patch_len, split_data, horizon=horizon)

        self.test_patch_len = self.patch_len
        return train_loader, val_loader

    def predict(self,
                test_data: InputData,
                output_mode: str = None):
        if not output_mode:
            output_mode = self.forecast_mode
        # test_loader = self._get_test_loader(test_data)
        test_loader, _ = self._prepare_data(test_data, False, 0)
        last_patch = test_loader.dataset[-1][0][None, ...]
        fcs = self._predict(last_patch, output_mode)

        # some logic to select needed ts

        # forecast_idx_predict = np.arange(start=test_data.idx[-self.horizon],
        #                                  stop=test_data.idx[-self.horizon] +
        #                                  self.horizon,
        #                                  step=1)
        forecast_idx_predict = np.arange(start=test_data.idx[-1],
                                         stop=test_data.idx[-1] + self.horizon,
                                         step=1)
        predict = OutputData(
            idx=forecast_idx_predict,
            task=self.task_type,
            predict=fcs.reshape(self.horizon, -1, fcs.size(-1)),
            target=self.target,
            data_type=DataTypesEnum.table)
        
        return predict
        
        
    def _predict(self, x, output_mode, **output_kw):
        mode = 'lagged' if self.preprocess_to_lagged else 'auto'
        x = x.to(default_device())
        fc = self.model.forecast(x, self.horizon, mode, output_mode, **output_kw)
        return fc

    def predict_for_fit(self,
                        test_data,
                        output_mode: str = 'labels'): # will here signature conflict raise in case I drop kw?
        output_mode = 'predictions' 
        # test_loader = self._get_test_loader(test_data)
        fcs = self._predict(test_loader, output_mode)

        # test_loader = self._get_test_loader(test_data)
        test_loader, _ = self._prepare_data(test_data, False, 0)
        last_patch = test_loader.dataset[-1][0][None, ...]
        fcs = self._predict(last_patch, output_mode)

        # some logic to select needed ts

        # forecast_idx_predict = np.arange(start=test_data.idx[-self.horizon],
        #                                  stop=test_data.idx[-self.horizon] +
        #                                  self.horizon,
        #                                  step=1)
        forecast_idx_predict = np.arange(start=test_data.idx[-1],
                                         stop=test_data.idx[-1] + self.horizon,
                                         step=1)

        predict = OutputData(
            idx=forecast_idx_predict,
            task=self.task_type,
            predict=fcs.squeeze().numpy(),
            target=self.target,
            data_type=DataTypesEnum.table)   
        return predict
    

    def _train_loop(self, model,
                    train_loader,
                    loss_fn,
                    val_loader,
                    optimizer):
        train_steps = len(train_loader)
        early_stopping = EarlyStopping()
        scheduler = lr_scheduler.OneCycleLR(optimizer=optimizer,
                                            steps_per_epoch=train_steps,
                                            epochs=self.epochs,
                                            max_lr=self.learning_rate)
        kwargs = {'lradj': 'type3'}

        best_model = None
        best_val_loss = float('inf')

        for epoch in range(self.epochs):
            iter_count = 0
            train_loss = []
            model.train()
            training_loss = 0.0
            valid_loss = 0.0

            for i, (batch_x, batch_y) in enumerate(train_loader):
                iter_count += 1
                optimizer.zero_grad()
                batch_x = batch_x.float().to(default_device())
                batch_y = batch_y[:, ..., [0]].float().to(default_device()) # only first entrance
                outputs, *hidden_state = model(batch_x)
                # return batch_x, outputs, batch_y

                loss = loss_fn(outputs, batch_y, self.model.scaler)
                train_loss.append(loss.item())

                loss.backward()
                optimizer.step()

                # adjust_learning_rate(optimizer, scheduler,
                #                      epoch, learning_rate=, printout=False, **kwargs)
                scheduler.step()
            if val_loader is not None and epoch % val_interval == 0:
                model.eval()
                total = 0
                for batch in val_loader:
                    inputs, targets = batch
                    output = model(inputs)

                    loss = loss_fn(output, targets.float())

                    valid_loss += loss.data.item() * inputs.size(0)
                    total += inputs.size(0)
                valid_loss /= total
                if valid_loss < best_val_loss:
                    best_val_loss = valid_loss
                    best_model = copy.deepcopy(model)

            train_loss = np.average(train_loss)
            print("Epoch: {0}, Steps: {1} | Train Loss: {2:.7f}".format(
                epoch + 1, train_steps, train_loss))
            if early_stopping.early_stop:
                print("Early stopping")
                break
            print('Updating learning rate to {}'.format(
                scheduler.get_last_lr()[0]))
        return best_model


    @convert_inputdata_to_torch_time_series_dataset
    def _create_dataset(self,
                        ts: InputData,
                        flag: str = 'test',
                        batch_size: int = 16,
                        freq: int = 1):
        return ts
    
    def _get_train_val_loaders(self,
                      ts,
                      patch_len=None,
                      split_data: bool = True,
                      validation_blocks: int = None, 
                      horizon=None):
        if not horizon:
            horizon = self.horizon
        if patch_len is None:
            patch_len = self.patch_len
        train_data = self.__ts_to_input_data(ts)
        if split_data:
            raise NotImplementedError('Problem with lagged_data splitting')
            train_data, val_data = train_test_data_setup(
                train_data, validation_blocks=validation_blocks)
            _, train_data.features, train_data.target = transform_features_and_target_into_lagged(train_data,
                                                                                                  horizon,
                                                                                                  patch_len)
            _, val_data.features, val_data.target = transform_features_and_target_into_lagged(val_data,
                                                                                              horizon,
                                                                                              patch_len)
            val_loader = self.__create_torch_loader(val_data)
            train_loader = self.__create_torch_loader(train_data)
            return train_loader, val_loader
        else:
            _, train_data.features, train_data.target = transform_features_and_target_into_lagged(train_data,
                                                                                                  horizon,
                                                                                                  patch_len)
        train_loader = self.__create_torch_loader(train_data)
        return train_loader, None


    def __ts_to_input_data(self, input_data: Union[InputData, pd.DataFrame]):
        if isinstance(input_data, InputData):
            return input_data
        
        task = Task(TaskTypesEnum.ts_forecasting,
                    TsForecastingParams(forecast_length=self.horizon))
        
        if not isinstance(input_data, pd.DataFrame):
            time_series = pd.DataFrame(input_data)

        if 'datetime' in time_series.columns:
            idx = pd.to_datetime(time_series['datetime'].values)
        else:
            idx = np.arange(len(time_series.values.flatten()))

        time_series = time_series.values

        train_input = InputData(idx=idx,
                                features=time_series.flatten(),
                                target=time_series.flatten(),
                                task=task,
                                data_type=DataTypesEnum.ts)
        
        return train_input

    def __create_torch_loader(self, train_data):
        train_dataset = self._create_dataset(train_data)
        train_loader = torch.utils.data.DataLoader(
            data.TensorDataset(train_dataset.x, train_dataset.y),
            batch_size=self.batch_size, shuffle=False)
        return train_loader
    
    
    def _get_test_loader(self,
                      test_data: Union[InputData, torch.Tensor]):
        test_data = self.__ts_to_input_data(test_data)
        if len(test_data.features.shape) == 1:
            test_data.features = test_data.features[None, ...]
        
        if not self.preprocess_to_lagged:
            features = HankelMatrix(time_series=test_data.features,
                                    window_size=self.test_patch_len or self.patch_len).trajectory_matrix
            features = torch.from_numpy(DataConverter(data=features).
                                        convert_to_torch_format()).float().permute(2, 1, 0)
            target = torch.from_numpy(DataConverter(
                data=features).convert_to_torch_format()).float()
        else:
        # if True:
            features = test_data.features
            features = torch.from_numpy(DataConverter(data=features).
                                        convert_to_torch_format()).float()
            target = torch.from_numpy(DataConverter(
                data=features).convert_to_torch_format()).float()
        test_loader = torch.utils.data.DataLoader(data.TensorDataset(features, target),
                                                  batch_size=self.batch_size, shuffle=False)
        return test_loader
    
    