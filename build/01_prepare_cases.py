# 01_prepare_cases.py
# ---------------------------------------------------------------------------
# Step 1: turn the trainer patients (chosen in step 0) into the files the web
# page reads: one JPEG picture per slice, one small data file per patient with
# the expert's microbleeds and the algorithm's detections, and the patient index.
#
# Run (from the folder of README.md):  python build/01_prepare_cases.py
# Reads (read-only): the same files as step 0, plus
#   $CMB_CHAIN_DIR/dev/synthseg/sub-XXX_synthseg.nii.gz   SynthSeg tissue map on the U-Net grid (CSF rule)
#   $VALDO_TASK2_DIR/sub-102/...                          held-out subject, only for the tutorial picture
# Writes:
#   data/img/sub-XXX/NNN.jpg   one picture per slice (8 bit, JPEG quality 90)
#   data/case_sub-XXX.js       microbleeds, algorithm detections, geometry of one patient
#   data/cases.js              index of all patients (loaded at the start of the page)
#   data/tutorial.js           one slice of the held-out subject sub-102 for the tutorial
#   build/cases_meta.json      crop boxes, windows, algorithm numbers (for step 2 and the README)
#
# What happens for every patient
#   1. load the T2*-weighted image and the expert mask; turn them into the
#      radiological view (front of the head at the top, patient's LEFT on the
#      RIGHT of the picture, slice 1 = lowest slice)
#   2. grey window: 0.5th to 99.5th percentile of the non-zero voxels -> 0..255
#   3. crop: the box around all non-zero voxels of the image (plus 4 voxels),
#      over all slices that hold any non-zero voxel. The box depends only on the
#      image, never on the microbleeds, so it gives nothing away.
#   4. every slice of the box -> JPEG (quality 90)
#   5. microbleeds = 26-connected clusters of the expert mask; size class by
#      the diameter of the sphere with the same volume
#   6. algorithm: the out-of-fold probability map of the U-Net ensemble, the
#      fixed post-processing of the chain (threshold 0.3, 26-connected components,
#      >= 2 mm3, <= 2100 voxels, SynthSeg CSF rule). Each remaining component
#      "clicks" once, at its voxel of highest probability, carried to the T2*
#      grid through the affine matrices. These clicks are scored with exactly the
#      same hit rule as the clicks of the student.
# ---------------------------------------------------------------------------
import base64
import datetime
import glob
import io
import json
import os
import platform
import shutil

import nibabel as nib
import numpy as np
import PIL
import scipy
from PIL import Image
from scipy import ndimage

# ---- settings (change here) -------------------------------------------------
VALDO = os.environ.get("VALDO_TASK2_DIR", "/home/uchralt/data/extern/valdo2021/Task2")
CHAIN = os.environ.get("CMB_CHAIN_DIR", "/home/uchralt/data/work/valdo-t2s")
PRED_RUN = "ergebnisse/turnier/ens2-a03-aniso-e60-gd"
SYNTHSEG = "dev/synthseg/{id}_synthseg.nii.gz"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data")

WINDOW_PERCENTILES = (0.5, 99.5)
CROP_MARGIN = 4                    # voxels around the non-zero box
JPEG_QUALITY = 90
TOLERANCE_INPLANE_MM = 2.0         # hit rule: this far within the slice ...
TOLERANCE_THROUGH_MM = 2.0         # ... and this far through the slices, but never less than 1 slice
TUTORIAL_SUBJECT = "sub-102"       # one of the 15 held-out subjects: never a trainer patient

# fixed post-processing of the chain (cmb-valdo-chain, cmb/transfer/evaluate.py + CSF rule)
THRESHOLD, MIN_MM3, MAX_VOXELS = 0.3, 2.0, 2100
CSF_LABELS = {4, 5, 14, 15, 24, 43, 44}
CONN26 = np.ones((3, 3, 3), dtype=bool)


def size_class(d):
    return "<2" if d < 2 else ("2-5" if d <= 5 else ">5")


def majority_label(component, seg):
    # majority SynthSeg label under the component; only background -> widen by 3 voxels (rule of the chain)
    for iterations in (0, 3):
        m = ndimage.binary_dilation(component, structure=CONN26, iterations=iterations) if iterations else component
        values = seg[m]
        values = values[values > 0]
        if len(values):
            return int(np.bincount(values).argmax())
    return 0


