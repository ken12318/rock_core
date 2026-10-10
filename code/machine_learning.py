"""
Train the rock-core porosity/permeability model used by the Django site.

Expected annotation file columns:
    image_path      relative or absolute image path
    porosity        measured or simulated porosity value
    permeability    measured or simulated permeability value
    rock_type       optional lithology label, enables type-aware training

Example:
    python code/machine_learning.py --data data/trains.xlsx --image-dir data/images --epochs 50
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_app.modeling import DEVICE, RockHybridModel, preprocess_image, train_transform, val_transform


REQUIRED_COLUMNS = {"image_path", "porosity", "permeability"}
DEFAULT_OUTPUT = ROOT / "code" / "best_rock_model.pth"


@dataclass
class TrainConfig:
    data: str
    image_dir: str | None
    output: str
    epochs: int
    batch_size: int
    lr: float
    patience: int
    val_size: float
    seed: int


class RockCoreDataset(Dataset):
    def __init__(self, frame, image_dir, scaler_poro, scaler_perm, rock_classes, transform):
        self.frame = frame.reset_index(drop=True)
        self.image_dir = Path(image_dir) if image_dir else None
        self.scaler_poro = scaler_poro
        self.scaler_perm = scaler_perm
        self.rock_classes = list(rock_classes)
        self.transform = transform

    def __len__(self):
        return len(self.frame)

    def resolve_image_path(self, value):
        path = Path(str(value))
        if path.is_absolute():
            return path
        if self.image_dir:
            return self.image_dir / path
        return ROOT / path

    def __getitem__(self, index):
        row = self.frame.iloc[index]
        image_path = self.resolve_image_path(row["image_path"])
        image = Image.open(image_path).convert("RGB")
        image = preprocess_image(image)
        image = self.transform(image)

        porosity = self.scaler_poro.transform([[float(row["porosity"])]])[0][0]
        permeability_log = np.log(max(float(row["permeability"]), 1e-6))
        permeability = self.scaler_perm.transform([[permeability_log]])[0][0]
        targets = torch.tensor([porosity, permeability], dtype=torch.float32)

        rock_type = str(row.get("rock_type", "未知岩性"))
        if rock_type not in self.rock_classes:
            rock_type = self.rock_classes[0]
        rock_code = torch.tensor(self.rock_classes.index(rock_type), dtype=torch.long)
        return image, rock_code, targets


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def read_annotations(path):
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    else:
        frame = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"标注文件缺少字段：{', '.join(sorted(missing))}")
    frame = frame.dropna(subset=list(REQUIRED_COLUMNS)).copy()
    if "rock_type" not in frame.columns:
        frame["rock_type"] = "未知岩性"
    frame["rock_type"] = frame["rock_type"].fillna("未知岩性").astype(str)
    return frame


def split_frame(frame, val_size, seed):
    stratify = frame["rock_type"] if frame["rock_type"].nunique() > 1 else None
    return train_test_split(frame, test_size=val_size, random_state=seed, stratify=stratify)


def build_scalers(frame):
    scaler_poro = StandardScaler()
    scaler_perm = StandardScaler()
    scaler_poro.fit(frame["porosity"].astype(float).to_numpy().reshape(-1, 1))
    permeability = np.log(frame["permeability"].astype(float).clip(lower=1e-6).to_numpy()).reshape(-1, 1)
    scaler_perm.fit(permeability)
    return scaler_poro, scaler_perm


def train_epoch(model, loader, optimizer, criterion):
    model.train()
    total_loss = 0.0
    for images, rock_codes, targets in loader:
        images = images.to(DEVICE)
        rock_codes = rock_codes.to(DEVICE)
        targets = targets.to(DEVICE)

        optimizer.zero_grad()
        porosity_pred, permeability_pred = model(images, rock_codes)
        preds = torch.stack([porosity_pred, permeability_pred], dim=1)
        loss = criterion(preds, targets)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * images.size(0)
    return total_loss / max(len(loader.dataset), 1)


def evaluate(model, loader, criterion, scaler_poro, scaler_perm):
    model.eval()
    total_loss = 0.0
    y_true = []
    y_pred = []
    with torch.no_grad():
        for images, rock_codes, targets in loader:
            images = images.to(DEVICE)
            rock_codes = rock_codes.to(DEVICE)
            targets = targets.to(DEVICE)

            porosity_pred, permeability_pred = model(images, rock_codes)
            preds = torch.stack([porosity_pred, permeability_pred], dim=1)
            loss = criterion(preds, targets)
            total_loss += loss.item() * images.size(0)
            y_true.append(targets.cpu().numpy())
            y_pred.append(preds.cpu().numpy())

    y_true = np.vstack(y_true)
    y_pred = np.vstack(y_pred)
    true_poro = scaler_poro.inverse_transform(y_true[:, [0]]).ravel()
    pred_poro = scaler_poro.inverse_transform(y_pred[:, [0]]).ravel()
    true_perm = np.exp(scaler_perm.inverse_transform(y_true[:, [1]]).ravel())
    pred_perm = np.exp(scaler_perm.inverse_transform(y_pred[:, [1]]).ravel())

    return {
        "loss": total_loss / max(len(loader.dataset), 1),
        "porosity_mae": mean_absolute_error(true_poro, pred_poro),
        "permeability_mae": mean_absolute_error(true_perm, pred_perm),
        "porosity_rmse": mean_squared_error(true_poro, pred_poro, squared=False),
        "permeability_rmse": mean_squared_error(true_perm, pred_perm, squared=False),
        "porosity_r2": r2_score(true_poro, pred_poro),
        "permeability_r2": r2_score(true_perm, pred_perm),
    }


def save_checkpoint(path, model, scaler_poro, scaler_perm, rock_classes, metrics, config):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "architecture": "rock_hybrid",
            "model_state_dict": model.state_dict(),
            "scaler_poro": scaler_poro,
            "scaler_perm": scaler_perm,
            "rock_classes": list(rock_classes),
            "metrics": metrics,
            "config": asdict(config),
        },
        path,
    )


def train(config):
    set_seed(config.seed)
    frame = read_annotations(config.data)
    train_frame, val_frame = split_frame(frame, config.val_size, config.seed)
    scaler_poro, scaler_perm = build_scalers(train_frame)
    rock_classes = sorted(frame["rock_type"].unique().tolist())

    train_ds = RockCoreDataset(train_frame, config.image_dir, scaler_poro, scaler_perm, rock_classes, train_transform)
    val_ds = RockCoreDataset(val_frame, config.image_dir, scaler_poro, scaler_perm, rock_classes, val_transform)
    train_loader = DataLoader(train_ds, batch_size=config.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=config.batch_size, shuffle=False, num_workers=0)

    model = RockHybridModel(num_rock_types=len(rock_classes)).to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)
    criterion = torch.nn.SmoothL1Loss()

    best_loss = float("inf")
    best_metrics = {}
    wait = 0
    for epoch in range(1, config.epochs + 1):
        train_loss = train_epoch(model, train_loader, optimizer, criterion)
        metrics = evaluate(model, val_loader, criterion, scaler_poro, scaler_perm)
        metrics["train_loss"] = train_loss
        metrics["epoch"] = epoch
        scheduler.step(metrics["loss"])

        print(
            f"Epoch {epoch:03d} | train_loss={train_loss:.4f} | "
            f"val_loss={metrics['loss']:.4f} | porosity_mae={metrics['porosity_mae']:.3f} | "
            f"permeability_mae={metrics['permeability_mae']:.3f}"
        )

        if metrics["loss"] < best_loss:
            best_loss = metrics["loss"]
            best_metrics = metrics
            save_checkpoint(config.output, model, scaler_poro, scaler_perm, rock_classes, best_metrics, config)
            wait = 0
        else:
            wait += 1
            if wait >= config.patience:
                print(f"Early stopping at epoch {epoch}.")
                break

    metrics_path = Path(config.output).with_suffix(".metrics.json")
    metrics_path.write_text(json.dumps(best_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved model: {config.output}")
    print(f"Saved metrics: {metrics_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Train rock-core porosity/permeability model.")
    parser.add_argument("--data", required=True, help="Excel/CSV annotation file.")
    parser.add_argument("--image-dir", default=None, help="Directory for relative image paths.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output checkpoint path.")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--val-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    return TrainConfig(**vars(args))


if __name__ == "__main__":
    train(parse_args())
