# 04_tutorial_pictures.py
# ---------------------------------------------------------------------------
# Step 4 (16.11.2026): the example pictures of the lookalike steps of the tutorial.
#
# Input : $VALDO_TASK2_DIR/sub-109, sub-201   (held-out VALDO 2021 Task 2 subjects, CC BY-NC-SA 4.0)
#         build/case_table.tsv                 (which subjects are trainer patients)
# Output: data/tutorial_pics.js                (window.CMB_TUTORIAL_PICS; loaded only when the tutorial opens)
#
# Run   : ~/miniconda3/envs/medizin/bin/python build/04_tutorial_pictures.py
#
# Every picture comes from a VALDO subject that is NOT one of the 57 trainer patients and has NO microbleed in the
# expert mask, so a lookalike shown here is never an answer of the trainer. The examples were picked by eye from
# contact sheets of the 15 held-out subjects; the ring is placed from the data (darkest spot / dark region near the
# picked point). Same display as the trainer (01_prepare_cases.py): radiological view, grey window 0.5-99.5 percentile.
# "Calcium" is a likely reading of a dark spot in the choroid plexus; without a CT it is not proven.
# ---------------------------------------------------------------------------
import base64, io, json, os
import numpy as np, nibabel as nib
from scipy import ndimage
from PIL import Image

VALDO = os.environ.get("VALDO_TASK2_DIR", "/home/uchralt/data/extern/valdo2021/Task2")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "tutorial_pics.js")

# find: "blob" = dark spot around the seed, "region" = dark area (signal loss), "dot" = only the darkest voxel
# key: subject, slice (0-based, display order = lowest first), centre of the cut-out (column, row), half size in mm,
#      seed of the ring (column, row), how the ring is found, extra mm around the found spot
PICS = {
    "calcium": dict(sub="sub-109", z=15, centre=(300, 330), half_mm=30, seed=(313, 343), find="blob", margin_mm=3,
                    label="choroid plexus in the ventricle"),
    "base":    dict(sub="sub-201", z=76, centre=(250, 175), half_mm=38, seed=(250, 150), find="region", margin_mm=2,
                    label="above the sinuses and the orbits"),
    "edge":    dict(sub="sub-201", z=117, centre=(300, 128), half_mm=24, seed=(312, 112), find="dot", margin_mm=3.5,
                    label="on the edge of the brain"),
}

table = [l.rstrip("\n").split("\t") for l in open(os.path.join(HERE, "case_table.tsv"))]
head = table[0]
trainer = {r[0] for r in table[1:] if r[head.index("trainer_patient")] == "yes"}


def load(sub):
    t2s = nib.as_closest_canonical(nib.load(f"{VALDO}/{sub}/{sub}_space-T2S_desc-masked_T2S.nii.gz"))
    ref = nib.as_closest_canonical(nib.load(f"{VALDO}/{sub}/{sub}_space-T2S_CMB.nii.gz"))
    img = np.ascontiguousarray(np.asarray(t2s.dataobj, np.float32)[::-1, ::-1, :].transpose(2, 1, 0))
    lo, hi = np.percentile(img[img > 0], (0.5, 99.5))
    return t2s, (np.clip((img - lo) / (hi - lo), 0, 1) * 255).round().astype(np.uint8), int((np.asarray(ref.dataobj) > 0).sum())


out = {}
for key, p in PICS.items():
    assert p["sub"] not in trainer, p["sub"]
    assert not os.path.exists(os.path.join(HERE, "..", "data", f"case_{p['sub']}.js")), p["sub"]
    t2s, g, n_cmb = load(p["sub"])
    assert n_cmb == 0, f"{p['sub']} has expert microbleeds"
    mm = float(t2s.header.get_zooms()[0]); h = int(round(p["half_mm"] / mm))
    cx, cy = p["centre"]; x0, y0 = cx - h, cy - h
    sl = g[p["z"]].astype(np.float32) / 255
    sx, sy = p["seed"]; r = int(round(3 / mm))
    win = np.where(sl > 0, sl, 1.0)[sy - r:sy + r + 1, sx - r:sx + r + 1]    # outside the brain (0) does not count
    j, i = np.unravel_index(win.argmin(), win.shape); my, mx = sy - r + j, sx - r + i      # darkest voxel near the seed
    yy, xx = np.mgrid[:sl.shape[0], :sl.shape[1]]
    near = np.hypot(xx - mx, yy - my) * mm <= (6 if p["find"] == "blob" else 25)   # only look this far from the darkest voxel
    if p["find"] == "blob":     # a dark spot: darker than 0.25, inside the brain
        dark = (sl < 0.25) & (sl > 0) & near
    else:                        # a dark region (signal loss): darker than 0.2, inside the filled brain outline, small bits removed
        dark = ndimage.binary_opening((sl < 0.2) & ndimage.binary_fill_holes(sl > 0), iterations=2) & near
    lab, _ = ndimage.label(dark)
    comp = lab == lab[my, mx]
    if not lab[my, mx] or p["find"] == "dot":    # "dot": the ring sits on the darkest voxel (it touches the dark rim of the brain)
        comp = np.zeros_like(dark); comp[my, mx] = True
    ys, xs = np.nonzero(comp)
    ccx, ccy = xs.mean(), ys.mean()
    radius_mm = float(np.sqrt(((xs - ccx) ** 2 + (ys - ccy) ** 2).max()) * mm) + p["margin_mm"]
    crop = g[p["z"], y0:y0 + 2 * h, x0:x0 + 2 * h]
    buf = io.BytesIO(); Image.fromarray(crop).save(buf, format="PNG", optimize=True)
    out[key] = {"subject": p["sub"], "slice": p["z"] + 1, "nSlices": int(g.shape[0]), "width": int(crop.shape[1]), "height": int(crop.shape[0]),
                "voxelMm": [round(mm, 4), round(float(t2s.header.get_zooms()[1]), 4)], "sliceMm": round(float(t2s.header.get_zooms()[2]), 2),
                "ring": [round(ccx - x0, 1), round(ccy - y0, 1), round(radius_mm, 1)], "label": p["label"],
                "png": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")}
    print(key, p["sub"], "slice", p["z"] + 1, "ring", out[key]["ring"], "crop", crop.shape, "png", len(buf.getvalue()), "bytes")

with open(OUT, "w") as f:
    f.write("// Made by build/04_tutorial_pictures.py. Lookalike pictures of held-out VALDO subjects without microbleeds "
            "(not trainer patients; VALDO 2021 Task 2, CC BY-NC-SA 4.0).\n")
    f.write("window.CMB_TUTORIAL_PICS = " + json.dumps(out, separators=(",", ":")) + ";\n")
print(OUT, os.path.getsize(OUT), "bytes")
