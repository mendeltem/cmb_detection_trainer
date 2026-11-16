# Pictures for the clip "Microbleed or vessel? Scroll." of the CMB Detection Trainer (16.11.2026).
# A copy of the lecture script lecture_1118/film/code/07_vessel_vs_bleed.py, moved to the public VALDO scan sub-102:
# the scan of the trainer's tutorial, NOT one of the trainer's 57 patients (the lecture clip uses sub-207, which is one).
# sub-102 has thick slices (4 mm, 35 slices), so the scroll has 7 slices (28 mm) instead of 19 slices of 0.8 mm.
#
# Run:                ~/miniconda3/envs/medizin/bin/python build/vessel_clip/01_vessel_images.py   (from the repo folder)
# Reads (read-only):  ~/data/extern/valdo2021/Task2/sub-102/   (VALDO 2021 Task 2, CC BY-NC-SA 4.0)
# Writes (WORK = build/vessel_clip/work, not in git):
#                     WORK/img/vv/bleed_00.png ... bleed_06.png    7 slices around the one microbleed (expert mask)
#                     WORK/img/vv/vessel_00.png ... vessel_06.png  the same 7 slices around one vessel that crosses them
#                     WORK/img/vv/bleed_side.png, vessel_side.png  both seen from the side (darkest value through a 4.5 mm slab)
#                     WORK/img/vv_all.png                          the four pictures in one (for looking at)
#                     WORK/img/vv/info.json                        on which slices each dot is seen
#
# The vessel has no expert label. It was found in the scan: a dark dot that goes on from slice to slice and moves
# (candidates: dark dots >= 0.30 darker than their surroundings, followed over >= 4 slices; picked by eye from a contact
# sheet: a vessel in a CSF-filled sulcus). Step 3 follows it automatically, so the numbers in the clip come from the data.
import json, os
import numpy as np, nibabel as nib
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont

# ---- settings (change here) -------------------------------------------------------------------------------------------
SUB = "sub-102"
FOLDER = os.path.expanduser(f"~/data/extern/valdo2021/Task2/{SUB}/")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "img")
HALF = 20                                   # half width of the cut-out in voxels (40 voxels of 0.45 mm = 18 mm)
N_SLICES = 7                                # slices in the scroll (7 x 4 mm = 28 mm)
BLEED_CENTRE = (191, 250); BLEED_FIRST = 14     # the only microbleed of the expert mask (slice 17), slices 14 ... 20
VESSEL_CENTRE = (350, 246); VESSEL_FIRST = 14   # the vessel (other hemisphere, in a sulcus), the same slices 14 ... 20
VESSEL_SEED = (346, 243, 18)                # one voxel inside the vessel (x, y, slice)
STEP = 3                                    # the dot may move this many voxels per slice (3 x 0.45 mm per 4 mm slice)
SEEN_IF_DARKER_BY = 0.30                    # the dot counts as "seen" if it is this much darker than its surroundings (0 ... 1)
SIDE_SLICES = 5                             # slices in the side view (5 x 4 mm = 20 mm, about as wide as the cut-out)
SIDE_SLAB = 5                               # half thickness of the slab for the side view, in voxels (10 x 0.45 mm = 4.5 mm)
ZOOM = 10                                   # every voxel becomes 10 x 10 pixels

# ---- Step 1: load the scan and the expert mask ------------------------------------------------------------------------
t2s = nib.as_closest_canonical(nib.load(FOLDER + f"{SUB}_space-T2S_desc-masked_T2S.nii.gz"))
image = np.asarray(t2s.dataobj, dtype=np.float32)
mask = np.asarray(nib.as_closest_canonical(nib.load(FOLDER + f"{SUB}_space-T2S_CMB.nii.gz")).dataobj) > 0
voxel_mm = [float(v) for v in t2s.header.get_zooms()[:3]]
low, high = np.percentile(image[image > 0], [0.5, 99.5])
grey = np.clip((image - low) / (high - low), 0, 1)          # grey values 0 ... 1
os.makedirs(OUT + "/vv", exist_ok=True)


def cut_out(centre, z):
    """One slice around a point, shown the radiological way: front at the top, patient's left on the right."""
    part = grey[centre[0] - HALF:centre[0] + HALF, centre[1] - HALF:centre[1] + HALF, z]
    return np.flipud(part.T)[:, ::-1]


def picture(array, height=None):
    size = (array.shape[1] * ZOOM, height or array.shape[0] * ZOOM)
    if height:    # side view: each 4 mm slice is one block, as thick as it really is (no smoothing between slices)
        return Image.fromarray((array * 255).astype(np.uint8)).resize((array.shape[1], height), Image.NEAREST).resize(size, Image.LANCZOS)
    return Image.fromarray((array * 255).astype(np.uint8)).resize(size, Image.LANCZOS)


def place(centre, x, y):
    """Where a voxel (x, y) lies in the cut-out, as a share 0 ... 1 from the left and from the top."""
    return [round((centre[0] + HALF - 1 - x + .5) / (2 * HALF), 3), round((centre[1] + HALF - 1 - y + .5) / (2 * HALF), 3)]


