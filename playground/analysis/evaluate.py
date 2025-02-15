import os

from joonmyung.compression.apply import apply_patch
from playground.script.utils import getCompressionParser

os.environ["CUDA_VISIBLE_DEVICES"] = "4"
from joonmyung.analysis import JDataset, JModel, ZeroShotInference
from joonmyung.meta_data import data2path
from joonmyung.utils import read_classnames
from joonmyung.log import AverageMeter
from joonmyung.metric import accuracy
from tqdm import tqdm
import torch



root_path, dataset_name, batch_size, device, debug = "/hub_data1/joonmyung/weights", "imagenet", 100, 'cuda', True
classnames = read_classnames("/hub_data1/joonmyung/data/imagenet/classnames.txt")
num_classes, model_name, model_number = len(classnames), "ViT-B/16", 2

modelMaker = JModel(num_classes, root_path, device=device)
model = modelMaker.getModel(model_number, model_name)
data_path, num_classes, _, _ = data2path(dataset_name)
dataset = JDataset(data_path, dataset_name, transform_type=2, device=device)
dataloader = dataset.getAllItems(batch_size)

model = ZeroShotInference(model, classnames, prompt = "a photo of a {}.", device = device)
compression = [[1, 0, 10, 0, 1, 1], [1, 10, 25, 1], [0]]
apply_patch(model.model, compression)
result = {"acc1" : AverageMeter(), "acc5" : AverageMeter()}
args = getCompressionParser()

for compression in args.compression:
    for r_merge in args.r_merge:
        with torch.no_grad():
            for image, labels in tqdm(dataloader):
                B = image.shape[0]
                image, labels = image.to(device), labels.to(device)
                logits = model(image)
                acc1, acc5 = accuracy(logits, labels, topk=(1, 5))
                result["acc1"].update(acc1.item(), n=B) # 68.2
                result["acc5"].update(acc5.item(), n=B)
print(1)