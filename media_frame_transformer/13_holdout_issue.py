from os import mkdir
from os.path import exists, join

from config import ISSUES, MODELS_DIR

from media_frame_transformer import models
from media_frame_transformer.dataset import (
    PrimaryFrameDataset,
    get_kfold_primary_frames_datasets,
    load_all_primary_frame_samples,
)
from media_frame_transformer.eval import reduce_and_save_metrics
from media_frame_transformer.experiment_config import (
    ARCH,
    BATCHSIZE,
    FOLDS_TO_RUN,
    KFOLD,
)
from media_frame_transformer.experiments import run_experiments
from media_frame_transformer.learning import train
from media_frame_transformer.utils import mkdir_overwrite, write_str_list_as_txt

EXPERIMENT_NAME = f"13.{ARCH}"


def _train():
    path2datasets = {}

    for holdout_issue in ISSUES:
        model_name = f"holdout_{holdout_issue}"
        # train on all issues other than the holdout one
        train_issues = [iss for iss in ISSUES if iss != holdout_issue]

        kfold_datasets = get_kfold_primary_frames_datasets(train_issues, KFOLD)
        holdout_issue_all_samples = load_all_primary_frame_samples([holdout_issue])
        holdout_issue_dataset = PrimaryFrameDataset(holdout_issue_all_samples)

        for ki in FOLDS_TO_RUN:
            path2datasets[
                join(MODELS_DIR, EXPERIMENT_NAME, model_name, f"fold_{ki}")
            ] = {
                "train": kfold_datasets[ki]["train"],
                "valid": kfold_datasets[ki]["valid"],
                "additional_valid_datasets": {"holdout_issue": holdout_issue_dataset},
            }
    run_experiments(ARCH, path2datasets, batchsize=BATCHSIZE)


if __name__ == "__main__":
    _train()
    reduce_and_save_metrics(join(MODELS_DIR, EXPERIMENT_NAME))
