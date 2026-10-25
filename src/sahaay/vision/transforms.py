"""
Sahaay AI - Flood Vision Transforms
Defines standardized image preprocessing pipelines for training, validation, and production inference.
"""

from torchvision import transforms

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

def get_train_transforms(image_size: int = 224) -> transforms.Compose:
    """
    Data augmentation and normalization pipeline for model training.
    Applies random crops, horizontal flips, and slight color perturbations
    to simulate varying monsoon lighting and angles while keeping evaluation untouched.
    """
    return transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomResizedCrop(image_size, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    ])

def get_eval_transforms(image_size: int = 224) -> transforms.Compose:
    """
    Deterministic evaluation and production inference transform pipeline.
    Resizes image to 256 then extracts center 224x224 crop followed by standard ImageNet normalization.
    """
    return transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    ])

def get_monsoon_train_transforms(image_size: int = 224) -> transforms.Compose:
    """
    Realistic monsoon degradation augmentation pipeline for robust model training.
    Injects Gaussian blur, sharpness attenuation, contrast degradation, and lighting shifts
    characteristic of torrential rain downpours and lens mist.
    """
    return transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomResizedCrop(image_size, scale=(0.75, 1.0)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
        transforms.RandomAdjustSharpness(sharpness_factor=0.4, p=0.4),
        transforms.GaussianBlur(kernel_size=(5, 9), sigma=(0.1, 2.5)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    ])

