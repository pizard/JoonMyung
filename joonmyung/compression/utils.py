import torch.nn.functional as F
import torch
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
        vis2vis_ratio  = attn_headavg[:, start:end, start:end].mean(dim=-2).sum(dim=-1)
        vis2text_ratio = attn_headavg[:, end:, start:end].mean(dim=-2).sum(dim=-1)
        vis2last_ratio = attn_headavg[:, -1, start:end].sum(dim=-1)
        result = torch.cat([vis2vis_ratio, vis2text_ratio, vis2last_ratio], dim=0)
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
        [start, end] = info_ana.get("img_idx", [None, None])

        if attn is not None: # (B, H, T, T)
            # PART I.  INFORMATION
            info_ana["vis_ratio"].append(getAttnFrom(attn, start=start, end=end, cls=cls, enc=enc))

            # PART II. VISUALIZATION
            info_ana["base"].append(unPrune(getImpBase(attn, start, end, cls=cls), source))
            info_ana["vidTLDR"].append(unPrune(getImpVidTLDR(attn, start, end), source))
            if start != None and end != None:
                info_ana["fastV"].append(getImpFastV(attn, start, end))
                info_ana["fitPrune"].append(getImpFitprune(attn, start, end))

        if feat is not None:
            info_ana["norm2"].append(unPrune(getL2Norm(feat, start, end), source))
            if info_ana.get("lm_head", None):
                logits = info_ana["lm_head"](info_ana["norm"](feat[:, -1].detach()))
                log_probs = F.log_softmax(logits, dim=-1)
                probs = log_probs.exp()
                entropy = -(probs * log_probs).sum(dim=-1)
                pred = logits.argmax(dim=-1).int()
                info_ana["logit"].append(logits)
                info_ana["entropy"].append(entropy)
                info_ana["pred"].append(pred)


    if info["compression"]["use"]:
        cls, importance = info["compression"]["cls"], None
        [start, end] = info["compression"]["img_idx"]

        if attn is not None and info["compression"]["info_type"] == 0:    # attn : BASE
            importance = getImpBase(attn, start=start, end = end, cls=cls)
        elif attn is not None and info["compression"]["info_type"] == 1:  # attn : vid-TLDR
            importance = getImpVidTLDR(attn, start=start, end = end)
        elif attn is not None and info["compression"]["info_type"] == 2:  # attn : fastV
            importance = getImpFastV(attn, start = start, end = end)
        elif attn is not None and info["compression"]["info_type"] == 3:  # attn : fitPrune
            importance = getImpFitprune(attn, start = start, end = end)
        elif feat is not None and info["compression"]["info_type"] == 4:  # feat : norm2
            importance = getL2Norm(feat, start=start, end = end)

        if importance is not None: info["compression"]["importance"] = importance

def resetInfo(info, compression = None):
    if info["analysis"]["use"]:
        # PART I. INFORMATION
        info["analysis"]["vis_ratio"] = []

        # PART II. VISUALIZATION
        info["analysis"]["base"]     = []
        info["analysis"]["vidTLDR"]  = []
        info["analysis"]["fastV"]    = []
        info["analysis"]["fitPrune"] = []

        info["analysis"]["norm2"]    = []
        info["analysis"]["pred"]    = []
        info["analysis"]["logit"]    = []
        info["analysis"]["entropy"]    = []

        info["analysis"]["img_idx"] = [None, None]


    if compression is not None:
        info["compression"]["use"] = True
        info["compression"]["info_type"]       = compression[0][0]
        info["compression"]["prune_r_layer"]   = compression[0][1]
        info["compression"]["prune_r"]         = compression[0][2]
        info["compression"]["prune_thr_layer"] = compression[0][3]
        info["compression"]["prune_thr"]       = compression[0][4]
        info["compression"]["border_remove"]   = compression[0][5]
        info["compression"]["group_num"]       = compression[0][6]



        info["use_flash_attn"] = False if info["compression"]["info_type"] in [0, 1, 2, 3] else True

        info["compression"]["tau_sim"] = compression[1][0]
        info["compression"]["tau_info"] = compression[1][1]
        info["compression"]["tau_size"] = compression[1][2]
        info["compression"]["pooling_type"] = compression[1][3]
        info["compression"]["mass"] = compression[2][0]

    if info["compression"]["use"]:
        info["compression"]["size"] = None
        info["compression"]["source"] = None
        info["compression"]["img_idx"] = [None, None]

#
#
# def saveResult(result_sep, result_all):
#     em, f1 = result_all["overall"]["list_em"], result_all["overall"]["list_f1"]
#     mod_image, mod_table, mod_text = result_all["modalities"]["image"]["list_f1"], result_all["modalities"]["table"]["list_f1"], result_all["modalities"]["text"]["list_f1"]
#     hop_single, hop_multi = result_all["hop_types"]["Single-hop"]["list_f1"], result_all["hop_types"]["Multi-hop"]["list_f1"]
#     drop_ratio_enc = sum([v["drop_ratio_enc"].item() for v in result_sep.values()]) / len(result_sep)
#     drop_ratio_dec = sum([v["drop_ratio_dec"].item() for v in result_sep.values()]) / len(result_sep)
#
#     results = {"em" : em, "f1" : f1, "mod_image" : mod_image, "mod_table" : mod_table, "mod_text" : mod_text, "hop_single": hop_single, "hop_multi": hop_multi,
#                "drop_ratio_enc" : drop_ratio_enc, "drop_ratio_dec" : drop_ratio_dec}




