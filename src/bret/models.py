import logging

import torch
import torch.nn as nn
from transformers import AutoModel, AutoTokenizer

from bret.layers.linear import BayesianLinear
from bret.model_utils import get_hf_model_id

logger = logging.getLogger(__name__)


def model_factory(model_name, method, device):
    if method == "vi":
        logger.info("Instantiating a Bayesian BERT retriever.")
        tokenizer, model = BayesianBERTRetriever.build(get_hf_model_id(model_name), device=device)
    else:
        logger.info("Instantiating a BERT retriever.")
        tokenizer, model = BERTRetriever.build(get_hf_model_id(model_name), device=device)
    return tokenizer, model


def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)


class BERTRetriever(nn.Module):
    def __init__(self, backbone, device="cpu"):
        super().__init__()
        self.backbone = backbone
        self.to(device)

    def forward(self, query=None, passage=None):
        qry_reps = self._encode(query)
        psg_reps = self._encode(passage)
        return (qry_reps, psg_reps)

    def _encode(self, qry_or_psg):
        if qry_or_psg is None:
            return None
        out = self.backbone(**qry_or_psg, return_dict=True)
        embeddings = mean_pooling(out, qry_or_psg["attention_mask"])
        return embeddings

    @classmethod
    def build(cls, model_name, device="cpu", **hf_kwargs):
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        backbone = AutoModel.from_pretrained(model_name, **hf_kwargs)
        return tokenizer, cls(backbone, device=device)


class BayesianBERTRetriever(BERTRetriever):
    def __init__(self, backbone, device="cpu"):
        super().__init__(backbone, device)
        for i in range(len(backbone.encoder.layer)):
            self.backbone.encoder.layer[i].attention.self.query = BayesianLinear(
                self.backbone.encoder.layer[i].attention.self.query
            )
            self.backbone.encoder.layer[i].attention.self.key = BayesianLinear(
                self.backbone.encoder.layer[i].attention.self.key
            )
            self.backbone.encoder.layer[i].attention.self.value = BayesianLinear(
                self.backbone.encoder.layer[i].attention.self.value
            )
            self.backbone.encoder.layer[i].attention.output.dense = BayesianLinear(
                self.backbone.encoder.layer[i].attention.output.dense
            )
            self.backbone.encoder.layer[i].intermediate.dense = BayesianLinear(
                self.backbone.encoder.layer[i].intermediate.dense
            )
            self.backbone.encoder.layer[i].output.dense = BayesianLinear(self.backbone.encoder.layer[i].output.dense)
        self.backbone.pooler.dense = BayesianLinear(self.backbone.pooler.dense)

    def kl(self):
        sum_kld = None
        for _, m in self.backbone.named_modules():
            if type(m) == BayesianLinear:
                if sum_kld is None:
                    sum_kld = m.kl()
                else:
                    sum_kld += m.kl()
        return sum_kld

    def forward(self, query=None, passage=None, num_samples=None):
        if num_samples is None:
            qry_reps = self._encode(query)
            if qry_reps is not None:
                qry_reps = qry_reps.unsqueeze(1)
            psg_reps = self._encode(passage)
            if psg_reps is not None:
                psg_reps = psg_reps.unsqueeze(1)
            return (qry_reps, psg_reps)

        qry_reps = self._encode_vi(query, num_samples)
        psg_reps = self._encode_vi(passage, num_samples)

        return (qry_reps, psg_reps)

    def _encode_vi(self, qry_or_psg, num_samples):
        reps = None
        if qry_or_psg is not None:
            batch_size = qry_or_psg["input_ids"].size(0)
            qry_or_psg["input_ids"] = qry_or_psg["input_ids"].repeat_interleave(num_samples, dim=0)
            qry_or_psg["attention_mask"] = qry_or_psg["attention_mask"].repeat_interleave(num_samples, dim=0)
            reps = self._encode(qry_or_psg).reshape(batch_size, num_samples, -1)
        return reps
