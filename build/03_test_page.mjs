// 03_test_page.mjs
// ---------------------------------------------------------------------------
// Step 3: drive the page in a headless browser and check what it shows.
//
// Input : index.html, data/, build/test_expected.json (from step 2)
// Output: PASS / FAIL lines on the screen, build/test_results.txt,
//         screenshots (PNG) in build/screenshots/
//
// Run   : ~/.nvm/versions/node/v22.22.2/bin/node build/03_test_page.mjs
//
// Needs the "playwright" package and a headless Chromium. Where they are can
// be set with the environment variables PLAYWRIGHT_DIR and CHROMIUM_PATH.
// The page is served by a tiny local web server started here (like GitHub
// Pages); one part of the test opens it from file:// as well.
// ---------------------------------------------------------------------------
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

// ---- settings --------------------------------------------------------------
const BUILD = path.dirname(fileURLToPath(import.meta.url));
const PAGE_DIR = path.dirname(BUILD);
const SHOTS = process.env.SHOT_DIR || path.join(BUILD, "screenshots");
const PLAYWRIGHT_DIR = process.env.PLAYWRIGHT_DIR || "/home/uchralt/.hermes/hermes-agent/node_modules/playwright";
const CHROMIUM_PATH = process.env.CHROMIUM_PATH ||
  path.join(process.env.HOME, ".cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell");
const STORAGE_KEY = "cmb-detection-trainer-v1";
const PAGE_URL_ARG = process.env.PAGE_URL || null;          // e.g. the live GitHub Pages address: only the short live check

fs.mkdirSync(SHOTS, { recursive: true });
const expected = JSON.parse(fs.readFileSync(path.join(BUILD, "test_expected.json"), "utf8"));
const ALL_IDS = Object.keys(expected.cases);
const { chromium } = createRequire(import.meta.url)(PLAYWRIGHT_DIR);

