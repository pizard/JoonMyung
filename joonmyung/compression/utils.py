import torch.nn.functional as F
import torch
import os

from joonmyung.compression.compression import needAttn


def getImpBase(attn, start=None, end=None, cls=False):
    attn_base = attn[:, :, 0].mean(dim=1) if cls else attn.mean(dim=(1,2))
    return attn_base[:, start:end]

def getImpFitprune(attn, start=None, end=None):
    attn_headmax = attn.max(dim=1).values
    attn_self = attn_headmax[:, start:end, start:end].mean(dim=1)
    attn_cross = attn_headmax[:, end:, start:end].mean(dim=1)
    importance  = attn_self * attn_cross
    return importance

def getImpFastV(attn, start=None, end=None):
    attn_headavg = attn.mean(dim=1)
    importance = attn_headavg[:, -1, start:end]
    return importance

def getL2Norm(feat, start = None, end = None):
    return torch.norm(feat, p=2, dim=-1)[:, start:end]

def getComplexity(feat, start=None, end=None):
    feat_norm = F.normalize(feat, dim=-1)[:, start:end]
    return 1 - (feat_norm @ feat_norm.transpose(-1, -2)).mean(dim=-1)

def getImpVidTLDR(attn, start = None, end = None):
    attn_headavg = attn.mean(dim=1) # B T T
    importance = -(attn_headavg * torch.log(attn_headavg)).mean(dim=1)[start:end]
    return importance

# def getDivPrune(feat, r_keep):
#     feat_norm = feat / feat.norm(dim=-1, keepdim=True)
#     feat_sim = 1 - torch.mm(feat_norm, feat_norm.t())
#
#     s = torch.empty(r_keep, dtype=torch.long, device=feat.device)
#     for i in range(r_keep):
#         if i == 0:
#             m2 = feat_sim  # (576, 576)
#         else:
#             m2 = torch.index_select(feat_sim, 0, torch.index_select(s, 0, torch.arange(0, i, device=cosine_matrix.device)))  # (1, 576)
#
#         if i == 0:
#             scores = torch.topk(m2, 2, dim=0, largest=False).values[1, :]  # 576
#         else:
#             scores = torch.min(m2, dim=0).values  # 576
#
#         phrase_to_add_idx = torch.argmax(scores)  # 234
#         s[i] = phrase_to_add_idx
#     return s


def unPrune(values, source):
    if source == None:
        return values
    result = torch.zeros_like(source, device=source.device, dtype=values.dtype)
    result[source] = values
    return result



def getAttnFrom(attn, start=None, end=None, cls=False, enc=False):
    attn_headavg = attn.mean(dim=1)
    if not enc and attn.shape[2] != 1:
        vis2textPre_ratio = attn_headavg[:, :start, start:end].mean(dim=-2).sum(dim=-1)
        vis2vis_ratio  = attn_headavg[:, start:end, start:end].mean(dim=-2).sum(dim=-1)
        vis2textPost_ratio = attn_headavg[:, end:-1, start:end].mean(dim=-2).sum(dim=-1)
        vis2last_ratio = attn_headavg[:, -1, start:end].sum(dim=-1)
        result = torch.cat([vis2textPre_ratio, vis2vis_ratio, vis2textPost_ratio, vis2last_ratio], dim=0)
    elif cls:
        patch2cls_ratio   = attn_headavg[:, 1:, 1:].mean(dim=-2).sum(dim=-1)
        patch2patch_ratio = attn_headavg[:,  0, 1:].sum(dim=-1)
        result = torch.cat([patch2cls_ratio, patch2patch_ratio], dim=0)
    else:
        result = None

    return result