# ---- Step 2: the microbleed: on which slices does the expert mask show it? --------------------------------------------
bleed_slices = list(range(BLEED_FIRST, BLEED_FIRST + N_SLICES))
labels, n = ndimage.label(mask, np.ones((3, 3, 3)))
number = labels[BLEED_CENTRE[0] - 3:BLEED_CENTRE[0] + 4, BLEED_CENTRE[1] - 3:BLEED_CENTRE[1] + 4, BLEED_FIRST + N_SLICES // 2].max()
bleed = labels == number
bleed_seen = [bool(bleed[:, :, z].any()) for z in bleed_slices]
bx, by, bz = ndimage.center_of_mass(bleed)
for i, z in enumerate(bleed_slices):
    picture(cut_out(BLEED_CENTRE, z)).save(f"{OUT}/vv/bleed_{i:02d}.png")

# ---- Step 3: the vessel: follow the dark dot from slice to slice ------------------------------------------------------
vessel_slices = list(range(VESSEL_FIRST, VESSEL_FIRST + N_SLICES))
around = ndimage.gaussian_filter(grey, (5, 5, 0))            # the surroundings: every slice blurred
track = {}
for direction in (range(VESSEL_SEED[2], vessel_slices[-1] + 1), range(VESSEL_SEED[2] - 1, vessel_slices[0] - 1, -1)):
    x, y = VESSEL_SEED[:2]
    for z in direction:
        window = grey[x - STEP:x + STEP + 1, y - STEP:y + STEP + 1, z]   # the darkest voxel within STEP voxels of the last position
        i, j = np.unravel_index(window.argmin(), window.shape)
        x, y = x - STEP + i, y - STEP + j
        track[z] = (int(x), int(y), float(around[x, y, z] - grey[x, y, z]))
vessel_seen = [track[z][2] > SEEN_IF_DARKER_BY for z in vessel_slices]
for i, z in enumerate(vessel_slices):
    picture(cut_out(VESSEL_CENTRE, z)).save(f"{OUT}/vv/vessel_{i:02d}.png")

# ---- Step 4: both seen from the side (the darkest value through a slab; back on the left, top of the head at the top) ---
def side_view(centre, x_mid, z_first):
    slab = grey[x_mid - SIDE_SLAB:x_mid + SIDE_SLAB, centre[1] - HALF:centre[1] + HALF, z_first:z_first + SIDE_SLICES].min(axis=0)
    return picture(np.flipud(slab.T), height=round(SIDE_SLICES * voxel_mm[2] / voxel_mm[0] * ZOOM))   # true height: 5 x 4 mm = 20 mm

bleed_side = side_view(BLEED_CENTRE, BLEED_CENTRE[0], 15)       # slices 15 ... 19, the microbleed in the middle
vessel_side = side_view(VESSEL_CENTRE, 349, 15)                 # slices 15 ... 19; the slab x 344 ... 353 holds the track (x 353 ... 346)
bleed_side.save(f"{OUT}/vv/bleed_side.png"); vessel_side.save(f"{OUT}/vv/vessel_side.png")

# ---- Step 5: one picture with all four (still version of the deck) ----------------------------------------------------
mid = N_SLICES // 2; S = 2 * HALF * ZOOM; GAP = 16; TOP = 44
SH = bleed_side.height
sheet = Image.new("RGB", (2 * S + GAP, S + SH + 2 * TOP + GAP), (11, 13, 18)); draw = ImageDraw.Draw(sheet)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
for k, (name, colour, top, bottom) in enumerate([("microbleed", (255, 225, 77), f"{OUT}/vv/bleed_{mid:02d}.png", bleed_side),
                                                  ("vessel", (252, 98, 85), f"{OUT}/vv/vessel_{mid:02d}.png", vessel_side)]):
    x0 = k * (S + GAP)
    draw.text((x0 + 8, 6), name + ": one slice", fill=colour, font=font); sheet.paste(Image.open(top).convert("RGB"), (x0, TOP))
    draw.text((x0 + 8, S + TOP + GAP + 6), "from the side", fill=colour, font=font); sheet.paste(bottom.convert("RGB"), (x0, S + 2 * TOP + GAP))
sheet.save(f"{OUT}/vv_all.png")

z_seen = [z for z, s in zip(vessel_slices, vessel_seen) if s]
# ---- Step 6: the numbers for the clip --------------------------------------------------------------------------------
info = {
    "subject": SUB, "side_slices": SIDE_SLICES, "voxel_mm": [round(v, 2) for v in voxel_mm], "cut_out_mm": round(2 * HALF * voxel_mm[0], 1), "slices": N_SLICES,
    "bleed": {"voxels": int(bleed.sum()), "seen": bleed_seen, "seen_slices": int(sum(bleed_seen)), "seen_mm": round(sum(bleed_seen) * voxel_mm[2], 1),
              "dot": place(BLEED_CENTRE, bx, by)},
    "vessel": {"seen": vessel_seen, "seen_slices": int(sum(vessel_seen)), "seen_mm": round(sum(vessel_seen) * voxel_mm[2], 1),
               "dots": [place(VESSEL_CENTRE, track[z][0], track[z][1]) for z in vessel_slices],
               "seen_from_to": [z_seen[0], z_seen[-1]],
               "moves_mm": round(float(np.hypot(track[z_seen[-1]][0] - track[z_seen[0]][0],      # from the first to the last slice it is seen on
                                                 track[z_seen[-1]][1] - track[z_seen[0]][1]) * voxel_mm[0]), 1)},
}
json.dump(info, open(f"{OUT}/vv/info.json", "w"), indent=1)
print(json.dumps({k: (v if k not in ("bleed", "vessel") else {a: b for a, b in v.items() if a not in ("seen", "dots")}) for k, v in info.items()}))
print("bleed seen ", "".join("X" if s else "." for s in bleed_seen))
print("vessel seen", "".join("X" if s else "." for s in vessel_seen))
