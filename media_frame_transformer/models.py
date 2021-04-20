import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import RobertaModel

from media_frame_transformer.experiment_config import VOCAB_SIZE
from media_frame_transformer.utils import DEVICE

_MODELS = {}


def get_model(arch: str):
    return _MODELS[arch]()


def register_model(arch: str):
    def _register(f):
        assert arch not in _MODELS
        _MODELS[arch] = f
        return f

    return _register


class LinearRegressionModel(nn.Module):
    def __init__(
        self,
        task="c",
        use_label_distribution_deviation=False,
    ):
        super().__init__()
        self.task = task
        assert task in ["c", "rs"]

        self.use_label_distribution_deviation = use_label_distribution_deviation
        print(use_label_distribution_deviation)

        self.ff = nn.Linear(
            VOCAB_SIZE,
            15,
            # bias=not use_label_distribution_deviation,
        )
        # nn.init.constant_(self.ff.weight, 0)

    def forward(self, batch):

        bow = batch["bow"].to(DEVICE).to(torch.float)
        logits = self.ff(bow)

        if self.task == "c":
            labels = batch["primary_frame_idx"].to(DEVICE)
            frame_loss = F.cross_entropy(logits, labels, reduction="none")
            loss = frame_loss
        # elif self.task == "rm":
        #     labels = batch["both_frame_vec"].to(DEVICE)
        #     frame_loss = F.binary_cross_entropy_with_logits(
        #         logits, labels, reduction="none"
        #     )
        #     frame_loss = frame_loss.mean(dim=-1)
        #     loss = frame_loss
        elif self.task == "rs":
            labels = batch["primary_frame_vec"].to(DEVICE)
            frame_loss = F.binary_cross_entropy_with_logits(
                logits, labels, reduction="none"
            )
            frame_loss = frame_loss.mean(dim=-1)
            loss = frame_loss
        else:
            raise NotImplementedError()

        if (
            hasattr(self, "use_label_distribution_deviation")
            and self.use_label_distribution_deviation
        ):
            if self.task in ["c", "rs"]:
                label_distribution = batch["primary_frame_distr"]
            elif self.task == "rm":
                label_distribution = batch["both_frame_distr"]
            else:
                raise NotImplementedError()
            logits = logits + torch.log(label_distribution.to(DEVICE).to(torch.float))

        loss = loss.sum()
        return {
            "logits": logits,
            "loss": loss,
            "labels": labels,
        }


@register_model("linreg.c")
def _():
    return LinearRegressionModel(task="c")


@register_model("linreg.rs")
def _():
    return LinearRegressionModel(task="rs")


@register_model("linreg.c_dev")
def _():
    return LinearRegressionModel(task="c", use_label_distribution_deviation=True)


class RobertaFrameClassifier(nn.Module):
    def __init__(
        self,
        dropout=0.1,
        n_class=15,
        task="c",
        use_label_distribution_input=None,
        use_label_distribution_deviation=False,
    ):
        super(RobertaFrameClassifier, self).__init__()
        self.task = task
        assert task in ["c", "rm", "rs"]

        self.roberta = RobertaModel.from_pretrained(
            "roberta-base", hidden_dropout_prob=dropout
        )
        self.dropout = nn.Dropout(p=dropout)
        self.roberta_emb_size = 768

        self.use_label_distribution_input = use_label_distribution_input
        if use_label_distribution_input is not None:
            if use_label_distribution_input == "ff":
                self.label_distribution_intake = nn.Sequential(
                    nn.Linear(15, 64),
                    nn.Tanh(),
                )
                self.roberta_emb_size += 64
            elif use_label_distribution_input == "id":
                self.label_distribution_intake = nn.Identity()
                self.roberta_emb_size += 15
            else:
                raise NotImplementedError()

        self.frame_ff = nn.Sequential(
            nn.Linear(self.roberta_emb_size, 768),
            nn.Tanh(),
            nn.Dropout(p=dropout),
            nn.Linear(768, n_class),
        )

        self.use_label_distribution_deviation = use_label_distribution_deviation

    def forward(self, batch):
        x = batch["x"].to(DEVICE)
        x = self.roberta(x)
        x = x[0]
        x = self.dropout(x)
        cls_emb = x[:, 0, :]  # the <s> tokens, i.e. <CLS>
        cls_emb = self.dropout(cls_emb)

        if self.task in ["c", "rs"]:
            label_distribution = batch["primary_frame_distr"]
        elif self.task == "rm":
            label_distribution = batch["both_frame_distr"]
        else:
            raise NotImplementedError()

        if (
            hasattr(self, "use_label_distribution_input")
            and self.use_label_distribution_input is not None
        ):
            label_distribution_encoded = self.label_distribution_intake(
                label_distribution.to(DEVICE).to(torch.float)
            )
            cls_emb = torch.cat([cls_emb, label_distribution_encoded], dim=-1)

        frame_out = self.frame_ff(cls_emb)  # (b, nclass)

        if (
            hasattr(self, "use_label_distribution_deviation")
            and self.use_label_distribution_deviation
        ):
            frame_out = frame_out + torch.log(
                label_distribution.to(DEVICE).to(torch.float)
            )

        # calculate loss
        if self.task == "c":
            labels = batch["primary_frame_idx"].to(DEVICE)
            frame_loss = F.cross_entropy(frame_out, labels, reduction="none")
            loss = frame_loss
        elif self.task == "rm":
            labels = batch["both_frame_vec"].to(DEVICE)
            frame_loss = F.binary_cross_entropy_with_logits(
                frame_out, labels, reduction="none"
            )
            frame_loss = frame_loss.mean(dim=-1)
            loss = frame_loss
        elif self.task == "rs":
            labels = batch["primary_frame_vec"].to(DEVICE)
            frame_loss = F.binary_cross_entropy_with_logits(
                frame_out, labels, reduction="none"
            )
            frame_loss = frame_loss.mean(dim=-1)
            loss = frame_loss

        loss_weight = batch["weight"].to(DEVICE)
        loss = (loss * loss_weight).mean()

        return {
            "logits": frame_out,
            "loss": loss,
            "labels": labels,
        }


def freeze_roberta_top_n_layers(model, n):
    # pretrained roberta = embeddings -> encoder.laysers -> classfier
    for param in model.roberta.embeddings.parameters():
        param.requires_grad = False
    for i, module in enumerate(model.roberta.encoder.layer):
        if i < n:
            for param in module.parameters():
                param.requires_grad = False
    return model


def freeze_roberta_all_transformer(model):
    model = freeze_roberta_top_n_layers(model, 12)
    return model


def freeze_roberta_module(model):
    for param in model.roberta.parameters():
        param.requires_grad = False
    return model


def create_models(name, dropout, task):
    @register_model(f"roberta_{name}.{task}")
    def _():
        return RobertaFrameClassifier(dropout=dropout, task=task)

    @register_model(f"roberta_{name}.{task}_dev")
    def _():
        return RobertaFrameClassifier(
            dropout=dropout,
            task=task,
            use_label_distribution_input=None,
            use_label_distribution_deviation=True,
        )


for name, dropout in [("meddrop", 0.15), ("highdrop", 0.2)]:
    for task in ["c", "rm", "rs"]:
        create_models(name, dropout, task)
