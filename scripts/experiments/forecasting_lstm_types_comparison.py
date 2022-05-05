from pytorch_lightning.callbacks import EarlyStopping

from ecodyna.metrics import RNNForecastMetricLogger
from ecodyna.mutitask_models import MultiTaskRNN
from scripts.experiments.forecasting_experiment import run_forecasting_experiment

if __name__ == '__main__':
    params = {
        'experiment': {
            'project': 'lstm-forecasting-comparison',
            'train_part': 0.75,
            'random_seed': 26,
            'n_splits': 5
        },
        'data': {
            'attractor': 'Lorenz',
            'trajectory_count': 100,
            'trajectory_length': 1000,
            'resample': True,
            'pts_per_period': 50,
            'ic_noise': 0.01
        },
        'models': {
            'common': {'model': 'LSTM', 'n_hidden': 32, 'n_layers': 1},
            'list': [
                (MultiTaskRNN, {'forecast_type': 'one_by_one'}),
                (MultiTaskRNN, {'forecast_type': 'multi'})
            ]
        },
        'dataloader': {
            'batch_size': 64,
            'num_workers': 8
        },
        'trainer': {
            'max_epochs': 50,
            'callbacks': [EarlyStopping('val_loss', patience=5)]
        },
        'metric_loggers': [RNNForecastMetricLogger],
        'in_out': {
            'n_in': 5,
            'n_out': 5
        }
    }
    params['models']['common'].update(params['in_out'])

    run_forecasting_experiment(params=params)
