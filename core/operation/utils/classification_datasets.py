from typing import Tuple

import numpy as np
import torch
from torch.utils.data import Dataset


class CustomClassificationDataset(Dataset):
    """Class for custom classification datasets.

    Args:
        images: Numpy matrix of images.
        targets: Numpy vector of targets.
    """

    def __init__(
        self,
        images: np.ndarray,
        targets: np.ndarray,
    ) -> None:
        self.images = torch.from_numpy(images)
        self.targets = targets

    def __getitem__(self, idx) -> Tuple[torch.Tensor, int]:
        """Returns a sample from a dataset.

        Args:
            idx: Index of sample.

        Returns:
            A tuple ``(image, target)``, where image is image tensor,
                and target is integer.
        """
        return self.images[idx], self.targets[idx]

    def __len__(self) -> int:
        """Return length of dataset"""
        return self.targets.size
