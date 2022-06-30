from cases.run.SignalRunner import SignalRunner
from cases.run.utils import read_tsv

if __name__ == '__main__':
    dict_of_dataset = {
        'Herring': read_tsv('Herring'),
        'Haptics': read_tsv('Haptics'),
        'DodgerLoopDay': read_tsv('DodgerLoopDay'),
        'Earthquakes': read_tsv('Earthquakes'),
        'FordA': read_tsv('FordA'),
        'FordB': read_tsv('FordB'),
        'Plane': read_tsv('Plane'),
        'Trace': read_tsv('Trace'),
        'ItalyPowerDemand': read_tsv('ItalyPowerDemand'),
        'Lightning7': read_tsv('Lightning7'),
        'ElectricDevices': read_tsv('ElectricDevices'),
        'Beef': read_tsv('Beef'),
        'PowerCons': read_tsv('PowerCons'),
        'ShapesAll': read_tsv('ShapesAll'),
        'EthanolLevel': read_tsv('EthanolLevel')
    }

    dict_of_wavelet_list = {
        'ElectricDevices': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'DodgerLoopDay': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'EthanolLevel': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'Earthquakes': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'Lightning7': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'Beef': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'ItalyPowerDemand': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'Haptics': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'ShapesAll': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'FordA': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'FordB': ['db5', 'sym5', 'coif5', 'bior2.4'],
        'PowerCons': ['db5', 'sym5', 'coif5', 'bior2.4'],
    }

    dict_of_win_list = {
        'ItalyPowerDemand': [3, 6, 9],
        'Herring': [48, 128, 170],
        'Haptics': [110, 220, 330],
        'DodgerLoopDay': [28, 56, 84],
        'Earthquakes': [48, 128, 170],
        'FordA': [50, 100, 150],
        'FordB': [50, 100, 150],
        'Plane': [14, 28, 42],
        'Trace': [27, 54, 81],
        'Lightning7': [32, 64, 96],
        'EthanolLevel': [170, 340, 510],
        'ElectricDevices': [10, 20, 30],
        'Beef': [100, 150, 200],
        'PowerCons': [30, 45, 60],
        'ShapesAll': [100, 150, 200]
    }

    list_of_dataset = [
        #'ItalyPowerDemand',
        # 'Haptics',
        'DodgerLoopDay',
        # 'Earthquakes',
        # 'FordA',
        # 'FordB',
        # # # 'Plane',
        # # # 'Trace',
        'Lightning7',
        'PowerCons',
        # 'ShapesAll',
        # 'Beef',
        # 'ElectricDevices',
        # 'EthanolLevel'
    ]


    fedot_params = {'problem': 'classification',
                    'seed': 42,
                    'timeout': 15,
                    'composer_params': {'max_depth': 10,
                                        'max_arity': 4,
                                        'cv_folds': 3,
                                        'stopping_after_n_generation': 20
                                        },
                    'verbose_level': 2,
                    'n_jobs': 4}

    runner = SignalRunner(list_of_dataset,
                          launches=3,
                          fedot_params=fedot_params)

    models = runner.run_experiment(dict_of_dataset=dict_of_dataset,
                                   dict_of_win_list=dict_of_wavelet_list,
                                   method='wavelet')

    print('VSE')