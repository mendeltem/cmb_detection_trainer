# Licence of the data in this repository: CC BY-NC-SA 4.0

The files in `data/`, the screenshots in `build/screenshots/`, and the case tables, JSON files and test results in `build/`
are derived from the public training data of the VALDO 2021 challenge, Task 2 (cerebral microbleeds):

> Sudre, Carole Hélène; Van Wijnen, Kimberlin; Dubost, Florian; de Groot, Marius; de Bruijne, Marleen (2021).
> Training dataset for the VALDO 2021 challenge - Vascular Lesion Detection. Zenodo. DOI: 10.5281/zenodo.4520773

They are shared under the licence of the source data, **Creative Commons Attribution-NonCommercial-ShareAlike 4.0
International (CC BY-NC-SA 4.0)**, https://creativecommons.org/licenses/by-nc-sa/4.0/ :
give credit as in the README (section "Data, credit and licence", including the ALFA contributors, funding and cohort
references), **non-commercial use only**, **share adaptations under the same licence**.

Changes made: cropping to the non-zero part of the image, grey window, conversion of every axial slice to an 8-bit JPEG picture,
microbleeds counted as 26-connected clusters, detections of an algorithm added.

The code of this repository (index.html, build scripts) is under the MIT licence: see `../LICENSE`.