// ---- a tiny static web server ------------------------------------------------
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".jpg": "image/jpeg", ".png": "image/png", ".json": "application/json", ".mp4": "video/mp4", ".md": "text/markdown" };
const server = http.createServer((req, res) => {
  const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  const file = path.join(PAGE_DIR, p === "/" ? "index.html" : p);
  if (!file.startsWith(PAGE_DIR) || !fs.existsSync(file) || fs.statSync(file).isDirectory()){ res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const BASE = PAGE_URL_ARG || `http://127.0.0.1:${server.address().port}/`;

// ---- small helpers ---------------------------------------------------------
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  [" + detail + "]" : ""}`);
}
const near = (a, b, tol = 1e-9) => (a === null || b === null ? a === b : Math.abs(a - b) <= tol);
const shot = (page, name, options = {}) => page.screenshot({ path: path.join(SHOTS, name + ".png"), ...options });
async function openPage(context, query = "?test=1", url = BASE) {
  const page = await context.newPage();
  page.problems = []; page.requests = []; page.dialogs = 0;
  page.on("console", m => { if (m.type() === "error") page.problems.push("console: " + m.text()); });
  page.on("pageerror", e => page.problems.push("pageerror: " + e.message));
  page.on("request", r => page.requests.push(r.url()));
  page.on("dialog", d => { page.dialogs++; d.dismiss(); });
  await page.goto(url + query);
  await page.waitForFunction(() => document.documentElement.dataset.ready === "1", null, { timeout: 30000 });
  return page;
}
const frames = page => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
const hook = (page, fn, ...args) => page.evaluate(([fn, args]) => window.__cmbTest[fn](...args), [fn, args]);
const st = page => page.evaluate(() => ({ id: window.__cmbTest.state.id, slice: window.__cmbTest.state.slice, scored: window.__cmbTest.state.scored }));
async function open(page, id) {
  const ok = await hook(page, "openPatient", id);
  await frames(page);
  return ok;
}
async function scoreViaButton(page) {
  await page.click("#btnScore");
  await page.waitForSelector("#modal:not([hidden])");
  await page.click("#modalOk");
  await page.waitForSelector("#f1Value");
  await frames(page);
}
async function noSideScroll(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
}
// Is the slice really drawn (not a black canvas)? Mean grey of the middle of the picture canvas.
async function pictureMean(page) {
  await frames(page);
  return page.evaluate(() => {
    const c = document.getElementById("cvImg"), w = c.width, h = c.height;
    const d = c.getContext("2d").getImageData(Math.round(w * 0.35), Math.round(h * 0.35), Math.round(w * 0.3), Math.round(h * 0.3)).data;
    let s = 0; for (let i = 0; i < d.length; i += 4) s += d[i];
    return s / (d.length / 4);
  });
}
// colour of the ring canvas at the centre of a voxel
async function overlayAt(page, x, y) {
  await frames(page);
  return page.evaluate(([x, y]) => {
    const cv = document.getElementById("cv"), rect = cv.getBoundingClientRect(), p = window.__cmbTest.voxelToClient(x, y), dpr = window.devicePixelRatio || 1;
    return [...cv.getContext("2d").getImageData(Math.round((p.x - rect.left) * dpr), Math.round((p.y - rect.top) * dpr), 1, 1).data];
  }, [x, y]);
}
async function goToSlice(page, z) { await hook(page, "setSlice", z); await page.waitForFunction(() => !!window.__cmbTest.currentImage()); await frames(page); }
async function clickVoxel(page, x, y) { const p = await hook(page, "voxelToClient", x, y); await page.mouse.click(p.x, p.y); await frames(page); }
const pageText = (page, sel) => page.$eval(sel, e => e.textContent);
function hand(tp, fp, fn) { return tp + fp + fn === 0 ? 1 : 2 * tp / (2 * tp + fp + fn); }

const browser = await chromium.launch({ executablePath: CHROMIUM_PATH });
const BROWSER_VERSION = browser.version();

// ===========================================================================
// Short check of a live address (PAGE_URL=...): loads, one patient, scoring works
// ===========================================================================
if (PAGE_URL_ARG) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await openPage(ctx, "?test=1&patient=sub-311");
  check("live: page loads without errors", page.problems.length === 0, page.problems.join(" | "));
  check("live: sub-311 opened", (await st(page)).id === "sub-311");
  check("live: slice picture drawn", (await pictureMean(page)) > 10);
  const e = expected.cases["sub-311"];
  await hook(page, "setMarkers", e.centroidClicks);
  await scoreViaButton(page);
  check("live: all centroids marked gives F1 1.000", (await pageText(page, "#f1Value")) === "1.000");
  check("live: algorithm F1 as computed in Python", near(+(await page.$eval("#algoF1", el => el.dataset.value)), e.algo.f1, 1e-9));
  await shot(page, "live_score");
  await ctx.close(); await browser.close(); server.close();
  const failed = results.filter(r => !r.ok).length;
  console.log(`\n${results.length - failed} of ${results.length} live checks passed`);
  process.exit(failed ? 1 : 0);
}

// ===========================================================================
// 1. First visit: tutorial, layout on a laptop
// ===========================================================================
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await openPage(ctx, "");
  check("first visit: page loads without console errors", page.problems.length === 0, page.problems.join(" | "));
  check("first visit: tutorial opens by itself", await page.$eval("#tut", e => !e.hidden));
  await page.waitForFunction(() => !document.getElementById("tutCv").hidden, null, { timeout: 5000 }).catch(() => {});
  check("tutorial: example picture shown", await page.$eval("#tutCv", e => !e.hidden && e.width > 100));
  check("tutorial: the clip is not loaded before it is played (preload=none)",
        !page.requests.some(u => u.includes("vessel_clip.mp4")) && (await page.$eval("#tutVid", v => v.preload)) === "none");
  await shot(page, "02_tutorial_step1");
  // every step in order: its title, what it shows, one screenshot each
  const TITLES = ["What to look for", "The expert's answer", "Size: what counts as one microbleed", "Lookalike 1 of 4: a vessel",
                  "Lookalike 2 of 4: calcium", "Lookalike 3 of 4: air and bone", "Lookalike 4 of 4: a dark edge", "How it works here",
                  "Reading your score", "Why the count matters"];
  check("tutorial: 10 steps", (await pageText(page, "#tutStep")).endsWith(`of ${TITLES.length}`), await pageText(page, "#tutStep"));
  await page.waitForFunction(() => !!window.CMB_TUTORIAL_PICS, null, { timeout: 5000 }).catch(() => {});
  const shown = () => page.evaluate(() => ({ canvas: !document.getElementById("tutCv").hidden ? document.getElementById("tutCv").width : 0,
                                             video: !document.getElementById("tutVid").hidden, fig: !document.getElementById("tutFig").hidden,
                                             cap: document.getElementById("tutCap").textContent, text: document.getElementById("tutText").textContent }));
  // all tutorial pictures come from VALDO subjects that are not trainer patients (no data/case_<id>.js, not in the index)
  const tutSubjects = await page.evaluate(() => [window.CMB_TUTORIAL.subject, ...Object.values(window.CMB_TUTORIAL_PICS || {}).map(p => p.subject)]);
  const notTrainer = id => !ALL_IDS.includes(id) && !fs.existsSync(path.join(PAGE_DIR, "data", `case_${id}.js`));
  check("tutorial: 4 pictures loaded (example slice + 3 lookalikes)", tutSubjects.length === 4, tutSubjects.join(", "));
  check("tutorial: no picture subject is a trainer patient", tutSubjects.every(notTrainer), tutSubjects.join(", "));
  for (let k = 1; k < TITLES.length; k++){
    await page.click("#tutNext"); await frames(page);
    const title = await pageText(page, "#tutTitle"), v = await shown();
    check(`tutorial step ${k + 1}: "${TITLES[k]}"`, title === TITLES[k], title);
    if (k === 1) check("tutorial step 2: picture with the expert's ring", v.canvas > 100 && v.cap.includes("sub-102"));
    if (k === 2){
      check("tutorial step 3: zoomed picture of the example microbleed", v.canvas > 100 && v.cap.includes("24 mm"));
      check("tutorial step 3: size classes and the example's size", ["< 2 mm", "2–5 mm", "> 5 mm", "4.7 mm", "class 2–5 mm"].every(x => v.text.includes(x)));
      check("tutorial step 3: tiny ones missed most (4 of 10, 79 of 121 as in the README)", v.text.includes("4 of 10") && v.text.includes("79 of 121"));
    }
    if (k === 3){
      check("tutorial step 4: the clip is shown, the canvas hidden", v.video && v.canvas === 0);
      const vid = await page.$eval("#tutVid", e => ({ src: e.querySelector("source").getAttribute("src"), poster: e.getAttribute("poster"), controls: e.controls, auto: e.autoplay }));
      check("tutorial step 4: <video> refers to data/vessel_clip.mp4, controls, no autoplay", vid.src === "data/vessel_clip.mp4" && vid.controls && !vid.auto && vid.poster === "data/vessel_clip.jpg");
      const mp4 = path.join(PAGE_DIR, "data/vessel_clip.mp4"), size = fs.existsSync(mp4) ? fs.statSync(mp4).size : 0;
      check("tutorial step 4: data/vessel_clip.mp4 exists, under 8 MB", size > 100000 && size < 8e6, String(size));
      const res = await page.evaluate(async () => { const r = await fetch("data/vessel_clip.mp4", { method: "HEAD" }); return [r.status, r.headers.get("content-type")]; });
      check("tutorial step 4: the clip is served (200, video/mp4)", res[0] === 200 && res[1] === "video/mp4", res.join(" "));
      const poster = await page.evaluate(async () => (await fetch("data/vessel_clip.jpg")).status);
      check("tutorial step 4: poster picture served", poster === 200);
      check("tutorial step 4: data credit under the clip (VALDO, CC BY-NC-SA 4.0, changes made)", v.cap.includes("VALDO") && v.cap.includes("CC BY-NC-SA 4.0") && v.cap.includes("changes made") && v.cap.includes("sub-102"));
      const canH264 = await page.$eval("#tutVid", e => e.canPlayType('video/mp4; codecs="avc1.640028, mp4a.40.2"'));
      if (canH264){
        const dur = await page.$eval("#tutVid", e => new Promise(r => { e.addEventListener("loadedmetadata", () => r(e.duration), { once: true }); e.load(); setTimeout(() => r(-1), 8000); }));
        check("tutorial step 4: the clip loads in the browser (about 31 s)", dur > 25 && dur < 40, String(dur));
      } else check("tutorial step 4: H.264 not in this headless Chromium build: file checked with ffprobe instead", true, "canPlayType empty");
    }
    if (k >= 4 && k <= 6){
      const key = ["calcium", "base", "edge"][k - 4];
      const sub = await page.evaluate(k => window.CMB_TUTORIAL_PICS[k].subject, key);
      check(`tutorial step ${k + 1}: picture with a ring, subject ${sub} is not a trainer patient`, v.canvas > 100 && v.cap.includes(sub) && notTrainer(sub) && v.cap.includes("no microbleed in the expert mask"));
    }
    if (k === 7) check("tutorial step 8: text only, no picture", !v.fig);
    if (k === 8){
      check("tutorial step 9: drawn example shown", v.canvas > 100 && v.cap.includes("Drawn example"));
      check("tutorial step 9: precision 0.75, recall 0.60, F1 0.67 = 2*3/(2*3+1+2)", ["3 / 4 = 0.75", "3 / 5 = 0.60", "= 0.67"].every(x => v.text.includes(x)) && Math.abs(hand(3, 1, 2) - 0.667) < 0.001);
      check("tutorial step 9: 'the algorithm was better this time' explained", v.text.includes("same scan") && v.text.includes("same rule"));
    }
    if (k === 9){
      check("tutorial step 10: more than 4 microbleeds, five sources with DOI links", v.text.includes("more than 4 microbleeds") &&
            (await page.$$eval("#tutText a[href^='https://doi.org/']", a => a.length)) === 5);
    }
    await shot(page, k === 1 ? "03_tutorial_step2_answer" : `03_tutorial_step${k + 1}`);
  }
  check("tutorial: last step has a Start button", (await pageText(page, "#tutNext")) === "Start");
  check("tutorial: Skip is hidden on the last step", await page.$eval("#tutSkip", e => e.hidden));
  await page.click("#tutBack"); await frames(page);
  check("tutorial: Back goes one step back", (await pageText(page, "#tutTitle")) === TITLES[TITLES.length - 2]);
  await page.click("#tutNext"); await frames(page);
  await page.click("#tutNext");
  check("tutorial: closes", await page.$eval("#tut", e => e.hidden));
  check("tutorial: no console errors", page.problems.length === 0, page.problems.join(" | "));
  await page.reload(); await page.waitForFunction(() => document.documentElement.dataset.ready === "1");
  await frames(page);
  check("tutorial: not shown again after a reload", await page.$eval("#tut", e => e.hidden));
  check("all requests stay on the page's own address (no internet needed)", page.requests.every(u => u.startsWith(BASE)), page.requests.find(u => !u.startsWith(BASE)) || "");
  check("no native alert / confirm", page.dialogs === 0);
  await shot(page, "01_start_laptop");
  await ctx.close();
}
{
  // Skip in the middle of the tutorial closes it and counts as seen
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await openPage(ctx, "");
  await page.click("#tutNext"); await page.click("#tutNext"); await page.click("#tutNext"); await frames(page);
  check("tutorial: Skip shown in the middle (step 4)", await page.$eval("#tutSkip", e => !e.hidden));
  await page.click("#tutSkip");
  check("tutorial: Skip closes it", await page.$eval("#tut", e => e.hidden));
  await page.reload(); await page.waitForFunction(() => document.documentElement.dataset.ready === "1"); await frames(page);
  check("tutorial: after Skip not shown again", await page.$eval("#tut", e => e.hidden));
  await ctx.close();
}
{
  // every tutorial step on a phone: no sideways scrolling, the dialog fits the width; one screenshot per step
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await openPage(ctx, "");
  await page.waitForFunction(() => !!window.CMB_TUTORIAL_PICS, null, { timeout: 5000 }).catch(() => {});
  let wide = [];
  for (let k = 0; k < 10; k++){
    await frames(page);
    const w = await page.$eval(".tutbox", b => b.scrollWidth <= b.clientWidth + 1);
    if (!w || !(await noSideScroll(page))) wide.push(k + 1);
    await shot(page, `20_phone_tutorial_step${k + 1}`);
    if (k < 9) await page.tap("#tutNext");
  }
  check("phone: all 10 tutorial steps without sideways scrolling", wide.length === 0, wide.join(","));
  check("phone tutorial: no errors", page.problems.length === 0, page.problems.join(" | "));
  await ctx.close();
}