def score(clusters, markers, voxel_mm, tol_slices):
    # The hit rule of the page (index.html, scoreMarkers), written in Python.
    dx, dy, dz = voxel_mm
    pairs, near = [], [[] for _ in markers]
    for mi, (mx, my, mz) in enumerate(markers):
        for ci, c in enumerate(clusters):
            v = np.array(c["voxels"]).reshape(-1, 3)
            sl = np.abs(v[:, 2] - mz)
            inplane = np.hypot((v[:, 0] - mx) * dx, (v[:, 1] - my) * dy)
            ok = (sl <= tol_slices) & (inplane <= TOLERANCE_INPLANE_MM + 1e-9)
            if ok.any():
                d = float(np.sqrt(inplane[ok] ** 2 + (sl[ok] * dz) ** 2).min())
                pairs.append((d, mi, ci)); near[mi].append(ci)
    pairs.sort()
    status, found_by = [None] * len(markers), [-1] * len(clusters)
    for d, mi, ci in pairs:
        if status[mi] is None and found_by[ci] < 0:
            status[mi] = "hit"; found_by[ci] = mi
    for mi in range(len(markers)):
        if status[mi] is None:
            status[mi] = "dup" if near[mi] else "fp"
    tp = sum(f >= 0 for f in found_by)
    fp = status.count("fp")
    fn = len(clusters) - tp
    f1 = 1.0 if tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)
    classes = {k: [0, 0] for k in ("<2", "2-5", ">5")}
    for ci, c in enumerate(clusters):
        classes[c["size_class"]][1] += 1
        classes[c["size_class"]][0] += found_by[ci] >= 0
    return dict(tp=tp, fp=fp, fn=fn, dup=status.count("dup"), f1=f1, classes=classes, status=status)


def load_display(sub):
    """T2* image and expert mask in the display order [slice, row, column] (radiological view)."""
    t2s = nib.load(f"{VALDO}/{sub}/{sub}_space-T2S_desc-masked_T2S.nii.gz")
    ref = nib.load(f"{VALDO}/{sub}/{sub}_space-T2S_CMB.nii.gz")
    assert t2s.shape == ref.shape and np.allclose(t2s.affine, ref.affine, atol=1e-3)
    axcodes = "".join(nib.aff2axcodes(t2s.affine))
    t2s, ref = nib.as_closest_canonical(t2s), nib.as_closest_canonical(ref)
    assert nib.aff2axcodes(t2s.affine) == ("R", "A", "S")
    img = np.asanyarray(t2s.dataobj).astype(np.float32)
    mask = np.asanyarray(ref.dataobj) > 0
    # column 0 = patient's RIGHT (flip axis 0); row 0 = FRONT (flip axis 1); slice 0 = lowest
    img = np.ascontiguousarray(img[::-1, ::-1, :].transpose(2, 1, 0))
    mask = np.ascontiguousarray(mask[::-1, ::-1, :].transpose(2, 1, 0))
    return t2s, img, mask, axcodes


def to_uint8(img):
    lo, hi = np.percentile(img[img > 0], WINDOW_PERCENTILES)
    return (np.clip((img - lo) / (hi - lo), 0, 1) * 255).round().astype(np.uint8), (float(lo), float(hi))


# ---- the patients ------------------------------------------------------------------
table = [l.rstrip("\n").split("\t") for l in open(os.path.join(HERE, "case_table.tsv"))]
head, table = table[0], table[1:]
subjects = [r[0] for r in table if r[head.index("trainer_patient")] == "yes"]
print(f"{len(subjects)} trainer patients")

if os.path.isdir(os.path.join(OUT, "img")):
    shutil.rmtree(os.path.join(OUT, "img"))
for old in glob.glob(os.path.join(OUT, "case_*.js")):
    os.remove(old)
os.makedirs(os.path.join(OUT, "img"), exist_ok=True)

