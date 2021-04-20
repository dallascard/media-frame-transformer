import sys
from collections import defaultdict
from os import makedirs
from os.path import join
from pprint import pprint
from random import Random

import media_frame_transformer.models_roberta  # noqa
from config import BATCHSIZE, ISSUES, MODELS_DIR
from media_frame_transformer.dataset import PrimaryFrameDataset
from media_frame_transformer.eval import reduce_and_save_metrics
from media_frame_transformer.experiments import run_experiments
from media_frame_transformer.learning import (
    N_DATALOADER_WORKER,
    VALID_BATCHSIZE,
    valid_epoch,
)
from media_frame_transformer.text_samples import load_all_text_samples

_arch = sys.argv[1]
EXPERIMENT_NAME = f"3f.{_arch}"


# RNG = Random()
# RNG_SEED = 0xDEADBEEF
# RNG.seed(RNG_SEED)

# DISTR_WRONGNESS_NUM_TRIALS = 5


def _train():
    path2datasets = {}

    for holdout_issue in ISSUES:
        model_name = f"holdout_{holdout_issue}"

        train_issues = [iss for iss in ISSUES if iss != holdout_issue]
        train_issues_all_samples = load_all_text_samples(
            train_issues,
            split="train",
            task="primary_frame",
        )
        train_issue_dataset = PrimaryFrameDataset(train_issues_all_samples)

        holdout_issue_all_samples = load_all_text_samples(
            [holdout_issue],
            split="train",
            task="primary_frame",
        )
        holdout_issue_dataset = PrimaryFrameDataset(holdout_issue_all_samples)

        path2datasets[join(MODELS_DIR, EXPERIMENT_NAME, model_name)] = {
            "train": train_issue_dataset,
            "valid": holdout_issue_dataset,
        }
    run_experiments(
        _arch,
        path2datasets,
        batchsize=BATCHSIZE,
        num_early_stop_non_improve_epoch=10,
        max_epochs=10,
    )


# def _eval_distribution_wrongness():
#     issue2samplesize2trial2f1 = defaultdict(lambda: defaultdict(dict))
#     for issue in ISSUES:
#         model = torch.load(
#             join(MODELS_DIR, EXPERIMENT_NAME, f"holdout_{issue}", "checkpoint.pth")
#         ).to(DEVICE)

#         all_samples = load_all_text_samples(
#             [issue],
#             split="train",
#             task="primary_frame",
#         )
#         for trial in range(DISTR_WRONGNESS_NUM_TRIALS):
#             RNG.shuffle(all_samples)

#             for numsample in DATASET_SIZES:
#                 selected_samples = all_samples[:numsample]
#                 props = np.zeros((15,)) + 1e-8
#                 for sample in selected_samples:
#                     props[frame_code_to_idx(sample.code)] += 1
#                 props = props / props.sum()

#                 dataset = PrimaryFrameDataset(
#                     all_samples, issue2props_override={issue: props}
#                 )
#                 loader = DataLoader(
#                     dataset, batch_size=VALID_BATCHSIZE, num_workers=N_DATALOADER_WORKER
#                 )
#                 metrics = valid_epoch(model, loader)
#                 issue2samplesize2trial2f1[issue][numsample][trial] = metrics["f1"]

#             pprint(issue2samplesize2trial2f1)

#     savedir = join(OUTPUTS_DIR, _arch)
#     makedirs(savedir, exist_ok=True)
#     savepath = join(savedir, "13f_distr_wrongness.json")
#     save_json(dict(issue2samplesize2trial2f1), savepath)


if __name__ == "__main__":
    _train()
    # _eval_distribution_wrongness()
    reduce_and_save_metrics(join(MODELS_DIR, EXPERIMENT_NAME))