def getAnalysis(info, attn = None, feat = None, enc= False):
    if attn is not None and len(attn.shape) == 3: attn = attn[None]
    if feat is not None and len(feat.shape) == 2: feat = feat[None]


    if info["analysis"]["use"]:
        info_ana = info["analysis"]
        cls, source, group_num = info_ana["cls"], info["compression"].get("source", None), info["compression"].get("group_num", 1)
        if group_num > 1: source = source.unsqueeze(-1).expand(-1, -1, group_num).reshape(source.shape[0], -1)
        [i_start, i_end, i_len] = info_ana["img_idx"]

        if attn is not None: # (B, H, T, T)
            attn = attn.to(torch.float32)
            # PART I.  INFORMATION
            info_ana["vis_attn_ratio"].append(getAttnFrom(attn, start=i_start, end=i_end, cls=cls, enc=enc))
            if i_start:
                # [TXT_PRE, VIS, TXT_POST, EOS]
                attn_temp = attn.mean(dim=(0,1)) # (2551, 2551)
                attn_alloc_full = torch.stack([attn.mean(dim=(0, 1))[-1][:i_start].sum(dim=-1), attn.mean(dim=(0, 1))[-1][i_start:i_end].sum(dim=-1), attn.mean(dim=(0, 1))[-1][i_end:i_len-1].sum(dim=-1), attn.mean(dim=(0, 1))[-1][i_len-1:].sum(dim=-1)])
                attn_alloc_token = torch.stack([attn.mean(dim=(0, 1))[-1][:i_start].mean(dim=-1), attn.mean(dim=(0, 1))[-1][i_start:i_end].mean(dim=-1), attn.mean(dim=(0, 1))[-1][i_end:i_len-1].mean(dim=-1), attn.mean(dim=(0, 1))[-1][i_len-1:].mean(dim=-1)]).to(torch.float32)
                info_ana["eos_attn_alloc"].append(attn_alloc_full)
                info_ana["eos_attn_effi"].append(attn_alloc_token / attn_alloc_token[1])

            # PART II. VISUALIZATION
            info_ana["base"].append(unPrune(getImpBase(attn, i_start, i_end, cls=cls), source))
            info_ana["vidTLDR"].append(unPrune(getImpVidTLDR(attn, i_start, i_end), source))
            if i_start != None and i_end != None:
                info_ana["fastV"].append(getImpFastV(attn, i_start, i_end))
                info_ana["fitPrune"].append(getImpFitprune(attn, i_start, i_end))

        if feat is not None:
            info_ana["norm2"].append(unPrune(getL2Norm(feat, i_start, i_end), source))
            if info_ana.get("lm_head", None):
                logits = info_ana["lm_head"](info_ana["norm"](feat[-1].detach()))
                log_probs = F.log_softmax(logits, dim=-1)
                probs = log_probs.exp()
                entropy = -(probs * log_probs).sum(dim=-1)
                pred = logits.argmax(dim=-1).int()
                info_ana["logit"].append(logits)
                info_ana["entropy"].append(entropy)
                info_ana["pred"].append(pred)
            if i_start == None: # ENCODER
                feat_norm = F.normalize(feat.to(torch.float32), dim=-1) # ↑ : 단순
                complexity = 1 - (feat_norm @ feat_norm.transpose(-1, -2)).mean() # ↑ : 복잡
                info_ana["complexity"].append(complexity)

    if info["compression"]["use"]:
        cls, importance = info["compression"]["cls"], None
        [i_start, i_end] = info["compression"]["img_idx"]

        if attn is not None and info["compression"]["info_type"] == 1:    # attn : BASE
            importance = getImpBase(attn, start=i_start, end = i_end, cls=cls)
        elif attn is not None and info["compression"]["info_type"] == 2:  # attn : vid-TLDR
            importance = getImpVidTLDR(attn, start=i_start, end = i_end)
        elif attn is not None and info["compression"]["info_type"] == 3:  # attn : fastV
            importance = getImpFastV(attn, start = i_start, end = i_end)
        elif attn is not None and info["compression"]["info_type"] == 4:  # attn : fitPrune
            importance = getImpFitprune(attn, start = i_start, end = i_end)
        elif feat is not None and info["compression"]["info_type"] == 5:  # feat : norm2
            importance = getL2Norm(feat, start=i_start, end = i_end)
        elif feat is not None and info["compression"]["info_type"] == 6:  # feat : redundancy
            importance = getComplexity(feat, start=i_start, end = i_end)

        if importance is not None: info["compression"]["importance"] = importance

        # if info["source"] is None: info["source"] = torch.ones((B * (T // info["group_num"]) ), dtype=torch.bool, device=x.device)
        # if info["size"] is None: info["size"] = torch.ones_like(x[..., 0, None]) # (B, T, 1)


def resetInfo(info, compression = None, ret=None):
    if info["analysis"]["use"]:
        # PART I. INFORMATION
        info["analysis"]["vis_attn_ratio"]  = []
        info["analysis"]["eos_attn_alloc"] = []
        info["analysis"]["eos_attn_effi"]  = []

        # PART II. VISUALIZATION
        info["analysis"]["base"]     = []
        info["analysis"]["vidTLDR"]  = []
        info["analysis"]["fastV"]    = []
        info["analysis"]["fitPrune"] = []

        info["analysis"]["norm2"]    = []
        info["analysis"]["pred"]     = []
        info["analysis"]["logit"]    = []
        info["analysis"]["entropy"]  = []

        info["analysis"]["white_mask"] = None
        info["analysis"]["img_idx"]    = [None, None, None]

        # PART III. DIFFICULTY
        info["analysis"]["complexity"] = []

    if compression is not None:
        info["compression"]["use"] = True
        info["compression"]["info_type"]       = compression[0]
        info["compression"]["prune_r_layer"]   = compression[1]
        info["compression"]["prune_r"]         = compression[2]
        info["compression"]["prune_thr_layer"] = compression[3]
        info["compression"]["prune_thr"]       = compression[4]
        info["compression"]["group_num"]       = compression[5] if compression[5] else 1
        info["compression"]["prePrune"]        = compression[6]
        info["compression"]["propAttn"]        = compression[7]


        info["compression"]["tau_sim"]      = 0
        info["compression"]["tau_info"]     = 0
        info["compression"]["tau_size"]     = 0
        info["compression"]["pooling_type"] = 0
        info["compression"]["mass"]         = 0
        info["compression"]["need_attn"] = [needAttn(info, l) for l in range(50)]

    if info["compression"]["use"]:
        info["compression"]["size"] = None
        info["compression"]["source"] = None
        info["compression"]["img_idx"] = [None, None]

    if ret is not None:
        if ret:
            white = torch.load(f"/hub_data1/joonmyung/conference/2026AAAI/m3docrag/temp/white_ret_pix.pt", weights_only=True)
        else:
            white = torch.load(f"/hub_data1/joonmyung/conference/2026AAAI/m3docrag/temp/white_qa_pix.pt", weights_only=True)
        info["temp"]["white"] = white

def grouping(x, group_num):
    D = x.shape[-1]
    return x.reshape(-1, group_num, D) if len(x.shape) == 2 else x.reshape(x.shape[0], -1, group_num, D)

def pruning(x, mask, prop=False):
    D = x.shape[-1] # T, D

    remain = x.masked_select(mask.reshape(-1, 1, 1)).view(-1, D)
    if prop:
        remain = torch.cat([remain, x.masked_select(~mask.reshape(-1, 1, 1)).view(-1, D).mean(dim=0, keepdim=True)], dim=0)

    return remain