index_rows, meta = [], {}
for sub in subjects:
    canon, img, mask, axcodes = load_display(sub)
    nz, ny, nx = img.shape
    dx, dy, dz = [float(v) for v in canon.header.get_zooms()[:3]]
    img8, window = to_uint8(img)

    # ---- crop box: from the image only ----
    nonzero = img8 > 0
    zs = np.nonzero(nonzero.any(axis=(1, 2)))[0]
    ys = np.nonzero(nonzero.any(axis=(0, 2)))[0]
    xs = np.nonzero(nonzero.any(axis=(0, 1)))[0]
    x0, x1 = max(0, xs.min() - CROP_MARGIN), min(nx, xs.max() + 1 + CROP_MARGIN)
    y0, y1 = max(0, ys.min() - CROP_MARGIN), min(ny, ys.max() + 1 + CROP_MARGIN)
    z0, z1 = int(zs.min()), int(zs.max()) + 1
    x0, x1, y0, y1 = int(x0), int(x1), int(y0), int(y1)
    assert not mask[:z0].any() and not mask[z1:].any(), f"{sub}: microbleed outside the slice range"
    assert not mask[:, :y0].any() and not mask[:, y1:].any() and not mask[:, :, :x0].any() and not mask[:, :, x1:].any()
    crop = img8[z0:z1, y0:y1, x0:x1]
    cmask = mask[z0:z1, y0:y1, x0:x1]
    W, H, N = x1 - x0, y1 - y0, z1 - z0

    # ---- pictures ----
    folder = os.path.join(OUT, "img", sub)
    os.makedirs(folder)
    total = 0
    for k in range(N):
        path = os.path.join(folder, f"{k:03d}.jpg")
        Image.fromarray(crop[k]).save(path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        total += os.path.getsize(path)

    # ---- microbleeds ----
    tol_slices = max(1, int(TOLERANCE_THROUGH_MM // dz))
    labels, n = ndimage.label(cmask, structure=CONN26)
    clusters = []
    for k in range(1, n + 1):
        vz, vy, vx = np.nonzero(labels == k)
        volume = len(vx) * dx * dy * dz
        d = (6 * volume / np.pi) ** (1 / 3)
        clusters.append({
            "id": k, "n_voxels": int(len(vx)), "volume_mm3": round(volume, 2), "diameter_mm": round(d, 2),
            "size_class": size_class(d),
            "centroid": [round(float(vx.mean()), 2), round(float(vy.mean()), 2), round(float(vz.mean()), 2)],
            "bbox": [int(vx.min()), int(vy.min()), int(vz.min()), int(vx.max()), int(vy.max()), int(vz.max())],
            "voxels": np.stack([vx, vy, vz], axis=1).flatten().tolist(),
        })
    # sort from bottom to top so that the numbers on the page follow the slices
    clusters.sort(key=lambda c: (c["centroid"][2], c["centroid"][1], c["centroid"][0]))
    for i, c in enumerate(clusters):
        c["id"] = i + 1

    # ---- algorithm ----
    pred_path = glob.glob(f"{CHAIN}/{PRED_RUN}/fold*/{sub}_pred_proba.nii.gz")
    assert len(pred_path) == 1, f"{sub}: no single out-of-fold prediction"
    fold = int(pred_path[0].split("/fold")[1].split("/")[0])
    pred_img = nib.load(pred_path[0])
    prob = np.asanyarray(pred_img.dataobj).astype(np.float32) / 255.0
    seg_img = nib.load(os.path.join(CHAIN, SYNTHSEG.format(id=sub)))
    assert seg_img.shape == prob.shape and np.allclose(seg_img.affine, pred_img.affine, atol=1e-3)
    seg = np.asanyarray(seg_img.dataobj).astype(np.int32)
    grid_voxel_mm3 = float(np.prod(pred_img.header.get_zooms()[:3]))
    assert abs(grid_voxel_mm3 - 0.25) < 1e-3
    plab, pn = ndimage.label(prob > THRESHOLD, structure=CONN26)
    psize = np.bincount(plab.ravel(), minlength=pn + 1)
    to_canon = np.linalg.inv(canon.affine) @ pred_img.affine          # U-Net grid voxel -> T2* voxel (canonical)
    algo, removed = [], {"small": 0, "giant": 0, "csf": 0}
    for c, box in enumerate(ndimage.find_objects(plab), start=1):
        if psize[c] * grid_voxel_mm3 < MIN_MM3:
            removed["small"] += 1; continue
        if psize[c] > MAX_VOXELS:
            removed["giant"] += 1; continue
        comp = plab[box] == c
        if majority_label(comp, seg[box]) in CSF_LABELS:
            removed["csf"] += 1; continue
        p = np.where(comp, prob[box], -1)
        peak = np.unravel_index(int(np.argmax(p)), p.shape)
        g = np.array([box[0].start + peak[0], box[1].start + peak[1], box[2].start + peak[2], 1.0])
        i, j, kk = (to_canon @ g)[:3]
        col, row, sl = (nx - 1) - i, (ny - 1) - j, kk                  # same flips as the picture
        x, y, z = int(round(col)) - x0, int(round(row)) - y0, int(round(sl)) - z0
        inside = 0 <= x < W and 0 <= y < H and 0 <= z < N
        algo.append({"x": x, "y": y, "z": z, "peak": round(float(prob[tuple(g[:3].astype(int))]), 3),
                     "volume_mm3": round(float(psize[c] * grid_voxel_mm3), 2), "inside": inside})
    algo.sort(key=lambda a: -a["peak"])
    outside = [a for a in algo if not a["inside"]]
    assert not outside, f"{sub}: {len(outside)} algorithm detections outside the picture"
    s = score(clusters, [(a["x"], a["y"], a["z"]) for a in algo], (dx, dy, dz), tol_slices)

    data = {
        "id": sub, "site": int(sub[4]), "width": int(W), "height": int(H), "n_slices": int(N),
        "voxel_mm": [round(dx, 4), round(dy, 4), round(dz, 4)],
        "crop": {"x0": int(x0), "y0": int(y0), "z0": int(z0), "full": [int(nx), int(ny), int(nz)]},
        "nifti_axcodes": axcodes,
        "tolerance": {"inplane_mm": TOLERANCE_INPLANE_MM, "slices": tol_slices},
        "clusters": clusters,
        "algo": [[a["x"], a["y"], a["z"]] for a in algo],
        "algo_info": [[a["peak"], a["volume_mm3"]] for a in algo],
        "img": f"data/img/{sub}/",
    }
    with open(os.path.join(OUT, f"case_{sub}.js"), "w") as f:
        f.write("// Made by build/01_prepare_cases.py - do not edit by hand. Derived from VALDO 2021 Task 2, CC BY-NC-SA 4.0.\n")
        f.write("window.CMB_CASES = window.CMB_CASES || {};\n")
        f.write(f'window.CMB_CASES["{sub}"] = ' + json.dumps(data, separators=(",", ":")) + ";\n")
    size_mb = (total + os.path.getsize(os.path.join(OUT, f"case_{sub}.js"))) / 1e6
    cls = {k: sum(c["size_class"] == k for c in clusters) for k in ("<2", "2-5", ">5")}
    index_rows.append({
        "id": sub, "site": int(sub[4]), "nSlices": int(N), "width": int(W), "height": int(H),
        "voxelMm": data["voxel_mm"], "nRef": len(clusters), "classes": [cls["<2"], cls["2-5"], cls[">5"]],
        "algoF1": round(s["f1"], 4), "algoTP": s["tp"], "algoFP": s["fp"], "algoFN": s["fn"], "algoDup": s["dup"],
        "algoClasses": [s["classes"][k][0] for k in ("<2", "2-5", ">5")], "fold": fold, "sizeMb": round(size_mb, 2),
    })
    meta[sub] = {"crop": [int(x0), int(x1), int(y0), int(y1), int(z0), int(z1)], "window": [round(window[0], 3), round(window[1], 3)],
                 "fold": fold, "tol_slices": tol_slices, "algo_removed": removed, "algo_detections": len(algo),
                 "algo": {k: s[k] for k in ("tp", "fp", "fn", "dup", "f1")}, "size_mb": round(size_mb, 2)}
    print(f"{sub}  {W}x{H}x{N} (of {nx}x{ny}x{nz})  voxel {dx:.2f}x{dy:.2f}x{dz:.2f}  microbleeds {len(clusters)} "
          f"{cls}  algo {len(algo)} detections TP {s['tp']} FP {s['fp']} FN {s['fn']} dup {s['dup']} F1 {s['f1']:.3f}  "
          f"{size_mb:.2f} MB", flush=True)
    del img, img8, mask, crop, prob, seg, plab

# ---- tutorial picture (held-out subject, not a trainer patient) -------------------
assert TUTORIAL_SUBJECT not in subjects
canon, img, mask, _ = load_display(TUTORIAL_SUBJECT)
img8, _ = to_uint8(img)
labels, n = ndimage.label(mask, structure=CONN26)
assert n == 1
vz, vy, vx = np.nonzero(labels == 1)
z = int(np.bincount(vz).argmax())                     # slice with the largest cross-section
nonzero = img8[z] > 0
ys, xs = np.nonzero(nonzero.any(axis=1))[0], np.nonzero(nonzero.any(axis=0))[0]
tx0, tx1, ty0, ty1 = max(0, xs.min() - 4), xs.max() + 5, max(0, ys.min() - 4), ys.max() + 5
buf = io.BytesIO()
Image.fromarray(img8[z, ty0:ty1, tx0:tx1]).save(buf, format="PNG", optimize=True)
dxt = float(canon.header.get_zooms()[0])
d_tut = (6 * len(vx) * float(np.prod(canon.header.get_zooms()[:3])) / np.pi) ** (1 / 3)
tutorial = {"subject": TUTORIAL_SUBJECT, "width": int(tx1 - tx0), "height": int(ty1 - ty0),
            "voxelMm": [round(dxt, 4), round(float(canon.header.get_zooms()[1]), 4)],
            "cmb": [round(float(vx[vz == z].mean()) - tx0, 1), round(float(vy[vz == z].mean()) - ty0, 1)],
            "diameterMm": round(d_tut, 1), "slice": z + 1, "nSlices": int(img8.shape[0]),
            "png": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")}
with open(os.path.join(OUT, "tutorial.js"), "w") as f:
    f.write("// Made by build/01_prepare_cases.py. One slice of the held-out VALDO subject sub-102 (CC BY-NC-SA 4.0).\n")
    f.write("window.CMB_TUTORIAL = " + json.dumps(tutorial, separators=(",", ":")) + ";\n")

# ---- index ---------------------------------------------------------------------------
tp = sum(r["algoTP"] for r in index_rows); fp = sum(r["algoFP"] for r in index_rows); fn = sum(r["algoFN"] for r in index_rows)
index = {
    "cases": index_rows,
    "builtOn": datetime.date.today().isoformat(),
    "software": {"Python": platform.python_version(), "nibabel": nib.__version__, "NumPy": np.__version__,
                 "SciPy": scipy.__version__, "Pillow": PIL.__version__},
    "window": {"percentiles": list(WINDOW_PERCENTILES)},
    "jpegQuality": JPEG_QUALITY,
    "algorithm": {"name": "3D U-Net", "detail": "two-seed ensemble of the anisotropic 3D U-Net (a03-aniso), 5-fold cross-validation, out-of-fold",
                  "threshold": THRESHOLD, "minMm3": MIN_MM3, "maxVoxels": MAX_VOXELS, "csfRule": True,
                  "meanF1": round(float(np.mean([r["algoF1"] for r in index_rows])), 4),
                  "meanF1WithCmb": round(float(np.mean([r["algoF1"] for r in index_rows if r["nRef"] > 0])), 4),
                  "pooledF1": round(2 * tp / (2 * tp + fp + fn), 4), "tp": tp, "fp": fp, "fn": fn},
}
with open(os.path.join(OUT, "cases.js"), "w") as f:
    f.write("// Made by build/01_prepare_cases.py - do not edit by hand. Derived from VALDO 2021 Task 2, CC BY-NC-SA 4.0.\n")
    f.write("window.CMB_INDEX = " + json.dumps(index, separators=(",", ":")) + ";\n")
json.dump(meta, open(os.path.join(HERE, "cases_meta.json"), "w"), indent=1)
a = index["algorithm"]
print(f"\nalgorithm: mean F1 {a['meanF1']:.3f} over {len(index_rows)} patients, {a['meanF1WithCmb']:.3f} over the patients with "
      f"microbleeds, pooled F1 {a['pooledF1']:.3f} (TP {tp}, FP {fp}, FN {fn})")
print(f"data: {sum(r['sizeMb'] for r in index_rows):.1f} MB")
