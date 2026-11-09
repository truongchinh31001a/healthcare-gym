"""Three trainable ablations with matching image/tabular branch architectures."""
import torch
from torch import nn

from scripts.bodym_cnn import TwoViewBodyCNN, TARGETS, METADATA, PREPROCESS_VERSION

VARIANTS = ("tabular_only", "image_only", "fusion")


class AblationModel(nn.Module):
    def __init__(self, config, variant):
        super().__init__()
        if variant not in VARIANTS:
            raise ValueError("Unknown ablation variant")
        self.variant = variant
        template = TwoViewBodyCNN(config)
        self.encoder = template.encoder if variant != "tabular_only" else None
        self.metadata_encoder = template.metadata_encoder if variant != "image_only" else None
        width = (2 * config["channels"][-1] if self.encoder is not None else 0)
        width += config["metadata_hidden"][-1] if self.metadata_encoder is not None else 0
        layers = []
        for hidden in config["fusion_hidden"]:
            layers += [nn.Linear(width, hidden), nn.ReLU(inplace=True), nn.Dropout(config["dropout"])]
            width = hidden
        layers.append(nn.Linear(width, len(TARGETS)))
        self.head = nn.Sequential(*layers)

    def forward(self, images, metadata):
        branches = []
        if self.encoder is not None:
            batch = len(images)
            branches.append(self.encoder(images.reshape(batch * 2, *images.shape[2:])).reshape(batch, -1))
        if self.metadata_encoder is not None:
            branches.append(self.metadata_encoder(metadata))
        return self.head(torch.cat(branches, dim=1))


def load_ablation(path, device="cpu"):
    checkpoint = torch.load(path, map_location=device, weights_only=True)
    if checkpoint.get("phase") != "refit_without_calibration" or checkpoint.get("preprocess_version") != PREPROCESS_VERSION:
        raise ValueError("Expected a Phase 3 refit checkpoint, not the default all-train model")
    if checkpoint["targets"] != list(TARGETS) or checkpoint["metadata_names"] != list(METADATA):
        raise ValueError("Checkpoint input/target schema mismatch")
    model = AblationModel(checkpoint["config"], checkpoint["variant"]).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model, checkpoint
