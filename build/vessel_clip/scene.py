"""Manim scene of the clip "Microbleed or vessel? Scroll." for the CMB Detection Trainer (16.11.2026).
The scene CmbVessel of the lecture (lecture_1118/film/algo.py), with the same look, beats and text, on VALDO sub-102
(the trainer's tutorial scan, not a trainer patient). Changes for this scan: 7 slices of 4 mm instead of 19 of 0.8 mm;
the counts on screen say "k of n slices" for both dots; the scroll steps are slower; the part label names the trainer.
Numbers: work/img/vv/info.json (01_vessel_images.py). Rendered by 02_make_clip.py (FILM_DIR = build/vessel_clip/work)."""
import json
from engine import *                       # FILM_DIR = build/vessel_clip/work (beats, voice, pictures of this clip)
from algo import Algo                       # lecture scenes (lecture_1118/film on PYTHONPATH)


class CmbVesselTrainer(Algo):
    key = "cmb_vessel"

    def header(self):
        self.number, self.title = 1, "Microbleed or vessel? Scroll."
        t = T(self.title, 36, bold=True).to_corner(UL, buff=.4); p = T("CMB Detection Trainer", 22, DIM).to_corner(UR, buff=.45)
        self.head = VGroup(t, p); self.add(t, p)

    def construct(self):
        I = json.loads((HERE / "img/vv/info.json").read_text()); n = I["slices"]; mid = n // 2; h = 3.0
        mm = I["voxel_mm"][2]
        cb = np.array([-5.35, .45, 0]); cv = np.array([-2.1, .45, 0])
        at = lambda c, xy: c + np.array([(xy[0] - .5) * h, (.5 - xy[1]) * h, 0])
        fb = [ImageMobject(str(HERE / f"img/vv/bleed_{i:02d}.png")).set_height(h).move_to(cb) for i in range(n)]
        fv = [ImageMobject(str(HERE / f"img/vv/vessel_{i:02d}.png")).set_height(h).move_to(cv) for i in range(n)]
        seen_b, seen_v, dv = I["bleed"]["seen"], I["vessel"]["seen"], I["vessel"]["dots"]
        rb = Circle(.24, color=WHITE, stroke_width=3).move_to(at(cb, I["bleed"]["dot"])).set_z_index(5)
        rv = Circle(.24, color=WHITE, stroke_width=3).move_to(at(cv, dv[mid])).set_z_index(5)
        la = T("A ?", 26, DIM).move_to(cb + [0, 1.78, 0]); lv = T("B ?", 26, DIM).move_to(cv + [0, 1.78, 0])
        tw = h / n
        strip = lambda c: VGroup(*[Rectangle(width=tw * .8, height=.16, stroke_width=0, fill_color=GREY_D, fill_opacity=1).move_to(c + [(i - mid) * tw, -1.72, 0]) for i in range(n)])
        sb, sv = strip(cb), strip(cv)
        cur_b = Rectangle(width=tw, height=.3, stroke_color=WHITE, stroke_width=2).move_to(sb[mid]).set_z_index(5)
        cur_v = cur_b.copy().move_to(sv[mid])
        gone = "gone on the next slice" if I["bleed"]["seen_slices"] == 1 else "gone after a few slices"
        texts = [("one slice: two dark dots", GREY_B), (f"microbleed: {gone}", YELLOW_), ("vessel: goes on, and it moves", RED_),
                 ("from the side: ball or line", BLUE_), ("marking a vessel = false positive", RED_), ("also: calcium, edges near bone and air", GREY_B)]
        bx = [Box(t, c, 5.9, .72, 24).move_to([3.75, 1.95 - i * .92, 0]) for i, (t, c) in enumerate(texts)]
        def point(i, *extra, rt=.6):
            self.play(FadeIn(bx[i], shift=LEFT * .25), bx[i].on(), *([bx[i - 1].off()] if i else []), *extra, run_time=rt)
        state = dict(i=mid)
        def show(i, dt):
            """One step of the scroll: both panels jump to slice i, the vessel ring follows the dark dot."""
            self.remove(fb[state["i"]], fv[state["i"]]); self.add(fb[i], fv[i]); state["i"] = i
            rb.set_stroke(opacity=1 if seen_b[i] else .15)
            if seen_b[i]: sb[i].set_fill(YELLOW_)
            if seen_v[i]: sv[i].set_fill(RED_)
            self.play(rv.animate.move_to(at(cv, dv[i])), cur_b.animate.move_to(sb[i]), cur_v.animate.move_to(sv[i]), run_time=dt, rate_func=linear)
        def scroll(seq, t_end):
            seq = list(seq); dt = min(.6, max(.14, (t_end - self.now()) / max(len(seq), 1)))   # thick slices: up to 0.6 s per slice
            for i in seq:
                if self.now() + dt > t_end: break
                show(i, dt)
        mark_t = lambda name: self.starts[self.current] + self.marks[self.current].get(name, 0)
        # beat 0: one slice, two dark dots
        self.beat(0); self.header()
        self.play(FadeIn(fb[mid]), FadeIn(fv[mid]), FadeIn(la), FadeIn(lv), run_time=.7)
        self.to(.3); self.play(Create(rb), Create(rv), run_time=.6)
        self.at("same"); point(0, Indicate(rb, color=WHITE, scale_factor=1.25), Indicate(rv, color=WHITE, scale_factor=1.25))
        # beat 1: scroll
        self.beat(1)
        thick = T(f"{n} slices, each {mm:.0f} mm thick", 22, DIM).move_to([-3.72, -2.95, 0])
        self.at("scroll"); self.play(FadeIn(sb), FadeIn(sv), FadeIn(cur_b), FadeIn(cur_v), FadeIn(thick), run_time=.3)
        scroll(range(mid + 1, n), mark_t("gone"))
        la2 = T("microbleed", 26, YELLOW_, bold=True).move_to(la)
        nb = T(f"{I['bleed']['seen_slices']} of {n} slices\n= {I['bleed']['seen_mm']:.0f} mm", 22, YELLOW_).move_to(cb + [0, -2.3, 0])
        self.at("gone")
        for i in range(n):
            if seen_b[i]: sb[i].set_fill(YELLOW_)
        point(1, FadeOut(la), FadeIn(la2), FadeIn(nb), rt=.4)
        scroll(range(state["i"] - 1, mid - 1, -1), mark_t("stays"))
        lv2 = T("vessel", 26, RED_, bold=True).move_to(lv)
        nv = T(f"{I['vessel']['seen_slices']} of {n} slices\n= {I['vessel']['seen_mm']:.0f} mm", 22, RED_).move_to(cv + [0, -2.3, 0])
        self.at("stays")
        for i in range(n):
            if seen_v[i]: sv[i].set_fill(RED_)
        point(2, FadeOut(lv), FadeIn(lv2), FadeIn(nv), rv.animate.set_color(RED_), rt=.4)
        end = self.starts[1] + self.lens[1] - .2
        scroll(list(range(state["i"] - 1, -1, -1)) + list(range(1, n)) + list(range(n - 2, mid - 1, -1)), end)
        # beat 2: from the side
        self.beat(2)
        side_b = ImageMobject(str(HERE / "img/vv/bleed_side.png")).set_height(h).move_to(cb); side_v = ImageMobject(str(HERE / "img/vv/vessel_side.png")).set_height(h).move_to(cv)
        cap = T(f"seen from the side: {I['side_slices']} slices = {I['side_slices'] * mm:.0f} mm high", 22, DIM).move_to([-3.72, -2.95, 0])
        self.at("side"); point(3, FadeTransform(fb[state["i"]], side_b), FadeTransform(fv[state["i"]], side_v), FadeOut(rb), FadeOut(rv), FadeOut(cur_b), FadeOut(cur_v), FadeOut(thick), FadeIn(cap), rt=.9)
        # beat 3: marking the vessel is a false positive
        self.beat(3)
        b_mid, v_mid = fb[mid].copy(), fv[mid].copy()
        click = Circle(.3, color=YELLOW_, stroke_width=5).move_to(at(cv, dv[mid])).set_z_index(5)
        self.play(FadeTransform(side_b, b_mid), FadeTransform(side_v, v_mid), FadeOut(cap), run_time=.5); self.play(Create(click), run_time=.4)
        frame = Rectangle(width=h + .1, height=h + .1, stroke_color=RED_, stroke_width=5).move_to(cv)
        badge = Box("false positive", RED_, 2.8, .55, 22).move_to([-2.1, -3.1, 0])
        self.at("fp"); point(4, click.animate.set_color(RED_), Create(frame), FadeIn(badge), rt=.6); self.play(badge.on(), run_time=.3)
        self.at("bone"); point(5)
        self.finish()
