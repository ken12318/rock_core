import cv2
import numpy as np
import torch
from PIL import Image
from sklearn.preprocessing import StandardScaler
from torchvision import transforms


IMAGE_SIZE = 224
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class RockPrecisionModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.res_block1 = self._make_res_block(3, 32)
        self.res_block2 = self._make_res_block(32, 64)
        self.res_block3 = self._make_res_block(64, 128)
        self.res_block4 = self._make_res_block(128, 256)
        self.global_pool = torch.nn.AdaptiveAvgPool2d(1)
        self.fc = torch.nn.Sequential(
            torch.nn.Dropout(0.2),
            torch.nn.Linear(256, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64, 2),
        )

    def _make_res_block(self, in_channels, out_channels):
        return torch.nn.Sequential(
            torch.nn.Conv2d(in_channels, out_channels, 3, padding=1),
            torch.nn.BatchNorm2d(out_channels),
            torch.nn.ReLU(),
            torch.nn.Conv2d(out_channels, out_channels, 3, padding=1),
            torch.nn.BatchNorm2d(out_channels),
            torch.nn.ReLU(),
        )

    def forward(self, x):
        x = self.res_block1(x)
        x = self.res_block2(x)
        x = self.res_block3(x)
        x = self.res_block4(x)
        x = self.global_pool(x).flatten(1)
        output = self.fc(x)
        return output[:, 0], output[:, 1]


class RockTypeAwareModel(torch.nn.Module):
    def __init__(self, num_rock_types, embedding_dim=16):
        super().__init__()
        self.backbone = RockPrecisionModel()
        self.backbone.fc = torch.nn.Identity()
        self.rock_embedding = torch.nn.Embedding(num_rock_types, embedding_dim)
        self.head = torch.nn.Sequential(
            torch.nn.Dropout(0.25),
            torch.nn.Linear(256 + embedding_dim, 96),
            torch.nn.ReLU(),
            torch.nn.Linear(96, 2),
        )

    def forward(self, image, rock_type_code):
        x = self.backbone.res_block1(image)
        x = self.backbone.res_block2(x)
        x = self.backbone.res_block3(x)
        x = self.backbone.res_block4(x)
        image_feature = self.backbone.global_pool(x).flatten(1)
        rock_feature = self.rock_embedding(rock_type_code)
        output = self.head(torch.cat([image_feature, rock_feature], dim=1))
        return output[:, 0], output[:, 1]


class RockHybridModel(torch.nn.Module):
    def __init__(self, num_rock_types, embedding_dim=16):
        super().__init__()
        self.feature_extractor = RockPrecisionModel()
        self.feature_extractor.fc = torch.nn.Identity()
        self.generic_head = torch.nn.Sequential(
            torch.nn.Dropout(0.2),
            torch.nn.Linear(256, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64, 2),
        )
        self.rock_embedding = torch.nn.Embedding(num_rock_types, embedding_dim)
        self.type_head = torch.nn.Sequential(
            torch.nn.Dropout(0.25),
            torch.nn.Linear(256 + embedding_dim, 96),
            torch.nn.ReLU(),
            torch.nn.Linear(96, 2),
        )

    def extract_features(self, image):
        x = self.feature_extractor.res_block1(image)
        x = self.feature_extractor.res_block2(x)
        x = self.feature_extractor.res_block3(x)
        x = self.feature_extractor.res_block4(x)
        return self.feature_extractor.global_pool(x).flatten(1)

    def forward(self, image, rock_type_code=None):
        image_feature = self.extract_features(image)
        if rock_type_code is None:
            output = self.generic_head(image_feature)
        else:
            rock_feature = self.rock_embedding(rock_type_code)
            output = self.type_head(torch.cat([image_feature, rock_feature], dim=1))
        return output[:, 0], output[:, 1]


train_transform = transforms.Compose(
    [
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomVerticalFlip(p=0.5),
        transforms.RandomRotation(degrees=8),
        transforms.ColorJitter(brightness=0.12, contrast=0.12, saturation=0.08),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]
)

val_transform = transforms.Compose(
    [
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]
)


def preprocess_image(image):
    if image.mode != "RGB":
        image = image.convert("RGB")

    img = np.array(image)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    img = cv2.filter2D(img, -1, np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]]))
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    l_channel = cv2.equalizeHist(l_channel)
    lab = cv2.merge((l_channel, a_channel, b_channel))
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return Image.fromarray(img)


def fallback_scalers():
    porosity_scaler = StandardScaler()
    permeability_scaler = StandardScaler()
    porosity_scaler.fit(np.array([12, 13, 14, 15, 16, 17]).reshape(-1, 1))
    permeability_scaler.fit(np.log(np.array([160, 170, 180, 190, 200]).reshape(-1, 1)))
    return porosity_scaler, permeability_scaler
