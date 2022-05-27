from itertools import groupby

import dysts.base
import dysts.flows
import pytorch_lightning as pl
from pytorch_lightning.callbacks import EarlyStopping, LearningRateMonitor
from pytorch_lightning.loggers import WandbLogger
from torch.utils.data import DataLoader, random_split
from tqdm import tqdm

from config import ROOT_DIR
from ecodyna.data import load_from_params, ChunkMultiTaskDataset
from ecodyna.models.task_modules import ChunkClassifier, ChunkForecaster
from ecodyna.tasks.common import experiment_setup
from scripts.experiments.defaults import small_models


def get_logger(run_id: str, hyperparams: dict, **params):
    return WandbLogger(
        save_dir=f'{ROOT_DIR}/results',
        project=params['experiment']['project'],
        name=run_id, id=run_id,
        config={
            'ml': hyperparams,
            'data': params['data'],
            'dataloader': params['dataloader'],
            'experiment': params['experiment'],
            'trainer': {k: f'{v}' for k, v in params['trainer'].items()}
        }
    )


def get_trainer(logger, **params):
    return pl.Trainer(
        logger=logger, **params['trainer'],
        callbacks=[EarlyStopping('loss.val', patience=5, check_on_train_epoch_end=True),
                   LearningRateMonitor()]
    )


def classification_into_forecasting(params: dict):
    train_size, val_size = experiment_setup(**params)

    attractors = [getattr(dysts.flows, attractor_name)() for attractor_name in params['experiment']['attractors']]
    attractors.sort(key=lambda x: len(x.ic))  # itertools.groupby needs sorted data
    attractors_per_dim = groupby(attractors, key=lambda x: len(x.ic))

    for space_dim, attractors in attractors_per_dim:
        if space_dim != 3:
            continue
        print(f'Loading trajectories for attractors of dimension {space_dim}')
        tensors = {attractor.name: load_from_params(attractor=attractor.name, **params['data'])
                   for attractor in tqdm(list(attractors))}
        splits = {name: random_split(tensor, [train_size, val_size]) for name, tensor in tensors.items()}
        train_tensors = {name: split[0] for name, split in splits.items()}
        val_tensors = {name: split[1] for name, split in splits.items()}
        train_ds = ChunkMultiTaskDataset(train_tensors, **params['in_out'])
        val_ds = ChunkMultiTaskDataset(val_tensors, **params['in_out'])

        for Model, model_params in params['models']['list']:
            model = Model(space_dim=space_dim, n_classes=len(tensors), **model_params, **params['models']['common'])

            run_id = f'{model.name()}_dim_{space_dim}'
            forecaster = ChunkForecaster(model=model)
            wandb_logger = get_logger(f'{run_id}_fct', model.hyperparams, **params)
            trainer = get_trainer(wandb_logger, **params)
            trainer.fit(
                forecaster,
                train_dataloaders=DataLoader(train_ds.for_forecasting(), **params['dataloader'], shuffle=True),
                val_dataloaders=DataLoader(val_ds.for_forecasting(), **params['dataloader'])
            )
            wandb_logger.experiment.finish(quiet=True)

            model.freeze_featurizer()
            classifier = ChunkClassifier(model=model)
            wandb_logger = get_logger(f'{run_id}_cls', model.hyperparams, **params)
            trainer = get_trainer(wandb_logger, **params)
            trainer.fit(
                classifier,
                train_dataloaders=DataLoader(train_ds.for_classification(), **params['dataloader'], shuffle=True),
                val_dataloaders=DataLoader(val_ds.for_classification(), **params['dataloader'])
            )
            wandb_logger.experiment.finish(quiet=True)


if __name__ == '__main__':
    params = {
        'experiment': {
            'attractors': dysts.base.get_attractor_list(),
            'project': 'forecasting-into-classification',
            'train_part': 0.9,
            'random_seed': 42
        },
        'data': {
            'trajectory_count': 100,
            'trajectory_length': 100,
            'resample': True,
            'pts_per_period': 50,
            'ic_noise': 0.01,
            'seed': 42
        },
        'models': {
            'common': {'n_features': 32},
            'list': small_models
        },
        'dataloader': {
            'batch_size': 2048,
            'num_workers': 4,
            'persistent_workers': True
        },
        'trainer': {
            'max_epochs': 100,
            'deterministic': True,
            'val_check_interval': 1,
            'log_every_n_steps': 1,
            'gpus': 1
        },
        'metric_loggers': [],
        'in_out': {
            'n_in': 5,
            'n_out': 5
        }
    }
    params['models']['common'].update(params['in_out'])

    classification_into_forecasting(params)