// ===========================================================================
// 2. Every patient: the page counts like Python
// ===========================================================================
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await openPage(ctx);
  const index = await page.evaluate(() => window.CMB_INDEX);
  check("index lists 57 patients", index.cases.length === 57 && ALL_IDS.length === 57, `${index.cases.length}`);
  let bad = [], badAlgo = [], badCentroid = [], badMixed = [], badDup = [], badEmpty = [], badPic = [], badIndex = [];
  for (const id of ALL_IDS) {
    const e = expected.cases[id];
    if (!(await open(page, id))) { bad.push(id + " (not opened)"); continue; }
    const c = await hook(page, "getCase");
    if (c.nRef !== e.nRef || c.tolerance.slices !== e.tolSlices || JSON.stringify(c.classes) !== JSON.stringify(e.classes)) bad.push(id);
    const a = await hook(page, "algoScoreNow");
    if (a.tp !== e.algo.tp || a.fp !== e.algo.fp || a.fn !== e.algo.fn || a.dup !== e.algo.dup || !near(a.f1, e.algo.f1, 1e-12) ||
        JSON.stringify(a.cls) !== JSON.stringify(e.algoFoundClasses)) badAlgo.push(id);
    const row = index.cases.find(r => r.id === id);
    if (!near(row.algoF1, e.algo.f1, 1e-4) || row.nRef !== e.nRef) badIndex.push(id);
    await hook(page, "setMarkers", e.centroidClicks);
    let s = await hook(page, "ownScoreNow");
    if (s.tp !== e.nRef || s.fp !== 0 || s.f1 !== 1) badCentroid.push(id);
    await hook(page, "setMarkers", []);
    s = await hook(page, "ownScoreNow");
    if (s.f1 !== (e.nRef === 0 ? 1 : 0)) badEmpty.push(id);
    await hook(page, "setMarkers", e.mixedClicks);
    s = await hook(page, "ownScoreNow");
    if (s.tp !== e.mixed.tp || s.fp !== e.mixed.fp || s.fn !== e.mixed.fn || !near(s.f1, e.mixed.f1, 1e-12) || !near(s.f1, hand(s.tp, s.fp, s.fn), 1e-12)) badMixed.push(id);
    await hook(page, "setMarkers", e.dupClicks);
    s = await hook(page, "ownScoreNow");
    if (s.tp !== e.dups.tp || s.dup !== e.dups.dup || s.fp !== e.dups.fp || !near(s.f1, e.dups.f1, 1e-12)) badDup.push(id);
    await hook(page, "setMarkers", []);
    const im = await hook(page, "currentImage");
    if (!im || im.w !== c.width || im.h !== c.height) badPic.push(id);
  }
  check("every patient: number of microbleeds, size classes, slice tolerance = Python", bad.length === 0, bad.join(" "));
  check("every patient: algorithm TP/FP/FN/duplicates/F1 and found per size class = Python", badAlgo.length === 0, badAlgo.join(" "));
  check("index: algorithm F1 and microbleed count = Python", badIndex.length === 0, badIndex.join(" "));
  check("every patient: a click on every centroid gives F1 1.000, no false alarm", badCentroid.length === 0, badCentroid.join(" "));
  check("every patient: no marker gives F1 0 (1 when there is nothing to find)", badEmpty.length === 0, badEmpty.join(" "));
  check("every patient: half the centroids + 2 far clicks = Python and = 2TP/(2TP+FP+FN)", badMixed.length === 0, badMixed.join(" "));
  check("every patient: a second click next to a found microbleed is a duplicate, not counted", badDup.length === 0, badDup.join(" "));
  check("every patient: slice picture loaded with the size of the data file", badPic.length === 0, badPic.join(" "));
  check("only one patient file kept in memory", (await hook(page, "loadedCaseIds")).length === 1 && (await hook(page, "caseScriptCount")) === 0);
  const meanAlgo = ALL_IDS.reduce((s, id) => s + expected.cases[id].algo.f1, 0) / ALL_IDS.length;
  check("algorithm mean F1 in the index = mean of the Python values", near(index.algorithm.meanF1, meanAlgo, 1e-4), `${index.algorithm.meanF1} vs ${meanAlgo.toFixed(4)}`);
  // all slices of one patient per site load
  for (const id of ["sub-101", "sub-218", "sub-305"]) {
    await open(page, id);
    const n = (await hook(page, "getCase")).nSlices;
    await page.waitForFunction(n => window.__cmbTest.imagesLoaded() + window.__cmbTest.imagesFailed() >= n, n, { timeout: 60000 }).catch(() => {});
    const got = await hook(page, "imagesLoaded"), failed = await hook(page, "imagesFailed");
    check(`${id}: all ${n} slice pictures load`, got === n && failed === 0, `${got} loaded, ${failed} failed`);
  }
  check("part 2 without console errors", page.problems.length === 0, page.problems.join(" | "));
  await ctx.close();
}

