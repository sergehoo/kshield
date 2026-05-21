"""KAYDAN SHIELD — Architecture MiniFASNet vendorisée (Silent-Face-Anti-Spoofing).

Code repris du repo officiel :
    https://github.com/minivision-ai/Silent-Face-Anti-Spoofing
    src/model_lib/MiniFASNet.py — Licence MIT (Minivision 2020).

Vendorisé ici pour permettre la conversion .pth -> .onnx sans cloner tout le
repo. N'est importé que par la commande ``download_face_models --auto-convert``
(donc PyTorch n'est PAS requis au runtime de l'API — c'est uniquement un outil
de provisionnement).
"""
from __future__ import annotations

try:
    import torch
    import torch.nn.functional as F
    from torch import nn
except ImportError:  # pragma: no cover
    raise ImportError(
        "PyTorch requis pour utiliser MiniFASNet (uniquement pour la conversion "
        ".pth -> .onnx). Installer : `pip install torch`."
    )


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
class Conv_block(nn.Module):
    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding, groups=groups, bias=False)
        self.bn = nn.BatchNorm2d(out_c)
        self.prelu = nn.PReLU(out_c)

    def forward(self, x):
        return self.prelu(self.bn(self.conv(x)))


class Linear_block(nn.Module):
    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding, groups=groups, bias=False)
        self.bn = nn.BatchNorm2d(out_c)

    def forward(self, x):
        return self.bn(self.conv(x))


