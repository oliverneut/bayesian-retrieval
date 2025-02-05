import torch


def encode_query_mean(qry_emb):
    return qry_emb.mean(dim=0)


def encode_passage_mean(psg_emb):
    return psg_emb.mean(dim=0)


def encode_queries(queries, tokenizer, encoder, device, method, num_samples=None, max_qry_len=32):
    qry_embs = []
    with torch.no_grad():
        for _, qry in queries:
            qry_enc = tokenizer(
                qry, padding="max_length", truncation=True, max_length=max_qry_len, return_tensors="pt"
            ).to(device)
            if method == "bret":
                qry_emb = encoder(qry_enc, num_samples=num_samples)
                qry_emb = encode_query_mean(qry_emb)
            else:
                qry_emb = encoder(qry_enc)
            qry_embs.append(qry_emb.detach().cpu())
        qry_embs = torch.cat(qry_embs, dim=0)
    return qry_embs


def encode_corpus(corpus, tokenizer, encoder, device, method, num_samples=None, max_psg_len=256):
    psg_embs = []
    with torch.no_grad():
        for _, psg in corpus:
            psg_enc = tokenizer(
                psg, padding="max_length", truncation=True, max_length=max_psg_len, return_tensors="pt"
            ).to(device)
            if method == "bret":
                psg_emb = encoder(psg_enc, num_samples=num_samples)
                psg_emb = encode_passage_mean(psg_emb)
            else:
                psg_emb = encoder(psg_enc)
            psg_embs.append(psg_emb.detach().cpu())
        psg_embs = torch.cat(psg_embs, dim=0)
    return psg_embs