// ===========================================================================
// 3. Marking with the mouse, scoring, the result on the screen (laptop)
// ===========================================================================
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await openPage(ctx, "?test=1&patient=sub-207");
  check("?patient=sub-207 opens that patient", (await st(page)).id === "sub-207");
  check("address is cleaned after use", !(await page.evaluate(() => location.search.includes("patient="))));
  check("slice picture is drawn (not black)", (await pictureMean(page)) > 10);
  const e = expected.cases["sub-207"];
  // keys, wheel, slider
  const s0 = (await st(page)).slice;
  await page.mouse.move(700, 450);
  await page.keyboard.press("ArrowUp"); check("arrow up: next slice", (await st(page)).slice === s0 + 1);
  await page.keyboard.press("PageDown"); check("page down: 5 slices lower", (await st(page)).slice === s0 - 4);
  const cvBox = await page.$eval("#cv", el => { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.move(cvBox.x, cvBox.y);
  await page.mouse.wheel(0, -120); await frames(page);
  check("mouse wheel up: higher slice", (await st(page)).slice === s0 - 3);
  const z0 = await page.evaluate(() => window.__cmbTest.view.zoom);
  await page.keyboard.down("Control"); await page.mouse.wheel(0, -200); await page.keyboard.up("Control"); await frames(page);
  check("Ctrl + wheel zooms in", (await page.evaluate(() => window.__cmbTest.view.zoom)) > z0);
  const pan0 = await page.evaluate(() => window.__cmbTest.view.panX);
  await page.mouse.move(cvBox.x, cvBox.y); await page.mouse.down(); await page.mouse.move(cvBox.x + 60, cvBox.y + 20, { steps: 5 }); await page.mouse.up(); await frames(page);
  check("drag moves the picture and places no marker", (await page.evaluate(() => window.__cmbTest.view.panX)) !== pan0 && (await hook(page, "markers")).length === 0);
  await page.click("#zoomFit"); await frames(page);
  // click the first 5 microbleeds at their centroid, one far point, remove and set it again
  const clicks = e.centroidClicks.slice(0, 5);
  for (const [x, y, z] of clicks) { await goToSlice(page, z); await clickVoxel(page, x, y); }
  check("five clicks: five markers", (await hook(page, "markers")).length === 5);
  const [fx, fy, fz] = e.farClicks[0];
  await goToSlice(page, fz); await clickVoxel(page, fx, fy);
  check("click in empty brain: a sixth marker", (await hook(page, "markers")).length === 6);
  await clickVoxel(page, fx, fy);
  check("click on the ring again removes it", (await hook(page, "markers")).length === 5);
  await clickVoxel(page, fx, fy);
  check("marker list under the picture", (await page.$$("#markList button[data-jump]")).length === 6);
  await page.click("#markList button[data-jump='0']"); await frames(page);
  check("marker list: jump to marker 1 goes to its slice", (await st(page)).slice === clicks[0][2]);
  await shot(page, "04_marking");
  await page.evaluate(() => window.scrollTo(0, 0));
  await scoreViaButton(page);
  const tp = 5, fp = 1, fn = e.nRef - 5, f1 = hand(tp, fp, fn);
  check("score: F1 on the screen = 2TP/(2TP+FP+FN) by hand", (await pageText(page, "#f1Value")) === f1.toFixed(3), `${await pageText(page, "#f1Value")} vs ${f1.toFixed(3)}`);
  const sc = await hook(page, "getScore");
  check("score: TP 5, FP 1, FN " + fn, sc.tp === 5 && sc.fp === 1 && sc.fn === fn);
  check("score: table rows show the counts", (await pageText(page, "#rowTP")).includes("5") && (await pageText(page, "#rowFP")).includes("1"));
  const algoShown = +(await page.$eval("#algoF1", el => el.dataset.value));
  check("score: algorithm F1 = Python", near(algoShown, e.algo.f1, 1e-12), `${algoShown}`);
  const verdict = await page.$eval("#verdict", el => el.dataset.verdict);
  const want = Math.round(f1 * 1000) > Math.round(e.algo.f1 * 1000) ? "win" : Math.round(f1 * 1000) < Math.round(e.algo.f1 * 1000) ? "lose" : (1 < e.algo.fp ? "lose" : 1 > e.algo.fp ? "win" : "tie");
  check("score: verdict line fits the numbers", verdict === want, `${verdict} vs ${want}`);
  const headText = await pageText(page, "#verdict .head");
  check("score: verdict text", (want === "lose" && headText === "The algorithm was better this time") || (want === "win" && headText === "You beat the algorithm") || (want === "tie" && headText.startsWith("A tie")), headText);
  // recall by size class
  const found = [0, 0, 0]; const cls = await page.evaluate(() => { const C = window.CMB_CASES["sub-207"]; return C.clusters.map(c => c.size_class); });
  for (const st_ of sc.foundBy.map((m, ci) => [m, ci])) if (st_[0] >= 0) found[["<2", "2-5", ">5"].indexOf(cls[st_[1]])]++;
  check("score: recall by size class row (< 2 mm)", (await pageText(page, "#rowCls0")).includes(`${found[0]}/${e.classes[0]}`), await pageText(page, "#rowCls0"));
  check("score: recall by size class row (2-5 mm)", (await pageText(page, "#rowCls1")).includes(`${found[1]}/${e.classes[1]}`), await pageText(page, "#rowCls1"));
  check("score: patient locked (badge, no new marker on click)", !(await page.$eval("#lockBadge", el => el.hidden)));
  await clickVoxel(page, fx + 20, fy);
  check("score: a click after scoring adds nothing", (await hook(page, "markers")).length === 6);
  // overlay colours: hit cross at a centroid (green), false alarm ring (red)
  await page.click("#zoomFit"); await page.click("#fillRef"); await goToSlice(page, clicks[0][2]);
  const px = await overlayAt(page, clicks[0][0], clicks[0][1]);
  check("overlay: found microbleed drawn green", px[1] > 120 && px[0] < 80 && px[3] > 60, px.join(","));
  const missedCi = sc.foundBy.findIndex(m => m < 0);
  const mc = await page.evaluate(ci => window.CMB_CASES["sub-207"].clusters[ci].voxels.slice(0, 3), missedCi);
  await goToSlice(page, mc[2]);
  const pm = await overlayAt(page, mc[0], mc[1]);
  check("overlay: missed microbleed drawn blue", pm[2] > 150 && pm[0] < 100 && pm[3] > 60, pm.join(","));
  await page.click("#fillRef");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.click("#refList button[data-ref='0']"); await frames(page);
  check("expert list: Jump goes to the microbleed's slice", (await st(page)).slice === e.centroidClicks[0][2]);
  await shot(page, "06_score_screen");
  await shot(page, "06b_score_screen_full_page", { fullPage: true });
  await page.click("#btnAlgo"); await frames(page);
  check("algorithm view: legend counts are the algorithm's", (await pageText(page, "#legend")).includes(String(e.algo.tp)) && (await pageText(page, "#sliceLabel")).includes("vs expert"));
  await shot(page, "07_algorithm_detections");
  await page.click("#btnAlgo");
  // progress
  check("progress: 1 of 57 done", (await page.$eval("#progDone", el => el.dataset.value)) === "1");
  check("progress: mean F1 = this F1", near(+(await page.$eval("#progMean", el => el.dataset.value)), f1, 1e-12));
  check("progress: recall by size counts", (await page.$eval("#progCls1", el => el.dataset.found)) === String(found[1]) && (await page.$eval("#progCls1", el => el.dataset.total)) === String(e.classes[1]));
  // a negative patient, no marker: "Correct: none"
  await page.click("#btnNext");
  await page.waitForFunction(() => !window.__cmbTest.isLoading() && window.__cmbTest.state.id !== "sub-207", null, { timeout: 20000 }).catch(() => {});
  await frames(page);
  check("Next patient opens another patient", (await st(page)).id !== "sub-207");
  await open(page, "sub-104");
  await scoreViaButton(page);
  check("patient without microbleeds, no marker: 'Correct: none', F1 1.000", (await pageText(page, ".f1box .lab")) === "Correct: none" && (await pageText(page, "#f1Value")) === "1.000");
  check("same with the algorithm (no detection): a tie", (await page.$eval("#verdict", el => el.dataset.verdict)) === "tie");
  await open(page, "sub-105");
  await scoreViaButton(page);
  check("sub-105 (no microbleed, algorithm 3 false alarms), no marker: you beat the algorithm", (await page.$eval("#verdict", el => el.dataset.verdict)) === "win");
  await open(page, "sub-233");
  await hook(page, "setMarkers", [e.farClicks[0].map((v, i) => Math.min(v, [100, 100, 50][i]))]);
  await scoreViaButton(page);
  check("patient without microbleeds, one marker: F1 0 and 'No microbleeds here'", (await pageText(page, "#f1Value")) === "0.000" && (await pageText(page, ".f1box .lab")) === "No microbleeds here");
  check("same, algorithm with 7 false alarms: you win on fewer false alarms", (await page.$eval("#verdict", el => el.dataset.verdict)) === "win");
  await shot(page, "08_negative_patient");
  // pooled numbers after 4 patients
  const P = [[5, 1, fn], [0, 0, 0], [0, 0, 0], [0, 1, 0]];
  const sums = P.reduce((a, b) => a.map((v, i) => v + b[i]), [0, 0, 0]);
  check("progress: pooled F1 = sum over first tries", near(+(await page.$eval("#progPooled", el => el.dataset.value)), hand(...sums), 1e-12));
  check("progress: mean F1 of 4 first tries", near(+(await page.$eval("#progMean", el => el.dataset.value)), (f1 + 1 + 1 + 0) / 4, 1e-12));
  check("progress: beat the algorithm 3 of 4 (or as computed)", (await page.$eval("#progBeat", el => el.dataset.value)) === String((want === "win" ? 1 : 0) + 2));
  // a second try does not change the first-try numbers
  await page.click("#btnRetry"); await page.click("#modalOk"); await frames(page);
  await scoreViaButton(page);
  check("another try: mean F1 unchanged (first tries only)", near(+(await page.$eval("#progMean", el => el.dataset.value)), (f1 + 1 + 1 + 0) / 4, 1e-12));
  // reload: progress and the scored patient come back
  await page.reload(); await page.waitForFunction(() => document.documentElement.dataset.ready === "1"); await frames(page);
  check("reload: same patient, still scored", (await st(page)).id === "sub-233" && (await st(page)).scored);
  check("reload: progress kept", (await page.$eval("#progDone", el => el.dataset.value)) === "4");
  // patient list
  await page.click("#pickBtn"); await frames(page);
  check("patient list: 57 rows", (await page.$$("#pickTable tbody tr")).length === 57);
  const hidden = await page.$$eval("#pickTable tbody tr", trs => trs.filter(tr => tr.querySelector(".hidden-val")).length);
  check("patient list: microbleed count hidden for the 53 patients not scored", hidden === 53, String(hidden));
  await page.click("#pickSite button[data-site='2']"); await frames(page);
  check("patient list: site 2 filter = 27 rows", (await page.$$("#pickTable tbody tr")).length === 27);
  await page.click("#pickSite button[data-site='all']");
  await page.click("#pickTable th[data-sort='first']"); await frames(page);
  const firstRow = await page.$eval("#pickTable tbody tr", tr => tr.dataset.id);
  check("patient list: sort by my first score puts a scored patient on top", ["sub-207", "sub-104", "sub-105", "sub-233"].includes(firstRow), firstRow);
  await shot(page, "09_patient_list");
  await page.click("#pickTable tr[data-id='sub-216']");
  await page.waitForFunction(() => !window.__cmbTest.isLoading() && window.__cmbTest.state.id === "sub-216", null, { timeout: 20000 }).catch(() => {});
  await frames(page);
  check("patient list: a click opens the patient", (await st(page)).id === "sub-216");
  // leaving an unscored patient with markers asks first
  await hook(page, "setMarkers", [[10, 10, 10]]);
  await page.click("#btnSkip");
  check("leaving with unscored markers asks first", await page.$eval("#modal", el => !el.hidden));
  await page.click("#modalCancel");
  check("cancel: patient stays", (await st(page)).id === "sub-216" && (await hook(page, "markers")).length === 1);
  // random order: no repeats until all are done
  const order = await page.evaluate(() => {
    const t = window.__cmbTest, ids = t.index.cases.map(c => c.id), seen = new Set(), saveRound = t.state.progress.round.slice();
    t.state.progress.round = [];
    for (let i = 0; i < ids.length - 1; i++){ const id = t.pickRandom(); seen.add(id); t.state.progress.round.push(id); }
    const last = t.pickRandom();
    t.state.progress.round.push(t.state.id);
    const fresh = t.pickRandom();
    const result = { distinct: seen.size, last, noneLeft: last === null, current: t.state.id, freshOk: !!fresh, roundAfter: t.state.progress.round.length };
    t.state.progress.round = saveRound;
    return result;
  });
  check("random order: 56 different patients before a repeat, then none left but the one on the screen", order.distinct === 56 && order.noneLeft);
  check("random order: when all are done a new round starts", order.freshOk && order.roundAfter === 0);
  // reset
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.click("#resetBtn");
  check("reset asks in the page", await page.$eval("#resetBox", el => !!el));
  await shot(page, "10_reset_confirmation");
  await page.click("#resetYes"); await page.waitForFunction(() => !window.__cmbTest.isLoading()); await frames(page);
  check("reset: progress is empty", (await page.$eval("#progDone", el => el.dataset.value)) === "0");
  check("part 3 without console errors, no native dialog", page.problems.length === 0 && page.dialogs === 0, page.problems.join(" | "));
  await ctx.close();
}

// ===========================================================================
// 4. Broken saves, blocked storage, missing files, file://
// ===========================================================================
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript(([key]) => {
    if (!sessionStorage.getItem("seeded")){
      sessionStorage.setItem("seeded", "1");
      localStorage.setItem(key, JSON.stringify({ v: 1, settings: { tutorialSeen: true },
        current: { id: "sub-999", slice: 5, scored: true, markers: "x" },
        progress: { patients: { "sub-311": { first: { f1: 7, tp: 1, fp: 0, fn: 0, cls: [0, 0, 1] } }, "sub-101": { first: { f1: 0.5, tp: 99, fp: 0, fn: 0, cls: [0, 0, 0] } },
                                "sub-313": { first: { f1: 1, tp: 1, fp: 0, fn: 0, dup: 0, cls: [0, 1, 0] }, best: 1, tries: 1 } },
                    history: [{ id: "nope", f1: 1, algo: 1 }, { id: "sub-313", f1: 1, algo: 1 }], round: ["sub-313", "sub-313", "x"] } }));
    }
  }, [STORAGE_KEY]);
  const page = await openPage(ctx);
  check("damaged save: page loads without errors", page.problems.length === 0, page.problems.join(" | "));
  check("damaged save: only the valid patient is kept", (await page.$eval("#progDone", el => el.dataset.value)) === "1");
  check("damaged save: unknown patient ignored, a random patient opened", (await st(page)).id !== "sub-999" && !(await st(page)).scored);
  await ctx.close();
}
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript(() => { localStorage.setItem("cmb-detection-trainer-v1", "{not json"); });
  const page = await openPage(ctx);
  check("save that is not JSON: page works", page.problems.length === 0 && (await st(page)).id !== null);
  await ctx.close();
}
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript(() => {
    Object.defineProperty(window, "localStorage", { get(){ throw new Error("blocked"); } });
    Object.defineProperty(window, "sessionStorage", { get(){ throw new Error("blocked"); } });
  });
  const page = await openPage(ctx, "?test=1&patient=sub-311");
  check("storage blocked: patient opens", (await st(page)).id === "sub-311");
  await hook(page, "setMarkers", expected.cases["sub-311"].centroidClicks);
  await scoreViaButton(page);
  check("storage blocked: scoring works", (await pageText(page, "#f1Value")) === "1.000");
  check("storage blocked: footer says so", (await pageText(page, "#footStorage")).includes("blocks local storage"));
  check("storage blocked: no errors", page.problems.length === 0, page.problems.join(" | "));
  await ctx.close();
}
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.route("**/data/case_sub-216.js", r => r.abort());
  await ctx.route("**/data/img/sub-218/**", r => r.abort());
  const page = await openPage(ctx, "?test=1&patient=sub-311");
  page.problems = [];
  const ok = await hook(page, "openPatient", "sub-216");
  check("missing data file: openPatient fails, the patient before stays", ok === false && (await st(page)).id === "sub-311");
  check("missing data file: a message in the page", !(await page.$eval("#toast", el => el.hidden)));
  const ok2 = await hook(page, "openPatient", "sub-218");
  check("missing slice pictures: the patient before stays", ok2 === false && (await st(page)).id === "sub-311");
  check("page still works after the failures", (await pictureMean(page)) > 10);
  await ctx.close();
}
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const fileUrl = pathToFileURL(path.join(PAGE_DIR, "index.html")).href;
  const page = await openPage(ctx, "?test=1&patient=sub-101", fileUrl);
  await page.waitForFunction(() => window.__cmbTest.imagesLoaded() > 10, null, { timeout: 20000 }).catch(() => {});
  check("file://: page opens a patient and loads its slice pictures", (await st(page)).id === "sub-101" && (await hook(page, "imagesLoaded")) > 10);
  await hook(page, "setMarkers", expected.cases["sub-101"].mixedClicks);
  await scoreViaButton(page);
  check("file://: scoring works (= Python)", (await pageText(page, "#f1Value")) === expected.cases["sub-101"].mixed.f1.toFixed(3));
  check("file://: no errors", page.problems.length === 0, page.problems.join(" | "));
  await ctx.close();
}

