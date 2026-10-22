from pathlib import Path

import matplotlib as mpl
import seaborn as sns

PAPER_DPI = 200
WIDTH = 5.5

ROSEWOOD = ["#5B1932", "#87354B", "#AF5763", "#D38075"]
BUTTER = ["#EEB089", "#FAE69E"]
PERIWINKLE = ["#ACBCE4", "#8193C7", "#5A6AA8", "#394287", "#1E1D60"]
GRADIENT = ROSEWOOD + BUTTER + PERIWINKLE
PALETTE = [GRADIENT[i] for i in (9, 3, 2, 8, 10, 0)]


def save(fig, out: Path) -> None:
    fig.savefig(Path(out).with_suffix(".png"), dpi=PAPER_DPI)


def apply() -> None:
    sns.set_theme(style="whitegrid")
    mpl.rcParams.update(
        {
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "axes.labelsize": 8,
            "axes.titlesize": 8,
            "legend.fontsize": 7,
            "legend.frameon": False,
            "figure.titlesize": 9,
            "axes.edgecolor": "black",
            "axes.linewidth": 0.8,
            "axes.grid": False,
            "axes.prop_cycle": mpl.cycler(color=PALETTE),
            "xtick.bottom": True,
            "ytick.left": True,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.color": "black",
            "ytick.color": "black",
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.minor.size": 1.2,
            "ytick.minor.size": 1.2,
            "xtick.minor.width": 0.5,
            "ytick.minor.width": 0.5,
            "xtick.major.pad": 2.0,
            "ytick.major.pad": 2.0,
            "axes.labelpad": 3.0,
            "axes.titlepad": 4.0,
            "figure.dpi": PAPER_DPI,
            "savefig.dpi": PAPER_DPI,
            "savefig.bbox": "tight",
        }
    )
