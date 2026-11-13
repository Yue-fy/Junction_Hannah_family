"""Our own re-implementation of the CubiCasa5K multi-task network (Kalervo et al. 2019, "CubiCasa5K: A Dataset
and an Improved Multi-Task Model for Floorplan Image Analysis"), written to match the parameter names of the
public checkpoint `model_best_val_loss_var.pkl` (CC BY-NC 4.0, https://github.com/CubiCasa/CubiCasa5k).
We do not import or execute the upstream code; the checkpoint is loaded with torch.load(weights_only=True).

Output: 44 channels = 21 junction heatmaps (sigmoid) + 12 room classes + 11 icon classes (logits).
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOMS = ["Background", "Outdoor", "Wall", "Kitchen", "Living Room", "Bed Room", "Bath", "Entry", "Railing",
         "Storage", "Garage", "Undefined"]
ICONS = ["No Icon", "Window", "Door", "Closet", "Electrical Appliance", "Toilet", "Sink", "Sauna Bench",
         "Fire Place", "Bathtub", "Chimney"]


class Residual(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.cin, self.cout = cin, cout
        h = cout // 2
        self.bn = nn.BatchNorm2d(cin)
        self.conv1 = nn.Conv2d(cin, h, 1)
        self.bn1 = nn.BatchNorm2d(h)
        self.conv2 = nn.Conv2d(h, h, 3, padding=1)
        self.bn2 = nn.BatchNorm2d(h)
        self.conv3 = nn.Conv2d(h, cout, 1)
        if cin != cout:
            self.conv4 = nn.Conv2d(cin, cout, 1)

    def forward(self, x):
        o = self.conv1(F.relu(self.bn(x)))
        o = self.conv2(F.relu(self.bn1(o)))
        o = self.conv3(F.relu(self.bn2(o)))
        return o + (self.conv4(x) if self.cin != self.cout else x)


class CC5KNet(nn.Module):
    def __init__(self, n_out=44):
        super().__init__()
        R = Residual
        self.conv1_ = nn.Conv2d(3, 64, 7, stride=2, padding=3)
        self.bn1 = nn.BatchNorm2d(64)
        self.r01, self.r02, self.r03, self.r04 = R(64, 128), R(128, 128), R(128, 128), R(128, 256)
        for lvl in (1, 2, 3):
            for k in (1, 2, 3):
                setattr(self, f"r{lvl}{k}_a", R(256, 256))
            setattr(self, f"r{lvl}1_b", R(256, 256))
            setattr(self, f"r{lvl}2_b", R(256, 256))
            setattr(self, f"r{lvl}3_b", R(256, 512))
        self.r41_a, self.r42_a, self.r43_a, self.r44_a, self.r45_a = R(256, 256), R(256, 256), R(256, 256), R(256, 512), R(512, 512)
        self.r41_b, self.r42_b, self.r43_b = R(256, 256), R(256, 256), R(256, 512)
        self.upsample4 = nn.ConvTranspose2d(512, 512, 2, stride=2)
        self.r4_ = R(512, 512)
        self.upsample3 = nn.ConvTranspose2d(512, 512, 2, stride=2)
        self.r3_ = R(512, 512)
        self.upsample2 = nn.ConvTranspose2d(512, 512, 2, stride=2)
        self.r2_ = R(512, 512)
        self.upsample1 = nn.ConvTranspose2d(512, 512, 2, stride=2)
        self.conv2_ = nn.Conv2d(512, 512, 1)
        self.bn2 = nn.BatchNorm2d(512)
        self.conv3_ = nn.Conv2d(512, 256, 1)
        self.bn3 = nn.BatchNorm2d(256)
        self.conv4_ = nn.Conv2d(256, n_out, 1)
        self.upsample = nn.ConvTranspose2d(n_out, n_out, 4, stride=4)

    @staticmethod
    def _add(x, y):
        if x.shape != y.shape:
            x = F.interpolate(x, size=y.shape[-2:], mode="bilinear", align_corners=False)
        return x + y

    def _seq(self, x, *names):
        for n in names:
            x = getattr(self, n)(x)
        return x

    def forward(self, x):
        o = F.max_pool2d(F.relu(self.bn1(self.conv1_(x))), 2)
        o = self._seq(o, "r01", "r02", "r03", "r04")
        a1 = self._seq(F.max_pool2d(o, 2), "r11_a", "r12_a", "r13_a")
        b1 = self._seq(o, "r11_b", "r12_b", "r13_b")
        a2 = self._seq(F.max_pool2d(a1, 2), "r21_a", "r22_a", "r23_a")
        b2 = self._seq(a1, "r21_b", "r22_b", "r23_b")
        a3 = self._seq(F.max_pool2d(a2, 2), "r31_a", "r32_a", "r33_a")
        b3 = self._seq(a2, "r31_b", "r32_b", "r33_b")
        a4 = self._seq(F.max_pool2d(a3, 2), "r41_a", "r42_a", "r43_a", "r44_a", "r45_a")
        b4 = self._seq(a3, "r41_b", "r42_b", "r43_b")
        u = self.r4_(self._add(self.upsample4(a4), b4))
        u = self.r3_(self._add(self.upsample3(u), b3))
        u = self.r2_(self._add(self.upsample2(u), b2))
        u = self._add(self.upsample1(u), b1)
        u = F.relu(self.bn2(self.conv2_(u)))
        u = F.relu(self.bn3(self.conv3_(u)))
        u = self.upsample(self.conv4_(u))
        return torch.cat([torch.sigmoid(u[:, :21]), u[:, 21:]], 1)


def load(weights):
    ck = torch.load(weights, map_location="cpu", weights_only=True)
    sd = ck["model_state"] if "model_state" in ck else ck
    m = CC5KNet()
    missing, unexpected = m.load_state_dict(sd, strict=False)
    bad = [k for k in missing if not k.endswith("num_batches_tracked")]
    if bad or unexpected:
        raise RuntimeError(f"state dict mismatch: missing={bad[:5]} unexpected={list(unexpected)[:5]}")
    return m.eval()