// ===========================================================================
// 5. Phone (390 x 844, touch) and other window sizes
// ===========================================================================
async function touch(cdp, type, pts) { await cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map((p, i) => ({ x: p.x, y: p.y, id: i })) }); }
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  const page = await openPage(ctx, "?test=1&patient=sub-311");
  const cdp = await ctx.newCDPSession(page);
  check("phone: no sideways scrolling", await noSideScroll(page));
  check("phone: quick buttons next to the picture", await page.$eval("#quickBar", el => getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 40));
  check("phone: slice picture drawn", (await pictureMean(page)) > 10);
  await shot(page, "11_phone_start");
  const e = expected.cases["sub-311"];
  const [cx, cy, cz] = e.centroidClicks[0];
  await goToSlice(page, cz);
  let p = await hook(page, "voxelToClient", cx, cy);
  await page.touchscreen.tap(p.x, p.y); await frames(page);
  check("phone: a tap places a marker", (await hook(page, "markers")).length === 1);
  // one finger up: higher slices
  const s0 = (await st(page)).slice;
  const v = await page.$eval("#cv", el => { const r = el.getBoundingClientRect(); return { x: r.left + r.width * 0.5, y: r.top + r.height * 0.7 }; });
  await touch(cdp, "touchStart", [v]);
  for (let k = 1; k <= 6; k++) await touch(cdp, "touchMove", [{ x: v.x, y: v.y - k * 10 }]);
  await touch(cdp, "touchEnd", []); await frames(page);
  const s1 = (await st(page)).slice;
  check("phone: one finger up scrolls to higher slices, no marker", s1 > s0 && (await hook(page, "markers")).length === 1, `${s0} -> ${s1}`);
  // two fingers apart: zoom
  const z0 = await page.evaluate(() => window.__cmbTest.view.zoom);
  await touch(cdp, "touchStart", [{ x: v.x - 30, y: v.y - 100 }, { x: v.x + 30, y: v.y - 100 }]);
  for (let k = 1; k <= 6; k++) await touch(cdp, "touchMove", [{ x: v.x - 30 - k * 10, y: v.y - 100 }, { x: v.x + 30 + k * 10, y: v.y - 100 }]);
  await touch(cdp, "touchEnd", []); await frames(page);
  check("phone: two fingers apart zoom in, no marker", (await page.evaluate(() => window.__cmbTest.view.zoom)) > z0 * 1.5 && (await hook(page, "markers")).length === 1);
  await page.tap("#quickUp"); await frames(page);
  check("phone: quick button ▲ goes one slice up", (await st(page)).slice === s1 + 1);
  await goToSlice(page, cz);
  await shot(page, "12_phone_marking_zoomed");
  await page.tap("#quickFit"); await frames(page);
  check("phone: Fit shows the whole slice again", (await page.evaluate(() => window.__cmbTest.view.zoom)) === 1);
  await page.tap("#btnScore"); await page.tap("#modalOk"); await page.waitForSelector("#f1Value"); await page.waitForTimeout(300);
  const vis = await page.evaluate(() => {
    const a = document.getElementById("f1Value").getBoundingClientRect(), b = document.getElementById("btnNext").getBoundingClientRect();
    return a.top >= 0 && b.bottom <= window.innerHeight;
  });
  check("phone: after Score the F1 and Next patient are on the screen", vis);
  check("phone: F1 1.000 for the one microbleed", (await pageText(page, "#f1Value")) === "1.000");
  await shot(page, "13_phone_score");
  await shot(page, "13b_phone_score_full_page", { fullPage: true });
  check("phone: no sideways scrolling after scoring", await noSideScroll(page));
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.tap("#pickBtn"); await frames(page);
  check("phone: patient list without sideways scrolling", await page.$eval("#pickTable", t => t.scrollWidth <= t.parentElement.clientWidth + 1));
  await shot(page, "14_phone_patient_list");
  await page.tap("#pickClose");
  await page.tap("#tutBtn"); await page.waitForTimeout(400);
  await shot(page, "15_phone_tutorial");
  check("phone: no errors", page.problems.length === 0, page.problems.join(" | "));
  await ctx.close();
}
for (const [w, h, name, touchDev] of [[1000, 700, "16_small_laptop", false], [820, 1180, "17_tablet", true], [844, 390, "18_phone_sideways", true], [1920, 1080, "19_full_hd", false]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: touchDev, hasTouch: touchDev });
  const page = await openPage(ctx, "?test=1&patient=sub-216");
  check(`${w}x${h}: no sideways scrolling`, await noSideScroll(page));
  const vh = await page.$eval("#view", el => el.getBoundingClientRect().height);
  check(`${w}x${h}: picture at least 220 px high and fits the window`, vh >= 220 && vh <= h, String(Math.round(vh)));
  await hook(page, "setMarkers", expected.cases["sub-216"].mixedClicks);
  await scoreViaButton(page);
  check(`${w}x${h}: score = Python`, (await pageText(page, "#f1Value")) === expected.cases["sub-216"].mixed.f1.toFixed(3));
  await page.evaluate(() => window.scrollTo(0, 0));
  await shot(page, name);
  check(`${w}x${h}: no errors`, page.problems.length === 0, page.problems.join(" | "));
  await ctx.close();
}

await browser.close();
server.close();
const failed = results.filter(r => !r.ok);
const lines = results.map(r => `${r.ok ? "PASS" : "FAIL"}  ${r.name}${r.detail ? "  [" + r.detail + "]" : ""}`);
fs.writeFileSync(path.join(BUILD, "test_results.txt"),
  `Test of the CMB Detection Trainer, ${new Date().toISOString()}\nChromium ${BROWSER_VERSION}, Node ${process.version}\n\n` +
  lines.join("\n") + `\n\n${results.length - failed.length} of ${results.length} checks passed\n`);
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
