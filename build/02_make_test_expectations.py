# 02_make_test_expectations.py
# ---------------------------------------------------------------------------
# Step 2: check the data files of step 1 in a SECOND, independent way and write
# the right answers for the browser test (step 3).
#
# Run (from the folder of README.md):  python build/02_make_test_expectations.py
# Reads:  the original VALDO files and U-Net predictions (read-only), data/cases.js, data/case_*.js
# Writes: build/test_expected.json, build/algorithm_check.tsv
#
# "Independent" means:
#   - the microbleeds are found with a hand-written flood fill (plain Python, no
#     scipy) on the ORIGINAL file, and turned into picture positions with the
#     axis codes of the file, not with nibabel's re-orientation;
#   - the algorithm's components are found with the same hand-written flood fill
#     on the thresholded probability map; size limit, CSF rule and the voxel of
#     highest probability are recomputed; the position on the T2* grid is
#     computed with the ORIGINAL affine matrices;
#   - the hit rule is written again in plain Python loops.
# Every number must agree with the data files, voxel by voxel and detection by
# detection. The script stops with an error otherwise.
#
# It also counts the algorithm the way the chain itself does (a component that
# overlaps a reference microbleed on the U-Net grid is a hit) and writes both
# counts side by side to build/algorithm_check.tsv (for the README).
# ---------------------------------------------------------------------------
import json
import math
import os
import random

import nibabel as nib
import numpy as np

VALDO = os.environ.get("VALDO_TASK2_DIR", "/home/uchralt/data/extern/valdo2021/Task2")
CHAIN = os.environ.get("CMB_CHAIN_DIR", "/home/uchralt/data/work/valdo-t2s")
PRED_RUN = "ergebnisse/turnier/ens2-a03-aniso-e60-gd"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
THRESHOLD, MIN_MM3, MAX_VOXELS = 0.3, 2.0, 2100
CSF = {4, 5, 14, 15, 24, 43, 44}
STEPS_26 = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) != (0, 0, 0)]


def read_js(path, marker):
    text = open(path).read()
    return json.loads(text[text.index(marker) + len(marker):].strip().rstrip(";"))


def flood_fill(voxels):
    todo, out = set(voxels), []
    while todo:
        start = todo.pop()
        cluster, queue = [start], [start]
        while queue:
            i, j, k = queue.pop()
            for a, b, c in STEPS_26:
                n = (i + a, j + b, k + c)
                if n in todo:
                    todo.remove(n); cluster.append(n); queue.append(n)
        out.append(cluster)
    return out


def to_picture(ijk, shape, axcodes, crop):
    # file voxel (i, j, k) -> picture (column, row, slice) of the cropped stack.
    # column grows towards the patient's LEFT, row towards the BACK, slice UP.
    i, j, k = ijk
    assert axcodes[0] in "LR" and axcodes[1] in "AP" and axcodes[2] in "SI"
    col = i if axcodes[0] == "L" else shape[0] - 1 - i
    row = j if axcodes[1] == "P" else shape[1] - 1 - j
    sl = k if axcodes[2] == "S" else shape[2] - 1 - k
    return (col - crop["x0"], row - crop["y0"], sl - crop["z0"])


def hit_rule(clusters, markers, mm, tol_mm, tol_sl):
    # plain loops: candidate pairs, nearest first, one to one
    cand = []
    for m_i, m in enumerate(markers):
        for c_i, cl in enumerate(clusters):
            best = None
            for (x, y, z) in cl:
                s = abs(z - m[2])
                if s > tol_sl:
                    continue
                r = math.sqrt(((x - m[0]) * mm[0]) ** 2 + ((y - m[1]) * mm[1]) ** 2)
                if r > tol_mm + 1e-9:
                    continue
                d = math.sqrt(r * r + (s * mm[2]) ** 2)
                best = d if best is None else min(best, d)
            if best is not None:
                cand.append((best, m_i, c_i))
    cand.sort()
    used_m, used_c = {}, {}
    for d, m_i, c_i in cand:
        if m_i not in used_m and c_i not in used_c:
            used_m[m_i] = c_i; used_c[c_i] = m_i
    near = {m_i for _, m_i, _ in cand}
    tp = len(used_c)
    dup = sum(1 for m_i in range(len(markers)) if m_i not in used_m and m_i in near)
    fp = len(markers) - tp - dup
    fn = len(clusters) - tp
    f1 = 1.0 if tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)
    return dict(tp=tp, fp=fp, fn=fn, dup=dup, f1=f1, found=sorted(used_c))


