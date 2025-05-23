from collections import defaultdict
import torch

def getImpFitprune(attn, start, end):
    # attn : (B, H, T, T)
    attn_headmax = attn.max(dim=1).values

    attn_self  = attn_headmax[:, start:end, start:end].sum(dim=1) / (end - start)
    attn_cross = attn_headmax[:, end:, start:end].sum(dim=1)
    importance  = attn_self * attn_cross
    return importance

def getImpFastV(attn, start=0, end=-1):
    # attn : (B, H, T, T)
    attn_headavg = attn.mean(dim=1)
    importance = attn_headavg[:, -1, start:end]

    return importance


def getl2compress(feat, start = 0, end = -1):
    return torch.norm(feat, p=2, dim=-1)[start:end]

def getVidTLDR(attn, start = 0, end = -1):
    attn = attn.mean(dim=1)
    scores = (attn * torch.log(attn)).sum(dim=2)[start:end]
    return scores

def getAnalysis(info, attn = None, feat = None, enc= False):
    if info["analysis"]["use"]:
        if enc:
            if attn is not None:
                info["analysis"]["cls"].append(attn.mean(dim=(0, 1)))
            if feat is not None:
                info["analysis"]["norm2"].append(torch.norm(feat, p=2, dim=-1))
        else:
            start, end = info["analysis"]["img_idx"]
            if attn is not None:
                info["analysis"]["fastV"].append(getImpFastV(attn, start, end))
                info["analysis"]["fitPrune"].append(getImpFitprune(attn, start, end))

            if feat is not None:
                info["analysis"]["norm2"].append(torch.norm(feat, p=2, dim=-1)[:, start:end])

    if info["compression"]["use"]:
        importance = None
        if enc:
            if attn is not None and info["compression"]["info_type"] == 0: # CLS
                importance = attn.mean(dim=(0, 1))
            elif attn is not None and info["compression"]["info_type"] == 1: # vid-TLDR
                importance = getVidTLDR(attn)
            elif feat is not None and info["compression"]["info_type"] == 2: # norm2
                importance = getl2compress(feat)

        else:
            start, end = info["analysis"]["img_idx"]
            if info["compression"]["info_type"] == 2 and attn != None: # fastV
                importance = getImpFastV(attn, start, end)
            elif info["compression"]["info_type"] == 3 and attn != None: # fitPrune
                importance = getImpFastV(attn, start, end)
            elif info["compression"]["info_type"] == 4 and feat != None: # norm2
                importance = getl2compress(feat, start, end)

        if importance is not None: info["compression"]["importance"] = importance

def resetInfo(info, compression = None):
    if info["analysis"]["use"]:
        info["analysis"]["attn"] = []
        info["analysis"]["hidden_states"] = []

        info["analysis"]["diff"] = []
        info["analysis"]["norm1"] = []
        info["analysis"]["norm2"] = []

        info["analysis"]["cls"] = []
        info["analysis"]["fastV"] = []
        info["analysis"]["fitPrune"] = []

    if compression is not None:
        info["compression"]["use"] = True

        info["compression"]["r_merge"] = compression[0][0]
        info["compression"]["r_prune"] = compression[0][1]
        info["compression"]["r_protected"] = compression[0][2]
        info["compression"]["r_half"] = compression[0][3]
        info["compression"]["proportional_attention"] = compression[0][4]
        info["compression"]["trace_source"] = compression[0][5]
        info["compression"]["info_type"] = compression[0][6]

        info["compression"]["tau_sim"] = compression[1][0]
        info["compression"]["tau_info"] = compression[1][1]
        info["compression"]["tau_size"] = compression[1][2]
        info["compression"]["pooling_type"] = compression[1][3]

        info["compression"]["mass"] = compression[2][0]



    if info["compression"]["use"]:
        info["compression"]["size"] = None
        info["compression"]["source"] = None



    # [10, 0, 0, 0, 0], [0, 0, 0, 0], [0]]
