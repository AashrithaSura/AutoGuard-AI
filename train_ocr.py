from __future__ import annotations

import argparse
import csv
import json
import random
import re
from pathlib import Path

import cv2
import easyocr
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from easyocr.recognition import AlignCollate
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parent

def normalize(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())

def edit_distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j - 1] + (ca != cb)))
        row = current
    return row[-1]

class PlateCropDataset(Dataset):
    def __init__(self, manifest: Path, data_root: Path, augment: bool = False):
        self.data_root = data_root
        self.augment = augment
        with manifest.open(newline="", encoding="utf-8-sig") as stream:
            self.rows = list(csv.DictReader(stream))
    def __len__(self):
        return len(self.rows)
    def __getitem__(self, index):
        row = self.rows[index]
        image_path = self.data_root / row["crop_path"]
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise RuntimeError(f"Could not read OCR crop: {image_path}")
        if self.augment:
            if random.random() < 0.35:
                alpha = random.uniform(0.75, 1.25)
                beta = random.uniform(-18, 18)
                image = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
            if random.random() < 0.20:
                angle = random.uniform(-3.0, 3.0)
                h, w = image.shape
                matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
                image = cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            if random.random() < 0.20:
                image = cv2.GaussianBlur(image, (3, 3), random.uniform(0.3, 1.0))
            if random.random() < 0.15:
                noise = np.random.normal(0, random.uniform(2, 8), image.shape).astype(np.float32)
                image = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        return Image.fromarray(image, "L"), normalize(row["plate_text"])

def batch_collate(batch):
    images, texts = zip(*batch)
    return list(images), list(texts)

def make_loader(dataset, batch_size, shuffle, height, width):
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, num_workers=0,
        collate_fn=lambda batch: (AlignCollate(imgH=height, imgW=width, keep_ratio_with_pad=True)([item[0] for item in batch]), [item[1] for item in batch]))

def validate(model, converter, loader, device):
    model.eval(); exact=0; errors=0; characters=0; count=0
    with torch.no_grad():
        for images, labels in loader:
            images=images.to(device); batch_size=images.size(0)
            dummy=torch.zeros((batch_size, 27), dtype=torch.long, device=device)
            logits=model(images,dummy)
            sizes=torch.IntTensor([logits.size(1)]*batch_size)
            decoded=converter.decode_greedy(logits.argmax(2).reshape(-1).cpu().numpy(),sizes)
            for prediction, truth in zip(decoded,labels):
                prediction=normalize(prediction); truth=normalize(truth)
                exact += prediction == truth; errors += edit_distance(prediction,truth)
                characters += max(1,len(truth)); count += 1
    return {"exact_match_accuracy":exact/max(count,1),"character_error_rate":errors/max(characters,1),"samples":count}

