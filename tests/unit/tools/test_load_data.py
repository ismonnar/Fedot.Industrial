import os

import numpy as np
import pandas as pd

from fedot_ind.api.utils.path_lib import PROJECT_PATH
from fedot_ind.tools.loader import DataLoader

ds_path = os.path.join(PROJECT_PATH, 'examples',
                       'data', 'ItalyPowerDemand_fake')


def test_init_loader():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    assert loader.dataset_name == ds_name
    assert loader.folder == path


def test_load_multivariate_data():
    # TODO: get back to loading from web when it is fixed
    # train_data, test_data = DataLoader('Epilepsy').load_data()

    # delete when loading from web is fixed
    path_folder = os.path.join(PROJECT_PATH, 'tests', 'data', 'datasets')
    train_data, test_data = DataLoader(
        'Blink', folder=path_folder).load_data()  # remove folder=path_folder also
    x_train, y_train = train_data
    x_test, y_test = test_data
    assert x_train.shape == (500, 4, 510)
    assert x_test.shape == (450, 4, 510)
    assert y_train.shape == (500,)
    assert y_test.shape == (450,)


def test_load_univariate_data():
    # train_data, test_data = DataLoader('DodgerLoopDay').load_data()

    # delete when loading from web is fixed
    path_folder = os.path.join(PROJECT_PATH, 'tests', 'data', 'datasets')
    train_data, test_data = DataLoader('ItalyPowerDemand_tsv',  # change to 'DodgerLoopDay' and adjust shapes below
                                       folder=path_folder).load_data()  # remove folder=path_folder also
    x_train, y_train = train_data
    x_test, y_test = test_data
    assert x_train.shape == (67, 24)
    assert x_test.shape == (67, 24)
    assert y_train.shape == (67,)
    assert y_test.shape == (67,)

# TODO: uncomment when loading from web is fixed
# def test_load_fake_data():
#     with pytest.raises(FileNotFoundError):
#         DataLoader('Fake').load_data()


def test__load_from_tsfile_to_dataframe():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    full_path = os.path.join(
        PROJECT_PATH,
        'examples/data/BitcoinSentiment/BitcoinSentiment_TEST.ts')
    x, y = loader._load_from_tsfile_to_dataframe(
        full_file_path_and_name=full_path, return_separate_X_and_y=True)


def test__load_from_tsfile_to_dataframe_with_timestamps():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    full_path = os.path.join(
        PROJECT_PATH,
        'examples/data/AppliancesEnergy/AppliancesEnergy_TEST.ts')
    x, y = loader._load_from_tsfile_to_dataframe(
        full_file_path_and_name=full_path, return_separate_X_and_y=True)

    assert isinstance(x, pd.DataFrame)
    assert isinstance(y, np.ndarray)
    assert x.shape[0] == y.shape[0]


def test_predict_encoding():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    full_path = os.path.join(ds_path, 'ItalyPowerDemand_fake_TEST.ts')
    encoding = loader.predict_encoding(file_path=full_path)
    assert encoding is not None


def test_read_txt_files():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    path = os.path.join(PROJECT_PATH, 'examples', 'data')
    x_train, y_train, x_test, y_test = loader.read_txt_files(
        dataset_name='ItalyPowerDemand_fake', temp_data_path=path)

    for i in [x_train, y_train, x_test, y_test]:
        assert i is not None


def test_read_ts_files():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    path = os.path.join(PROJECT_PATH, 'examples', 'data')
    x_train, y_train, x_test, y_test = loader.read_ts_files(
        dataset_name='ItalyPowerDemand_fake', data_path=path)

    for i in [x_train, y_train, x_test, y_test]:
        assert i is not None


def test_read_arff_files():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    path = os.path.join(PROJECT_PATH, 'examples', 'data')
    x_train, y_train, x_test, y_test = loader.read_arff_files(
        dataset_name='ItalyPowerDemand_fake', temp_data_path=path)

    for i in [x_train, y_train, x_test, y_test]:
        assert i is not None


def test_read_tsv():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    path = os.path.join(PROJECT_PATH, 'tests', 'data', 'datasets')
    x_train, y_train, x_test, y_test = loader.read_tsv(
        dataset_name='ItalyPowerDemand_tsv', data_path=path)

    for i in [x_train, y_train, x_test, y_test]:
        assert i is not None


def test_read_train_test_files():
    ds_name = 'name'
    path = '.'
    loader = DataLoader(dataset_name=ds_name, folder=path)
    path = os.path.join(PROJECT_PATH, 'examples', 'data')
    is_multi, (x_train, y_train), (x_test, y_test) = loader.read_train_test_files(
        dataset_name='ItalyPowerDemand_fake', data_path=path)

    for i in [x_train, y_train, x_test, y_test, is_multi]:
        assert i is not None
