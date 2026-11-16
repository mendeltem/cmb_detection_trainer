"""Builds the clip "Microbleed or vessel? Scroll." of the CMB Detection Trainer (16.11.2026): voice, Manim render, mp4.

    ~/miniconda3/envs/medizin/bin/python build/vessel_clip/02_make_clip.py voice          # beats + Kokoro voice af_heart (env tts)
    ~/miniconda3/envs/medizin/bin/python build/vessel_clip/02_make_clip.py render [audit]  # 1080p (audit: 640x360, layout check)
    ~/miniconda3/envs/medizin/bin/python build/vessel_clip/02_make_clip.py assemble       # data/vessel_clip.mp4 + data/vessel_clip.jpg

Run 01_vessel_images.py first. Needs the manim_film engine (blackbeard_wikki/tools/general/manim_film/src) and the lecture
scenes (lecture_1118/film/algo.py). Intermediates go to build/vessel_clip/work/ (not in git).
Voice: the lecture's text for this slide (film/short_beats.py "cmb_vessel"); beat 1 says how thick the slices are and,
from the data, whether the microbleed is gone on the next slice."""
import json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]; WORK = HERE / "work"
FILM = Path.home() / "data/work/lehre/lecture_1118/film"; E = Path.home() / "blackbeard_wikki/tools/general/manim_film/src"
TTS = Path.home() / "miniconda3/envs/tts/bin/python"; FF = Path.home() / "miniconda3/envs/tts/bin/ffmpeg"; MANIM = Path.home() / "miniconda3/envs/manim/bin/manim"
KEY, CLS = "cmb_vessel", "CmbVesselTrainer"


def voice():
    I = json.loads((WORK / "img/vv/info.json").read_text())
    gone = "gone on the next slice" if I["bleed"]["seen_slices"] == 1 else "gone after a few slices"
    beats = ["Is every dark dot a micro-bleed? No. On a single slice, a micro-bleed and a vessel cut across look the {same} same.",
             f"So {{scroll}} scroll through the slices. Here, each slice is {['zero', 'one', 'two', 'three', 'four', 'five'][round(I['voxel_mm'][2])]} millimetres thick. "
             f"The micro-bleed is {{gone}} {gone}. The vessel {{stays}} goes on, slice after slice, and it moves.",
             "From the {side} side, the micro-bleed is a ball, and the vessel is a line.",
             "Mark the vessel, and you have a {fp} false positive. Calcium, and the edges near {bone} bone and air, can fool us the same way."]
    (WORK / "beats").mkdir(parents=True, exist_ok=True)
    (WORK / f"beats/{KEY}_beats.json").write_text(json.dumps([{"say": b} for b in beats], indent=1))
    (WORK / "chapters.txt").write_text(f"scene.py {CLS} {KEY}\n")      # the voice tool reads the keys from here
    subprocess.run([str(TTS), str(E / "voice.py"), str(WORK)], check=True, env=dict(os.environ, KOKORO_DEVICE="cpu"))


def render(audit):
    env = dict(os.environ, FILM_DIR=str(WORK), PYTHONPATH=f"{E}:{HERE}:{FILM}", OMP_NUM_THREADS="1", CUDA_VISIBLE_DEVICES="")
    env.update(AUDIT="1", W="640", H="360", FPS="12") if audit else env.update(W="1920", H="1080")
    (WORK / "check").mkdir(exist_ok=True)
    r = subprocess.run(["nice", "-n", "5", str(MANIM), "render", "--disable_caching", "--format", "mp4", "--media_dir", str(WORK / "media"), "-o", CLS,
                        str(HERE / "scene.py"), CLS], env=env, capture_output=True, text=True, cwd=str(WORK))
    (WORK / f"check/render_{CLS}.out").write_text(r.stdout + r.stderr)
    bad = re.findall(r"LATE.*|Traceback.*|Error.*", r.stdout + r.stderr)
    print(CLS, "rc", r.returncode, bad[:5])
    if bad: sys.exit(1)


def assemble():
    n = len(json.loads((WORK / f"beats/{KEY}_beats.json").read_text()))
    lst = WORK / "check/concat.txt"; lst.write_text("".join(f"file '{WORK}/audio_beats/{KEY}_{i}.wav'\n" for i in range(n)))
    video = WORK / f"media/videos/scene/1080p30/{CLS}.mp4"        # not the 360p audit render
    clip, poster = REPO / "data/vessel_clip.mp4", REPO / "data/vessel_clip.jpg"
    subprocess.run([str(FF), "-nostdin", "-loglevel", "error", "-y", "-i", str(video), "-f", "concat", "-safe", "0", "-i", str(lst), "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ac", "1",
                    "-shortest", "-movflags", "+faststart", str(clip)], check=True)
    subprocess.run([str(FF), "-nostdin", "-loglevel", "error", "-y", "-ss", "7", "-i", str(clip), "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "5", str(poster)], check=True)
    print(clip, clip.stat().st_size, "bytes;", poster, poster.stat().st_size, "bytes")


if __name__ == "__main__":
    step = sys.argv[1]
    if step == "voice": voice()
    elif step == "render": render(len(sys.argv) > 2 and sys.argv[2] == "audit")
    elif step == "assemble": assemble()