def main():
    parser=argparse.ArgumentParser(description="Fine-tune EasyOCR’s pretrained English recognizer on plate crops.")
    parser.add_argument("--data-root",default="data/prepared_corrected",help="Prepared dataset directory containing the ocr/ folder.")
    parser.add_argument("--train-csv",default="data/prepared_corrected/ocr/train.csv")
    parser.add_argument("--val-csv",default="data/prepared_corrected/ocr/val.csv")
    parser.add_argument("--epochs",type=int,default=12)
    parser.add_argument("--batch",type=int,default=16)
    parser.add_argument("--height",type=int,default=64)
    parser.add_argument("--width",type=int,default=512)
    parser.add_argument("--lr-features",type=float,default=1e-5)
    parser.add_argument("--lr-head",type=float,default=5e-5)
    parser.add_argument("--patience",type=int,default=3)
    parser.add_argument("--resume-from",default=None)
    parser.add_argument("--checkpoint",default="models/plate_ocr.pth",help="Output checkpoint path.")
    parser.add_argument("--history-output",default="reports/ocr_training_history.json")
    parser.add_argument("--threads",type=int,default=0,help="CPU threads; 0 leaves PyTorch default.")
    args=parser.parse_args()
    random.seed(42); np.random.seed(42); torch.manual_seed(42)
    if args.threads:
        torch.set_num_threads(args.threads)
    device=torch.device("cpu")
    train_set=PlateCropDataset(ROOT/args.train_csv,ROOT/args.data_root,augment=True)
    val_set=PlateCropDataset(ROOT/args.val_csv,ROOT/args.data_root,augment=False)
    train_loader=make_loader(train_set,args.batch,True,args.height,args.width)
    val_loader=make_loader(val_set,args.batch,False,args.height,args.width)
    reader=easyocr.Reader(["en"],gpu=False,detector=False,recognizer=True,quantize=False)
    model=reader.recognizer.to(device)
    converter=reader.converter
    checkpoint=ROOT/args.checkpoint
    print(json.dumps({"train_rows":len(train_set),"val_rows":len(val_set),"checkpoint":str(checkpoint)}),flush=True)
    if args.resume_from:
        resume_path=ROOT/args.resume_from
        if not resume_path.is_file(): raise SystemExit(f"Resume checkpoint not found: {resume_path}")
        model.load_state_dict(torch.load(resume_path,map_location=device,weights_only=True))
    invalid=sorted({char for row in train_set.rows+val_set.rows for char in normalize(row["plate_text"])}-set(converter.dict))
    if invalid: raise SystemExit(f"Labels contain characters outside EasyOCR vocabulary: {invalid}")
    optimizer=torch.optim.AdamW([
        {"params":model.FeatureExtraction.parameters(),"lr":args.lr_features},
        {"params":model.SequenceModeling.parameters(),"lr":args.lr_head},
        {"params":model.Prediction.parameters(),"lr":args.lr_head},
    ],weight_decay=1e-4)
    criterion=nn.CTCLoss(blank=0,zero_infinity=True)
    checkpoint.parent.mkdir(parents=True,exist_ok=True)
    baseline=validate(model,converter,val_loader,device)
    best_cer=baseline["character_error_rate"]
    print(json.dumps({"resume_checkpoint":args.resume_from or "pretrained baseline","validation_baseline":baseline}),flush=True)
    history=[]; stale=0


    for epoch in range(1,args.epochs+1):
        model.train(); total_loss=0.0; batches=0
        for images,labels in train_loader:
            images=images.to(device); batch_size=images.size(0)
            targets,target_lengths=converter.encode(labels,batch_max_length=30)
            targets=targets.to(device=device,dtype=torch.long); target_lengths=target_lengths.to(device=device,dtype=torch.long)
            dummy=torch.zeros((batch_size,31),dtype=torch.long,device=device)
            logits=model(images,dummy)
            input_lengths=torch.full((batch_size,),logits.size(1),dtype=torch.long,device=device)
            loss=criterion(logits.log_softmax(2).permute(1,0,2),targets,input_lengths,target_lengths)
            if not torch.isfinite(loss): continue
            optimizer.zero_grad(set_to_none=True); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),5.0)
            optimizer.step(); total_loss+=float(loss.detach()); batches+=1
        val_metrics=validate(model,converter,val_loader,device)
        record={"epoch":epoch,"train_ctc_loss":total_loss/max(batches,1),"validation":val_metrics}
        history.append(record); print(json.dumps(record),flush=True)
        if val_metrics["character_error_rate"]<best_cer:
            best_cer=val_metrics["character_error_rate"]; stale=0
            torch.save(model.state_dict(),checkpoint)
        else:
            stale+=1
        if stale>=args.patience:
            print(f"Early stopping after {args.patience} validation checks without CER improvement.",flush=True); break
    (ROOT/"reports").mkdir(exist_ok=True)
    (ROOT/args.history_output).parent.mkdir(parents=True,exist_ok=True)
    (ROOT/args.history_output).write_text(json.dumps(history,indent=2),encoding="utf-8")
    print(f"Best validation checkpoint: {checkpoint}")
    print(f"Best validation character error rate: {best_cer:.4f}")

if __name__=="__main__": main()






