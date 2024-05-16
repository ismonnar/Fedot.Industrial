from fedot_ind.core.models.nn.network_impl.base_nn_model import BaseNeuralModel
from typing import Optional, Callable, Any, List, Union
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

class DeepARModule(Module):
    _loss_fns = {
        'normal': NormalDistributionLoss
    }

    def __init__(self, cell_type, input_size, hidden_size, rnn_layers, dropout, distribution):
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

    def forecast(self, prefix: torch.Tensor, horizon, mode='lagged', output_mode='quantiles', **mode_kw):
        self.eval()
        forecast = []
        if mode == 'lagged':
            with torch.no_grad():
                for i in range(horizon):
                    output = self(prefix)[0]
                    forecast.append(self._transform_params(output, target_scale=self.target_scale, mode=output_mode, **mode_kw).detach().cpu())
                    prediction = self._transform_params(output, target_scale=self.target_scale, 
                                                        mode='predictions')
                    prefix = torch.roll(prefix, -1, dims=-1)
                    prefix[..., [-1]] = prediction
            forecast = torch.stack(forecast)#.squeeze(1).permute(1, 2, 0)
        elif mode == 'auto':
            assert self.rnn.input_size == 1, "autoregressive mode requires the features not to be lagged"
        else:
            raise ValueError('Unknown forecasting type!')
        return forecast
    

    def forward(self, x: torch.Tensor,
                #  n_samples: int = None,
                   mode='raw', **mode_kw):
        """
        Forward pass
        x.size == (nseries, length)
        """
        x = self.scaler(x, normalize=True)
        hidden_state = self._encode(x)
        # decode
        
        if self.training:
            # assert n_samples is None, "cannot sample from decoder when training"
            assert mode == 'raw', "cannot use another mode, but 'raw' while training"
            return self._decode_whole_seq(x, hidden_state)
        else:
            output, hidden_state = self._decode_whole_seq(x, hidden_state)
            return self._transform_params(output, 
                                          mode=mode, **mode_kw), hidden_state        
    
    def to_quantiles(self, params: torch.Tensor, quantiles=None):
        if quantiles is None:
            quantiles = self.quantiles
        distr = self.distribution.map_x_to_distribution(params)
        return distr.icdf(quantiles).unsqueeze(1)
    
    def to_samples(self, params: torch.Tensor, n_samples=100):
        distr = self.distribution.map_x_to_distribution(params)
        return distr.sample((n_samples,)).permute(1, 2, 0) # distr_n x n_samples

    def to_predictions(self, params: torch.Tensor):
        distr = self.distribution.map_x_to_distribution(params)
        return distr.sample((1,)).permute(1, 2, 0) # distr_n x 1
    
    def _transform_params(self, distr_params, mode='raw', **mode_kw):
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
        

    
    def _decode_one(self, x,
                idx,
                hidden_state,
                ):
        x = x[..., [idx]]
        prediction, hidden_state = self._decode_whole_seq(x, hidden_state)
        prediction = prediction[:, [0], ...]  # select first time step fo this index
        return prediction, hidden_state

    def _decode_autoregressive(
        self,
        hidden_state: Any,
        first_target: Union[List[torch.Tensor], torch.Tensor],
        n_decoder_steps: int,
        n_samples: int = 1,
        **kwargs,
    ) -> Union[List[torch.Tensor], torch.Tensor]:

        # make predictions which are fed into next step
        output = []
        current_target = first_target
        current_hidden_state = hidden_state

        normalized_output = [first_target]

        for idx in range(n_decoder_steps):
            # get lagged targets
            current_target, current_hidden_state = self._decode_one(
                idx, 
                # lagged_targets=normalized_output, 
                hidden_state=current_hidden_state, **kwargs
            )

            # get prediction and its normalized version for the next step
            prediction, current_target = self.output_to_prediction(
                current_target, 
                # target_scale=target_scale,
                n_samples=n_samples
            )
            # save normalized output for lagged targets
            normalized_output.append(current_target)
            # set output to unnormalized samples, append each target as n_batch_samples x n_random_samples

            output.append(prediction)
        output = torch.stack(output, dim=1)
        return output


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
        self.forecast_mode = params.get('forecast_mode', 'raw')
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
        train_loader, val_loader = self._prepare_data(input_data, split_data=split_data)
        loss_fn, optimizer = self._init_model(input_data)
        self._train_loop(model=self.model, 
                        train_loader=train_loader,
                        loss_fn=loss_fn, 
                        optimizer=optimizer, 
                        val_loader=val_loader,
                        )
        return self

    def _prepare_data(self, input_data: InputData, split_data):
        val_loader = None
        # define patch_len
        if self.preprocess_to_lagged:
            self.patch_len = input_data.features.shape[-1]
            train_loader = self.__create_torch_loader(input_data)
        else:
            if self.patch_len is None:
                dominant_window_size = WindowSizeSelector(
                    method='dff').get_window_size(input_data.features)
                self.patch_len = 2 * dominant_window_size
            train_loader, val_loader = self._get_train_val_loaders(
                    input_data.features, self.patch_len, split_data)

        self.test_patch_len = self.patch_len
        return train_loader, val_loader



    def _predict_loop(self, test_loader, output_mode):
        model = self.model # or model for inference? 
        output = model.predict(test_loader, output_mode)

        y_pred = output #
        forecast_idx_predict = np.arange(start=test_data.idx[-self.horizon],
                                         stop=test_data.idx[-self.horizon] +
                                         self.horizon,
                                         step=1)
        predict = OutputData(
            idx=forecast_idx_predict,
            task=self.task_type,
            predict=y_pred.reshape(1, -1),
            target=self.target,
            data_type=DataTypesEnum.table)
        return predict

    def predict_for_fit(self,
                        test_data,
                        output_mode: str='samples'):
        y_pred = []
        true_mode = self.forecast_mode

        self.forecast_mode = output_mode
        model = self.model
        ##########

        y_pred = np.array(y_pred)
        y_pred = y_pred.squeeze()
        forecast_idx_predict = test_data.idx
        predict = OutputData(
            idx=forecast_idx_predict,
            task=self.task_type,
            predict=y_pred,
            target=self.target,
            data_type=DataTypesEnum.table)
        self.forecast_mode = true_mode
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

                loss = loss_fn(outputs, batch_y)
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

    def __predict_loop(self, test_loader):
        outputs = []
        with torch.no_grad():
            for x_test in test_loader:
                outputs.append(self.model.predict(x_test))
        output = torch.stack(outputs, dim=0)
        return output


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
                      unsqueeze_0=True):
        if patch_len is None:
            patch_len = self.patch_len
        train_data = self.__ts_to_input_data(ts)
        if split_data:
            raise NotImplementedError('Problem with lagged_data splitting')
            train_data, val_data = train_test_data_setup(
                train_data, validation_blocks=validation_blocks)
            _, train_data.features, train_data.target = transform_features_and_target_into_lagged(train_data,
                                                                                                  self.horizon,
                                                                                                  patch_len)
            _, val_data.features, val_data.target = transform_features_and_target_into_lagged(val_data,
                                                                                              self.horizon,
                                                                                              patch_len)
            val_loader = self.__create_torch_loader(val_data)
            train_loader = self.__create_torch_loader(train_data)
            return train_loader, val_loader
        else:
            _, train_data.features, train_data.target = transform_features_and_target_into_lagged(train_data,
                                                                                                  self.horizon,
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
            features = test_data.features
            features = torch.from_numpy(DataConverter(data=features).
                                        convert_to_torch_format()).float()
            target = torch.from_numpy(DataConverter(
                data=features).convert_to_torch_format()).float()
        test_loader = torch.utils.data.DataLoader(data.TensorDataset(features, target),
                                                  batch_size=self.batch_size, shuffle=False)
        return test_loader
    
    