index = read_js(os.path.join(DATA, "cases.js"), "window.CMB_INDEX = ")
expected = {"cases": {}, "algorithm": index["algorithm"]}
check_rows = []
problems = 0
random.seed(0)
for row in index["cases"]:
    sub = row["id"]
    page = read_js(os.path.join(DATA, f"case_{sub}.js"), f'window.CMB_CASES["{sub}"] = ')
    img_nii = nib.load(f"{VALDO}/{sub}/{sub}_space-T2S_desc-masked_T2S.nii.gz")
    ref_nii = nib.load(f"{VALDO}/{sub}/{sub}_space-T2S_CMB.nii.gz")
    axcodes = "".join(nib.aff2axcodes(img_nii.affine))
    shape = img_nii.shape[:3]
    mm = [float(v) for v in img_nii.header.get_zooms()[:3]]
    tol_sl = max(1, int(2.0 // mm[2]))

    # ---- reference microbleeds ----
    ref = np.asanyarray(ref_nii.dataobj)
    mine = flood_fill([tuple(int(v) for v in p) for p in zip(*np.nonzero(ref > 0))])
    mine_pic = sorted(sorted(to_picture(v, shape, axcodes, page["crop"]) for v in cl) for cl in mine)
    theirs = sorted(sorted(tuple(c["voxels"][i:i + 3]) for i in range(0, len(c["voxels"]), 3)) for c in page["clusters"])
    same = mine_pic == theirs
    sizes_ok = all(abs((6 * len(c_v) * mm[0] * mm[1] * mm[2] / math.pi) ** (1 / 3) - c["diameter_mm"]) < 0.01
                   for c_v, c in zip(sorted(theirs, key=len), sorted(page["clusters"], key=lambda c: c["n_voxels"])))
    classes = [0, 0, 0]
    for cl in mine:
        d = (6 * len(cl) * mm[0] * mm[1] * mm[2] / math.pi) ** (1 / 3)
        classes[0 if d < 2 else (1 if d <= 5 else 2)] += 1

    # ---- algorithm ----
    pred_nii = nib.load([p for p in [f"{CHAIN}/{PRED_RUN}/fold{k}/{sub}_pred_proba.nii.gz" for k in range(5)] if os.path.exists(p)][0])
    prob = np.asanyarray(pred_nii.dataobj).astype(np.float64) / 255.0
    seg = np.asanyarray(nib.load(f"{CHAIN}/dev/synthseg/{sub}_synthseg.nii.gz").dataobj).astype(np.int64)
    vox_mm3 = float(np.prod(pred_nii.header.get_zooms()[:3]))
    comps = flood_fill([tuple(int(v) for v in p) for p in zip(*np.nonzero(prob > THRESHOLD))])
    grid_ref = np.asanyarray(nib.load(f"{CHAIN}/dev/gitter_d/{sub}/{sub}_label.nii.gz").dataobj) > 0
    grid_ref_clusters = flood_fill([tuple(int(v) for v in p) for p in zip(*np.nonzero(grid_ref))])
    ref_id = {}
    for n_c, cl in enumerate(grid_ref_clusters):
        for v in cl:
            ref_id[v] = n_c
    world_to_file = np.linalg.inv(img_nii.affine)
    markers, overlap_hit_refs, overlap_fp = [], set(), 0
    for cl in comps:
        if len(cl) * vox_mm3 < MIN_MM3 or len(cl) > MAX_VOXELS:
            continue
        labs = [int(seg[v]) for v in cl if seg[v] > 0]
        if not labs:                                    # only background under it: look 3 voxels around
            ring = set()
            for (i, j, k) in cl:
                for a in range(-3, 4):
                    for b in range(-3, 4):
                        for c in range(-3, 4):
                            if max(abs(a), abs(b), abs(c)) <= 3:
                                ring.add((i + a, j + b, k + c))
            # the chain widens with 3 steps of 26-connectivity = the cube of +-3 voxels
            labs = [int(seg[v]) for v in ring if all(0 <= v[q] < seg.shape[q] for q in range(3)) and seg[v] > 0]
        major = max(set(labs), key=lambda l: (labs.count(l), -l)) if labs else 0
        if major in CSF:
            continue
        peak = max(cl, key=lambda v: (prob[v], -v[0], -v[1], -v[2]))
        world = pred_nii.affine @ np.array([*peak, 1.0])
        f = world_to_file @ world
        markers.append((float(prob[peak]), to_picture(tuple(int(round(t)) for t in f[:3]), shape, axcodes, page["crop"])))
        hits = {ref_id[v] for v in cl if v in ref_id}
        overlap_hit_refs |= hits
        overlap_fp += 0 if hits else 1
    markers.sort(key=lambda m: -m[0])
    marker_pos = [m[1] for m in markers]
    same_algo = sorted(marker_pos) == sorted(tuple(a) for a in page["algo"])
    # the page's own order of the microbleeds (the same voxel sets, checked above), so that indices match
    page_order = [[tuple(c["voxels"][i:i + 3]) for i in range(0, len(c["voxels"]), 3)] for c in page["clusters"]]
    s = hit_rule(page_order if same else mine_pic, marker_pos, mm, 2.0, tol_sl)
    a_ok = (s["tp"], s["fp"], s["fn"], s["dup"]) == (row["algoTP"], row["algoFP"], row["algoFN"], row["algoDup"]) and abs(s["f1"] - row["algoF1"]) < 1e-4
    ov_tp, ov_fn = len(overlap_hit_refs), len(grid_ref_clusters) - len(overlap_hit_refs)
    check_rows.append([sub, len(mine), len(grid_ref_clusters), len(marker_pos), s["tp"], s["fp"], s["fn"], s["dup"], round(s["f1"], 3),
                       ov_tp, overlap_fp, ov_fn])
    ok = same and sizes_ok and classes == row["classes"] and len(mine) == row["nRef"] and same_algo and a_ok and tol_sl == page["tolerance"]["slices"]
    problems += not ok
    print(f"{'ok ' if ok else 'BAD'} {sub}: microbleeds {len(mine)} (same voxels: {same}, sizes {sizes_ok}, classes {classes}), "
          f"algorithm {len(marker_pos)} detections (same: {same_algo}) TP {s['tp']} FP {s['fp']} FN {s['fn']} dup {s['dup']} "
          f"F1 {s['f1']:.3f} ({'same' if a_ok else 'DIFFERENT'})  | overlap count on the U-Net grid: TP {ov_tp} FP {overlap_fp} FN {ov_fn}", flush=True)

    # ---- click positions for the browser test ----
    clusters = page["clusters"]
    W, H, N = page["width"], page["height"], page["n_slices"]
    centroid_clicks = [[int(round(c["centroid"][0])), int(round(c["centroid"][1])), int(round(c["centroid"][2]))] for c in clusters]
    cs = hit_rule(theirs, [tuple(p) for p in centroid_clicks], mm, 2.0, tol_sl)
    assert cs["tp"] == len(clusters) and cs["fp"] == 0, f"{sub}: a centroid click is not a hit"
    # two clicks far (> 15 mm) from every microbleed, on the brain (picture not black), not near each other
    far = []
    pic = None
    tries = 0
    while len(far) < 2 and tries < 5000:
        tries += 1
        x, y, z = random.randrange(W), random.randrange(H), random.randrange(N)
        if any(abs(x - f[0]) * mm[0] < 20 and abs(y - f[1]) * mm[1] < 20 for f in far):
            continue
        dmin = min((math.sqrt(((v[0] - x) * mm[0]) ** 2 + ((v[1] - y) * mm[1]) ** 2 + ((v[2] - z) * mm[2]) ** 2)
                    for cl in theirs for v in cl), default=1e9)
        if dmin < 15:
            continue
        if pic is None:
            data_img = np.asanyarray(img_nii.dataobj)
            pic = True
        fi = [x + page["crop"]["x0"], y + page["crop"]["y0"], z + page["crop"]["z0"]]
        i = fi[0] if axcodes[0] == "L" else shape[0] - 1 - fi[0]
        j = fi[1] if axcodes[1] == "P" else shape[1] - 1 - fi[1]
        k = fi[2] if axcodes[2] == "S" else shape[2] - 1 - fi[2]
        if data_img[i, j, k] <= 0:
            continue
        far.append([x, y, z])
    assert len(far) == 2
    half = centroid_clicks[: len(clusters) // 2]
    mixed = hit_rule(theirs, [tuple(p) for p in half + far], mm, 2.0, tol_sl)
    dup_clicks = centroid_clicks + ([centroid_clicks[0][:2] + [centroid_clicks[0][2]]] if clusters else [])
    if clusters:                                   # a second click one voxel beside the first microbleed
        c0 = centroid_clicks[0]
        dup_clicks = centroid_clicks + [[min(W - 1, c0[0] + 1), c0[1], c0[2]]]
    dups = hit_rule(theirs, [tuple(p) for p in dup_clicks], mm, 2.0, tol_sl)
    expected["cases"][sub] = {
        "nRef": len(clusters), "classes": classes, "tolSlices": tol_sl,
        "algo": {k: s[k] for k in ("tp", "fp", "fn", "dup", "f1")},
        "algoFoundClasses": [sum(1 for ci in s["found"] if clusters[ci]["size_class"] == k) for k in ("<2", "2-5", ">5")],
        "centroidClicks": centroid_clicks,
        "farClicks": far,
        "mixedClicks": half + far, "mixed": {k: mixed[k] for k in ("tp", "fp", "fn", "dup", "f1")},
        "dupClicks": dup_clicks, "dups": {k: dups[k] for k in ("tp", "fp", "fn", "dup", "f1")},
    }
    del prob, seg, grid_ref

with open(os.path.join(HERE, "algorithm_check.tsv"), "w") as f:
    f.write("subject\tmicrobleeds_T2S\tmicrobleeds_grid\tdetections\tclick_TP\tclick_FP\tclick_FN\tclick_dup\tclick_F1\toverlap_TP\toverlap_FP\toverlap_FN\n")
    for r in check_rows:
        f.write("\t".join(str(v) for v in r) + "\n")
tp = sum(r[4] for r in check_rows); fp = sum(r[5] for r in check_rows); fn = sum(r[6] for r in check_rows)
otp = sum(r[9] for r in check_rows); ofp = sum(r[10] for r in check_rows); ofn = sum(r[11] for r in check_rows)
print(f"\nclick rule (this trainer): TP {tp} FP {fp} FN {fn} pooled F1 {2 * tp / (2 * tp + fp + fn):.3f}, "
      f"mean F1 {np.mean([r[8] for r in check_rows]):.3f}")
print(f"overlap on the U-Net grid (the chain's own count): TP {otp} FP {ofp} FN {ofn} pooled F1 {2 * otp / (2 * otp + ofp + ofn):.3f}")
json.dump(expected, open(os.path.join(HERE, "test_expected.json"), "w"))
print(f"{len(check_rows)} patients checked, {problems} problems")
if problems:
    raise SystemExit(1)