class Depth_Wise(nn.Module):
    def __init__(self, in_c, out_c, residual=False, kernel=(3, 3),
                 stride=(2, 2), padding=(1, 1), groups=1):
        super().__init__()
        self.conv = Conv_block(in_c, groups, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(groups, groups, groups=groups, kernel=kernel,
                                   padding=padding, stride=stride)
        self.project = Linear_block(groups, out_c, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual

    def forward(self, x):
        short = x if self.residual else None
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)
        if short is not None:
            x = x + short
        return x


class Residual(nn.Module):
    def __init__(self, c, num_block, groups, kernel=(3, 3), stride=(1, 1), padding=(1, 1)):
        super().__init__()
        modules = [
            Depth_Wise(c, c, residual=True, kernel=kernel, padding=padding,
                       stride=stride, groups=groups)
            for _ in range(num_block)
        ]
        self.model = nn.Sequential(*modules)

    def forward(self, x):
        return self.model(x)


# ---------------------------------------------------------------------------
# SE block (Squeeze-Excitation) — utilisé par MiniFASNetV1SE
# ---------------------------------------------------------------------------
class SEModule(nn.Module):
    def __init__(self, channels, reduction):
        super().__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Conv2d(channels, channels // reduction, kernel_size=1, padding=0, bias=False)
        self.relu = nn.ReLU(inplace=True)
        self.fc2 = nn.Conv2d(channels // reduction, channels, kernel_size=1, padding=0, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        b = x
        x = self.avg_pool(x)
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        x = self.sigmoid(x)
        return b * x


class Depth_Wise_SE(nn.Module):
    def __init__(self, in_c, out_c, residual=False, kernel=(3, 3),
                 stride=(2, 2), padding=(1, 1), groups=1, se_reduct=4):
        super().__init__()
        self.conv = Conv_block(in_c, groups, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(groups, groups, groups=groups, kernel=kernel,
                                   padding=padding, stride=stride)
        self.project = Linear_block(groups, out_c, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual
        self.se_module = SEModule(out_c, se_reduct)

    def forward(self, x):
        short = x if self.residual else None
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)
        x = self.se_module(x)
        if short is not None:
            x = x + short
        return x


class ResidualSE(nn.Module):
    def __init__(self, c, num_block, groups, kernel=(3, 3), stride=(1, 1), padding=(1, 1), se_reduct=8):
        super().__init__()
        modules = [
            Depth_Wise_SE(c, c, residual=True, kernel=kernel, padding=padding,
                          stride=stride, groups=groups, se_reduct=se_reduct)
            for _ in range(num_block)
        ]
        self.model = nn.Sequential(*modules)

    def forward(self, x):
        return self.model(x)


# ---------------------------------------------------------------------------
# Stage config — ordre exact des couches dans MiniFASNet (copié du repo officiel).
# ---------------------------------------------------------------------------
keep_dict = {
    '1.8M': [
        32, 32, 103, 103, 64, 13, 13, 64, 26, 26, 64, 13, 13, 64, 52, 52, 64,
        231, 231, 128, 154, 154, 128, 52, 52, 128, 26, 26, 128, 52, 52, 128,
        26, 26, 128, 26, 26, 128, 308, 308, 128, 26, 26, 128, 26, 26, 128, 512, 512
    ],
    '1.8M_': [
        32, 32, 103, 103, 64, 13, 13, 64, 13, 13, 64, 13, 13, 64, 13, 13, 64,
        231, 231, 128, 231, 231, 128, 52, 52, 128, 26, 26, 128, 77, 77, 128,
        26, 26, 128, 26, 26, 128, 308, 308, 128, 26, 26, 128, 26, 26, 128, 512, 512
    ],
}


# ---------------------------------------------------------------------------
# Backbone commun
# ---------------------------------------------------------------------------
class MiniFASNet(nn.Module):
    def __init__(self, keep, embedding_size, conv6_kernel=(5, 5),
                 drop_p=0.0, num_classes=3, img_channel=3):
        super().__init__()
        self.embedding_size = embedding_size
        self.conv1 = Conv_block(img_channel, keep[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1))
        self.conv2_dw = Conv_block(keep[0], keep[1], kernel=(3, 3),
                                    stride=(1, 1), padding=(1, 1), groups=keep[1])
        self.conv_23 = Depth_Wise(keep[1], keep[3], kernel=(3, 3),
                                   stride=(2, 2), padding=(1, 1), groups=keep[2])
        self.conv_3 = Residual(keep[3], num_block=4, groups=keep[4],
                                kernel=(3, 3), stride=(1, 1), padding=(1, 1))
        self.conv_34 = Depth_Wise(keep[3], keep[18], kernel=(3, 3),
                                   stride=(2, 2), padding=(1, 1), groups=keep[17])
        self.conv_4 = Residual(keep[18], num_block=6, groups=keep[19],
                                kernel=(3, 3), stride=(1, 1), padding=(1, 1))
        self.conv_45 = Depth_Wise(keep[18], keep[37], kernel=(3, 3),
                                   stride=(2, 2), padding=(1, 1), groups=keep[36])
        self.conv_5 = Residual(keep[37], num_block=2, groups=keep[38],
                                kernel=(3, 3), stride=(1, 1), padding=(1, 1))
        self.conv_6_sep = Conv_block(keep[37], keep[46], kernel=(1, 1),
                                      stride=(1, 1), padding=(0, 0))
        self.conv_6_dw = Linear_block(keep[46], keep[46], groups=keep[46],
                                       kernel=conv6_kernel, stride=(1, 1), padding=(0, 0))
        self.conv_6_flatten = nn.Flatten()
        self.linear = nn.Linear(keep[46], embedding_size, bias=False)
        self.bn = nn.BatchNorm1d(embedding_size)
        self.drop = nn.Dropout(p=drop_p)
        self.prob = nn.Linear(embedding_size, num_classes, bias=False)

    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2_dw(x)
        x = self.conv_23(x)
        x = self.conv_3(x)
        x = self.conv_34(x)
        x = self.conv_4(x)
        x = self.conv_45(x)
        x = self.conv_5(x)
        x = self.conv_6_sep(x)
        x = self.conv_6_dw(x)
        x = self.conv_6_flatten(x)
        x = self.linear(x)
        x = self.bn(x)
        x = self.drop(x)
        x = self.prob(x)
        return x


# ---------------------------------------------------------------------------
# Variante SE (squeeze-excitation)
# ---------------------------------------------------------------------------
class MiniFASNetSE(MiniFASNet):
    def __init__(self, keep, embedding_size, conv6_kernel=(5, 5),
                 drop_p=0.0, num_classes=3, img_channel=3):
        super().__init__(keep, embedding_size, conv6_kernel,
                         drop_p, num_classes, img_channel)
        # Remplace les Residual par des ResidualSE
        self.conv_3 = ResidualSE(keep[3], num_block=4, groups=keep[4],
                                  kernel=(3, 3), stride=(1, 1), padding=(1, 1))
        self.conv_4 = ResidualSE(keep[18], num_block=6, groups=keep[19],
                                  kernel=(3, 3), stride=(1, 1), padding=(1, 1))
        self.conv_5 = ResidualSE(keep[37], num_block=2, groups=keep[38],
                                  kernel=(3, 3), stride=(1, 1), padding=(1, 1))


# ---------------------------------------------------------------------------
# Wrappers exposés (avec les keep configs correspondant aux fichiers .pth)
# ---------------------------------------------------------------------------
def MiniFASNetV2(embedding_size=128, conv6_kernel=(5, 5),
                 drop_p=0.0, num_classes=3, img_channel=3):
    return MiniFASNet(keep_dict["1.8M_"], embedding_size, conv6_kernel,
                      drop_p, num_classes, img_channel)


def MiniFASNetV1SE(embedding_size=128, conv6_kernel=(5, 5),
                   drop_p=0.0, num_classes=3, img_channel=3):
    return MiniFASNetSE(keep_dict["1.8M"], embedding_size, conv6_kernel,
                        drop_p, num_classes, img_channel)
