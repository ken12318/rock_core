import base64
import io

import numpy as np
import torch
from django.conf import settings
from PIL import Image

from .modeling import DEVICE, RockHybridModel, RockPrecisionModel, RockTypeAwareModel, fallback_scalers, preprocess_image, val_transform


_model = None
_scaler_poro, _scaler_perm = fallback_scalers()
_rock_classes = []
_model_uses_rock_type = False
_model_has_generic_mode = False
_model_demo_mode = False
_load_error = None


def get_model():
    global _model, _load_error, _model_demo_mode, _model_has_generic_mode, _model_uses_rock_type, _rock_classes, _scaler_poro, _scaler_perm
    if _model is not None:
        return _model

    try:
        checkpoint = torch.load(settings.MODEL_PATH, map_location=DEVICE)
        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            _rock_classes = checkpoint.get("rock_classes", [])
            architecture = checkpoint.get("architecture")
            _model_has_generic_mode = architecture == "rock_hybrid"
            _model_uses_rock_type = architecture in {"rock_type_aware", "rock_hybrid"} and bool(_rock_classes)
            if architecture == "rock_hybrid":
                model = RockHybridModel(num_rock_types=len(_rock_classes)).to(DEVICE)
            elif _model_uses_rock_type:
                model = RockTypeAwareModel(num_rock_types=len(_rock_classes)).to(DEVICE)
            else:
                model = RockPrecisionModel().to(DEVICE)
            model.load_state_dict(checkpoint["model_state_dict"])
            _scaler_poro = checkpoint.get("scaler_poro", _scaler_poro)
            _scaler_perm = checkpoint.get("scaler_perm", _scaler_perm)
            _model_demo_mode = bool(checkpoint.get("metrics", {}).get("demo"))
        else:
            model = RockPrecisionModel().to(DEVICE)
            model.load_state_dict(checkpoint)
        model.eval()
        _model = model
        return _model
    except Exception as exc:
        _load_error = exc
        raise RuntimeError(f"模型加载失败：{exc}") from exc


def get_available_rock_types():
    try:
        get_model()
    except RuntimeError:
        return []
    if _model_has_generic_mode and _rock_classes:
        return ["通用模型"] + list(_rock_classes)
    return list(_rock_classes)


def get_model_context(rock_type):
    get_model()
    specialized = _model_uses_rock_type and rock_type not in {None, "", "通用模型", "未知岩性"}
    return {
        "label": f"{rock_type}专用模型" if specialized else "通用模型",
        "is_demo": _model_demo_mode,
    }


def encode_rock_type(rock_type):
    if rock_type in {None, "", "通用模型", "未知岩性"}:
        return None
    if not _model_uses_rock_type:
        return None
    if rock_type not in _rock_classes:
        raise ValueError(f"当前模型不支持岩性：{rock_type}，可选岩性：{', '.join(_rock_classes)}")
    return torch.tensor([_rock_classes.index(rock_type)], dtype=torch.long, device=DEVICE)


def predict_properties(image_bytes, rock_type=None):
    image = Image.open(io.BytesIO(image_bytes))
    tensor = val_transform(preprocess_image(image)).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        model = get_model()
        rock_type_code = encode_rock_type(rock_type)
        if rock_type_code is None:
            porosity_raw, permeability_raw = model(tensor)
        else:
            porosity_raw, permeability_raw = model(tensor, rock_type_code)

    porosity = _scaler_poro.inverse_transform(porosity_raw.cpu().numpy().reshape(-1, 1))[0][0]
    permeability_log = _scaler_perm.inverse_transform(permeability_raw.cpu().numpy().reshape(-1, 1))[0][0]
    permeability = np.exp(permeability_log)
    if _model_demo_mode:
        porosity, permeability = apply_demo_texture_adjustment(image, porosity, permeability)
    return round(float(porosity), 2), round(float(permeability), 2)


def apply_demo_texture_adjustment(image, porosity, permeability):
    sample = np.asarray(image.convert("RGB").resize((64, 64)), dtype=np.float32) / 255.0
    brightness = float(sample.mean())
    texture = float(sample.std())
    porosity_delta = (brightness - 0.45) * 2.4 + (texture - 0.18) * 5.5
    permeability_factor = np.exp((brightness - 0.45) * 0.7 + (texture - 0.18) * 2.2)
    adjusted_porosity = np.clip(float(porosity) + porosity_delta, 1.0, 28.0)
    adjusted_permeability = np.clip(float(permeability) * permeability_factor, 0.3, 350.0)
    return adjusted_porosity, adjusted_permeability


def make_thumbnail(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((140, 140))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=86)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
