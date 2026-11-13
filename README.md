# CMB Detection Trainer

A small web page for practising the detection of **cerebral microbleeds (CMB)** on T2*-weighted MRI.
You scroll through all slices of a patient, click on every microbleed you see, press **Score**, and get

- your **precision, recall and F1** against the expert's reference,
- your **hits, false alarms and misses** drawn on the picture (with a list to jump to each microbleed),
- your **recall per size class** (< 2 mm, 2–5 mm, > 5 mm),
- the F1 of an **algorithm** (a 3D U-Net) on the same scan, counted with the same rule, with a clear line
  "You beat the algorithm" or "The algorithm was better this time".

Then you press **Next patient** and go on, for as long as you like. There are 57 patients; 19 of them have
no microbleed at all.

**Open the trainer:** https://mendeltem.github.io/cmb_detection_trainer/

Sister page: the [WMH Rater Trainer](https://mendeltem.github.io/wmh_trainer/) (white matter hyperintensities on FLAIR).

**For teaching only. Not a medical device. Not for diagnosis or any clinical decision.**

## How to use

Open `index.html` in a browser. Nothing has to be installed and no internet is needed; the page also
works when the folder is served as a static site (for example GitHub Pages).

1. The page opens a random patient. A short tutorial (3 steps) is shown on the first visit; it can be
   opened again with the **Tutorial** button. The longer **How to** panel is closed until you open it.
2. Scroll through all slices (mouse wheel, arrow keys, the slider under the picture). Click on every
   microbleed: a ring marks it. Click the ring again to remove it. Markers on a slice close by are shown
   as a dashed ring, so you do not mark the same microbleed twice.
3. Press **Score**. The expert's microbleeds are shown and the patient is locked.
4. Press **Next patient** for another random patient. No patient is repeated until all 57 are done.

Other things on the page:

- **Show the algorithm's detections**: after scoring, the picture shows the algorithm's clicks against the
  expert instead of yours.
- **Choose patient**: the list of all 57 patients, with a filter by site, sorting, and your scores. The
  number of microbleeds and the algorithm's F1 of a patient are shown only after you have scored it
  (before, they would give the answer away).
- **My progress**: patients done, mean F1, pooled F1, false alarms per patient, how often you beat the
  algorithm, best score, recall per size class (you and the algorithm on the same patients) and a small
  chart of the last scores. The numbers use the **first try** of every patient, so trying a patient again
  does not polish the statistics (a better try becomes your best score).
- **Reset my progress** removes all scores on this device (after a confirmation in the page).
- A link of the form `index.html?patient=sub-207` opens one given patient.
- Progress and the markers you are working on are kept in the browser of this device only
  (`localStorage`). Nothing is uploaded. If the browser blocks storage the page still works, it only
  forgets the progress when it is closed.

On a phone or tablet: a tap marks (or removes) a microbleed, one finger moved up or down scrolls through
the slices, two fingers zoom and move the picture, **Fit** shows the whole slice again. The column to the
right of the picture holds the slice buttons, zoom and Fit and a free margin; a swipe that starts there
scrolls the page.

Keys on a laptop: up / down or left / right arrow = next / previous slice, `PgUp` / `PgDn` = 5 slices,
`+` `-` `0` zoom, `H` hides the markers. Mouse wheel = slice, Ctrl + wheel (or a trackpad pinch) = zoom,
drag = move the picture.

## How the score is counted

- **One microbleed** = one group of reference voxels that touch by a face, an edge or a corner
  (26-connectivity, `scipy.ndimage.label` with a 3 x 3 x 3 structure of ones).
- **Size** = diameter of the sphere with the same volume, d = (6 V / pi)^(1/3), V = number of voxels x voxel
  volume (on the original T2* grid). Size classes: **< 2 mm**, **2–5 mm** (2 and 5 included), **> 5 mm**.
- **Hit**: a marker is a hit if it lies inside a reference microbleed, or at most **2.0 mm** away from one of
  its voxels within the slice and at most **N slices** above or below that voxel, with
  N = max(1, floor(2.0 mm / slice thickness)): 1 slice at sites 1 and 3 (3–4 mm slices), 2 slices at site 2
  (0.8 mm slices).
- Markers and microbleeds are paired **one to one, nearest first**. A second marker on a microbleed that is
  already found is a **duplicate**: shown and reported, but not counted (neither hit nor false alarm).
  Every other marker is a **false alarm**.
- **Precision** = TP / (TP + FP), **recall** = TP / (TP + FN),
  **F1** = 2 TP / (2 TP + FP + FN).
- **Patients without microbleeds** (decision of this trainer): F1 uses the same formula, so every false
  alarm gives F1 = 0. If there is nothing to find and nothing is marked (0 / 0), the page shows
  **"Correct: none"** and counts **F1 = 1**. Recall is "n/a" there. The pooled F1 in "My progress" adds up
  TP, FP and FN over all patients first, so it does not depend on this convention.
- **You against the algorithm**: F1 compared with 3 decimals; if both F1 are the same, fewer false alarms
  wins (this decides most patients without microbleeds); otherwise it is a tie.

## Patients

The 57 patients are the **cross-validation subjects** of VALDO 2021 Task 2 that the chain
[cmb-valdo-chain](https://github.com/mendeltem/cmb-valdo-chain) used (the same 57 cases as the QC page
https://mendeltem.github.io/valdo-cmb-qc/). The other 15 of the 72 public subjects are the chain's held-out
cases; they have no out-of-fold prediction and are not used here (one of them, `sub-102`, gives the
tutorial picture, so the tutorial gives away no answer of a trainer patient). Subjects with 0 microbleeds
are kept on purpose: a trainer needs negatives.

| Site | Patients | with / without CMB | Microbleeds | Voxel (mm) | Slices | Data |
|---|---|---|---|---|---|---|
| 1 (`sub-1xx`) | 8 | 6 / 2 | 32 | 0.45 x 0.45 x 4.0 | 33–34 | 3.6 MB |
| 2 (`sub-2xx`) | 27 | 10 / 17 | 80 | 0.49 x 0.49 x 0.8 | 166–189 | 95.9 MB |
| 3 (`sub-3xx`) | 22 | 22 / 0 | 27 | 1.0 x 1.0 x 3.0–4.0 | 36–49 | 7.1 MB |
| all | **57** | **38 / 19** | **139** (10 < 2 mm, 121 2–5 mm, 8 > 5 mm) | | | 106.7 MB |

The slice counts are after the crop described below. `build/case_table.tsv` lists all 72 subjects and why
each one is used or not.

## Algorithm

**3D U-Net of [cmb-valdo-chain](https://github.com/mendeltem/cmb-valdo-chain)**: two-seed ensemble
(seeds 42 and 1) of the anisotropic 3D U-Net `a03-aniso`, trained 60 epochs on the 0.5 x 0.5 x 1 mm grid of
the chain, 5-fold cross-validation (fixed split, seed 0). **Every patient is predicted by the fold model
that never saw it** (out of fold). Post-processing is the fixed operating cell of the chain: probability
> 0.3, 26-connected components, components below 2 mm³ and above 2100 voxels removed, then the SynthSeg CSF
rule (a component whose majority SynthSeg label is CSF is removed). This is the chain's deliverable
(`ens2-a03-aniso-e60-gd` + CSF rule).

To score it with **exactly the rule of the student**, every remaining component "clicks" once, at its voxel
of highest probability, carried from the U-Net grid to the T2* grid with the two affine matrices. These
clicks go through the same hit rule (2 mm in-plane, ±N slices, one to one, duplicates not counted).

Result over the 57 patients: **mean F1 0.612** (0.549 over the 38 patients with microbleeds), **pooled F1
0.647** (TP 89, FP 47, FN 50); 14 of the 19 patients without microbleeds get no false alarm. By size: 4 of 10
(< 2 mm), 79 of 121 (2–5 mm), 6 of 8 (> 5 mm) found. Per site, pooled F1: site 1 0.607, site 2 0.707,
site 3 0.509. Counted the chain's own way (a component that overlaps a reference microbleed on the U-Net
grid is a hit) the counts are the same for every patient (`build/algorithm_check.tsv`), and the pooled F1
0.647 is the number reported by the chain. In sub-108 the algorithm's components split some microbleeds
(7 duplicates); duplicates are not counted, for the algorithm as for you.

## Pictures and file size

- **Orientation**: radiological view (patient's left on the right side of the picture, front of the head on
  top, slice 1 = lowest slice). The files are stored as LAS; turned with nibabel (`as_closest_canonical`,
  then flips), checked independently with the axis codes of the original files (step 2).
- **Grey window**: 0.5th to 99.5th percentile of the non-zero voxels of each scan, to 8 bit.
- **Crop**: the box around all non-zero voxels of the image plus 4 voxels, over all slices that hold any
  non-zero voxel. The box is taken from the **image only, never from the microbleeds**, and **all slices** in
  it are shown (no slab around the lesions), so the crop gives nothing away. Every reference microbleed lies
  inside the box (checked).
- **Format**: one **JPEG (quality 90)** per slice, loaded as a plain image only when the patient is opened,
  the slice on the screen first and then outwards. Lossless PNG would need about 180 MB for site 2 alone.
  The JPEG error was measured on six patients: mean 1.75 grey values (of 255) in the brain, 99th percentile 7;
  on the reference microbleed voxels mean 2.3, maximum 14. No resampling, no smoothing.
- Data in `data/`: 106.7 MB (6019 files); the 27 site-2 scans are 90 % of it (3–4 MB each, others 0.3–0.5 MB).

## Data, credit and licence

The images and reference annotations are derived from the public training data of the challenge:

> Sudre, Carole Hélène; Van Wijnen, Kimberlin; Dubost, Florian; de Groot, Marius; de Bruijne, Marleen (2021).
> Training dataset for the VALDO 2021 challenge - Vascular Lesion Detection. Zenodo. DOI: 10.5281/zenodo.4520773

Challenge paper: Sudre CH et al., "Where is VALDO? VAscular Lesions Detection and segmentatiOn challenge at MICCAI 2021",
Medical Image Analysis 2024, https://doi.org/10.1016/j.media.2023.103029 (arXiv 2208.07167).

Task 2 data come from the SABRE study, the Rotterdam Scan Study and the ALFA study, **for the ALFA Study**. ALFA contributors:
Müge Akinci, Annabella Beteta, Raffaele Cacciaglia, Alba Cañas, Irene Cumplido, Carme Deulofeu, Ruth Dominguez, Maria Emilio, Carles Falcón, Karine Fauria, Sherezade Fuentes, Juan Domingo Gispert, Oriol Grau-Rivera, José M. González-de-Echávarri, Laura Hernandez, Gema Huesa, Jordi Huguet, Iva Knezevic, Eider M. Arenaza-Urquijo, Eva M Palacios, Paula Marne, Tania Menchón, Marta Milà-Alomà, Carolina Minguillon, José Luis Molinuevo, Grégory Operto, Albina Polo, Gemma Salvadó, Sandra Pradas, Blanca Rodríguez, Aleix Sala-Vila, Gonzalo Sánchez-Benavides, Mahnaz Shekari, Anna Soteras, Marc Suárez-Calvet, Laura Stankeviciute, Marc Vilanova and Natalia Vilor-Tejedor.

Funding acknowledged as requested by the data providers: Wellcome Trust (082464/Z/07/Z), British Heart Foundation (SP/07/001/23603, PG/08/103, PG/12/29/29497 and CS/13/1/30327), Erasmus MC University Medical Center, the Erasmus University Rotterdam, the Netherlands Organization for Scientific Research (NWO) Grant 918-46-615, the Netherlands Organization for Health Research and Development (ZonMW), the Research Institute for Disease in the Elderly (RIDE), and the European Union Seventh Framework Programme (FP7/2007–2013) under grant agreement No. 601055, VPHDARE@IT, the Dutch Technology Foundation STW.

Cohort references: Tillin T, et al. Southall And Brent REvisited: Cohort profile of SABRE. Int J Epidemiol 2012, doi:10.1093/ije/dyq175 ·
Jones S, et al. Cohort profile update: SABRE. Int J Epidemiol 2020, doi:10.1093/ije/dyaa135 · Molinuevo JL, et al. 2016,
doi:10.1016/j.trci.2016.02.003 · Ikram MA, et al. The Rotterdam Scan Study: design update 2016 and main findings.
Eur J Epidemiol 2015, doi:10.1007/s10654-015-0105-7.

**Licence:** the source data are licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0
International License. The slice pictures, the data files in `data/` and this page are adaptations of that
material and are shared under the same licence, **CC BY-NC-SA 4.0**
(https://creativecommons.org/licenses/by-nc-sa/4.0/): **non-commercial use only (NC)**, give credit as above,
**share adaptations under the same licence (SA)**. Changes made: cropping to the non-zero part of the image,
grey window, conversion of every axial slice to an 8-bit JPEG picture, microbleeds counted as 26-connected
clusters, detections of an algorithm added. The same credit and licence are shown in the footer of the page.
**Code licence:** the code of this repository (`index.html` and the build scripts `build/*.py`, `build/*.mjs`) is under the
**MIT licence** (`LICENSE`): free to use, change and share, also commercially, with the copyright notice. The MIT licence does
not cover the data: everything derived from the scans (`data/`, `build/screenshots/`, the case tables and JSON files in `build/`)
stays under CC BY-NC-SA 4.0 (`data/LICENSE.md`).

## Folder layout

```
index.html                          the page (one file, no external libraries)
data/cases.js                       index of the 57 patients (loaded at the start)
data/case_sub-XXX.js                microbleeds, algorithm detections, geometry of one patient (loaded when opened)
data/img/sub-XXX/NNN.jpg            one picture per slice (NNN = slice - 1)
data/tutorial.js                    one slice of the held-out subject sub-102, loaded only when the tutorial opens
build/00_survey_cases.py            step 0: one table row per VALDO Task 2 subject, which ones are used
build/01_prepare_cases.py           step 1: write the files in data/
build/02_make_test_expectations.py  step 2: independent recount, right answers for the page test
build/03_test_page.mjs              step 3: test of the page in a headless browser
build/case_table.tsv                table from step 0
build/cases_meta.json               crop box, grey window, fold and algorithm counts per patient (step 1)
build/algorithm_check.tsv           click rule vs the chain's overlap count, per patient (step 2)
build/test_expected.json            numbers from step 2
build/test_results.txt              the result of the last page test
build/screenshots/                  pictures taken by the page test (PNG)
```

## How the data files were made

Only `index.html` and `data/` are needed to use the page. The scripts in `build/` document how the files in
`data/` were made and can make them again. They are plain numbered scripts, to be run in this order from the
folder of this README:

```
python build/00_survey_cases.py
python build/01_prepare_cases.py
python build/02_make_test_expectations.py
node   build/03_test_page.mjs
```

The Python scripts need `numpy`, `scipy`, `nibabel` and `pillow` (made with Python 3.11.16, nibabel 5.4.2,
NumPy 2.4.6, SciPy 1.17.1, Pillow 12.3.0). They read the public VALDO Task 2 data
(`VALDO_TASK2_DIR`, one folder `sub-XXX` per subject with `sub-XXX_space-T2S_desc-masked_T2S.nii.gz` and
`sub-XXX_space-T2S_CMB.nii.gz`) and the results of the chain (`CMB_CHAIN_DIR`: `dev/split.json`, the
out-of-fold probability maps `ergebnisse/turnier/ens2-a03-aniso-e60-gd/fold*/sub-XXX_pred_proba.nii.gz`,
the SynthSeg maps `dev/synthseg/sub-XXX_synthseg.nii.gz` and, for the check in step 2, the grid labels
`dev/gitter_d/sub-XXX/sub-XXX_label.nii.gz`). Making these chain results (training, SynthSeg) is not part of
this repository; see [cmb-valdo-chain](https://github.com/mendeltem/cmb-valdo-chain). The scripts stop with a
message if a file is missing; they never use other data instead.

Step 2 checks step 1 in an independent way: the microbleeds are found again with a hand-written flood fill
(plain Python) on the original files and placed with the axis codes of the files; the algorithm's components
are found again with the same flood fill on the probability map, size limits, CSF rule and the most certain
voxel are recomputed and carried to the T2* grid with the original affine matrices; the hit rule is written
again in plain Python loops. All 57 patients agree voxel by voxel and detection by detection.

## Test

`build/03_test_page.mjs` serves the folder with a small local web server and drives the page in a headless
Chromium (package `playwright`; places set with `PLAYWRIGHT_DIR` and `CHROMIUM_PATH`). Last run: **122 of 122
checks passed** (Chromium 151, Playwright, Node 22.22.2; the lines are in `build/test_results.txt`). It checks:

- for all 57 patients: number of microbleeds, size classes and slice tolerance in the page = Python; the
  algorithm's TP, FP, FN, duplicates, F1 and found per size class = Python; a click on every centroid gives
  F1 1.000; no marker gives 0 (1 for a patient without microbleeds); half of the centroids plus two clicks
  far from every microbleed and a duplicate click give the values computed in Python and by hand
- real mouse clicks, removing a marker, keys, wheel, Ctrl + wheel, dragging (moves, places no marker), the
  marker list, Score with the in-page question, the numbers, the verdict, recall per size class, the colours
  on the picture, Jump, the algorithm view, the lock after scoring
- patients without microbleeds ("Correct: none", tie and win on fewer false alarms), mean and pooled F1 in
  "My progress", first try only, reload, the patient list (hidden counts, filter, sorting, opening),
  leaving with unscored markers, the random order without repeats and the new round, reset
- damaged and foreign saves, blocked storage, a missing data file and missing slice pictures, the page
  opened from `file://`, all slice pictures of one patient per site
- a phone (390 x 844, touch): tap marks, one finger scrolls the slices, two fingers zoom, the quick buttons,
  F1 and "Next patient" on the screen after scoring, no sideways scrolling; and 1000 x 700, 820 x 1180,
  844 x 390, 1920 x 1080

With `PAGE_URL=https://mendeltem.github.io/cmb_detection_trainer/` the script only runs a short check of the
live page.

Not tested: Firefox, Safari, a real touch device, a real trackpad pinch.
