# 00_survey_cases.py
# ---------------------------------------------------------------------------
# Step 0: one table row per subject of VALDO 2021 Task 2 (all 72), and the
# decision which subjects become trainer patients.
#
# Run (from the folder of README.md):  python build/00_survey_cases.py
# Reads (read-only):
#   $VALDO_TASK2_DIR/sub-XXX/sub-XXX_space-T2S_desc-masked_T2S.nii.gz   T2*-weighted image
#   $VALDO_TASK2_DIR/sub-XXX/sub-XXX_space-T2S_CMB.nii.gz              expert microbleed mask
#   $CMB_CHAIN_DIR/dev/split.json                                      the 15 held-out cases and the 5 folds
#   $CMB_CHAIN_DIR/<PRED_RUN>/fold*/sub-XXX_pred_proba.nii.gz          out-of-fold prediction of the U-Net
# Writes: build/case_table.tsv
#
# A subject becomes a trainer patient if (1) it is one of the 57 cross-validation
# cases (not one of the 15 held-out cases) and (2) an out-of-fold prediction of
# the algorithm exists for it. Subjects with 0 microbleeds are kept on purpose.
#
# Words used below
#   microbleed = one cluster of expert voxels that touch by a face, an edge or a
#                corner (26-connectivity)
#   diameter   = diameter of the sphere with the same volume, d = (6 V / pi)^(1/3)
#   size class = < 2 mm, 2-5 mm, > 5 mm (by that diameter)
# ---------------------------------------------------------------------------
import glob
import json
import os

import nibabel as nib
import numpy as np
from scipy import ndimage

VALDO = os.environ.get("VALDO_TASK2_DIR", "/home/uchralt/data/extern/valdo2021/Task2")
CHAIN = os.environ.get("CMB_CHAIN_DIR", "/home/uchralt/data/work/valdo-t2s")
PRED_RUN = "ergebnisse/turnier/ens2-a03-aniso-e60-gd"     # two-seed ensemble of the anisotropic 3D U-Net
HERE = os.path.dirname(os.path.abspath(__file__))
CONN26 = np.ones((3, 3, 3), dtype=int)

split = json.load(open(os.path.join(CHAIN, "dev/split.json")))
held_out = set(split["validation"])
fold_of = {}
folds = split["folds"]
for k, members in (folds.items() if isinstance(folds, dict) else enumerate(folds)):
    for sub in members:
        fold_of[sub] = int(str(k).replace("fold", ""))


def size_class(d):
    return "<2" if d < 2 else ("2-5" if d <= 5 else ">5")


rows = []
for folder in sorted(glob.glob(VALDO + "/sub-*")):
    sub = os.path.basename(folder)
    t2s = nib.load(f"{folder}/{sub}_space-T2S_desc-masked_T2S.nii.gz")
    mask = np.asanyarray(nib.load(f"{folder}/{sub}_space-T2S_CMB.nii.gz").dataobj) > 0
    dx, dy, dz = [float(v) for v in t2s.header.get_zooms()[:3]]
    labels, n = ndimage.label(mask, structure=CONN26)
    sizes = np.bincount(labels.ravel())[1:]
    diam = [(6 * s * dx * dy * dz / np.pi) ** (1 / 3) for s in sizes]
    pred = glob.glob(f"{CHAIN}/{PRED_RUN}/fold*/{sub}_pred_proba.nii.gz")
    in_cv = sub not in held_out
    use = in_cv and len(pred) == 1
    rows.append([sub, "site " + sub[4], *t2s.shape[:3], f"{dx:.3f}", f"{dy:.3f}", f"{dz:.3f}", n,
                 sum(size_class(d) == "<2" for d in diam), sum(size_class(d) == "2-5" for d in diam),
                 sum(size_class(d) == ">5" for d in diam),
                 "held-out" if not in_cv else f"fold {fold_of.get(sub, '?')}",
                 "yes" if pred else "no", "yes" if use else "no"])
    print(f"{sub}: {t2s.shape} {dx:.2f}x{dy:.2f}x{dz:.2f} mm  microbleeds {n}  "
          f"{'held-out' if not in_cv else 'CV'}  prediction {'yes' if pred else 'no'}  -> {'TRAINER' if use else 'not used'}")

head = ["subject", "site", "nx", "ny", "nz", "dx_mm", "dy_mm", "dz_mm", "microbleeds_26conn",
        "n_lt2mm", "n_2to5mm", "n_gt5mm", "cv_fold", "prediction", "trainer_patient"]
with open(os.path.join(HERE, "case_table.tsv"), "w") as f:
    f.write("\t".join(head) + "\n")
    for r in rows:
        f.write("\t".join(str(v) for v in r) + "\n")
used = [r for r in rows if r[-1] == "yes"]
print(f"\n{len(rows)} subjects, {len(used)} trainer patients "
      f"({sum(r[8] > 0 for r in used)} with microbleeds, {sum(r[8] == 0 for r in used)} without)")
for s in ("1", "2", "3"):
    u = [r for r in used if r[0][4] == s]
    print(f"  site {s}: {len(u)} patients, {sum(r[8] > 0 for r in u)} with / {sum(r[8] == 0 for r in u)} without, "
          f"{sum(r[8] for r in u)} microbleeds")
