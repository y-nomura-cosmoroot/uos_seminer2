#!/usr/bin/env python3
"""analyze_pptx.py — Deep design extraction from a .pptx file.

Outputs a structured JSON describing:
  - theme (color scheme + font scheme, fully resolved)
  - slide size
  - slide master defaults (title/body font sizes)
  - per-slide data:
      background (solid / gradient / image)
      shapes: pos, size, shape_fill (noFill / solid / gradient), text_runs
              with resolved color / fontSize / fontFace / bold / italic
      pictures: pos, size
      layout_hint: one-column / two-column-left-text-right-image / before-after / ...

The goal is to avoid the typical analysis mistakes an LLM makes on pptx XML:
  - Mistaking a text-color `srgbClr` for a shape fill
  - Leaving `schemeClr` references unresolved (e.g. "tx2" instead of "#353E49")
  - Treating a `noFill` textbox with light-colored giant text as a "gray band"
  - Losing gradient stops / angles / alpha
  - Missing `<p:pic>` placements that signal two-column layouts

Usage:
    python analyze_pptx.py <path/to/file.pptx> [--out design_report.json]
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

EMU_PER_INCH = 914400


def emu_to_inch(emu: int | str | None) -> float | None:
    if emu is None:
        return None
    try:
        return round(int(emu) / EMU_PER_INCH, 3)
    except (TypeError, ValueError):
        return None


def unpack_pptx(pptx_path: str, dest: str) -> None:
    """Unzip the pptx into dest directory."""
    subprocess.run(["unzip", "-o", "-q", pptx_path, "-d", dest], check=True)


def read_xml(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_theme(theme_xml: str) -> dict[str, Any]:
    """Resolve the theme color scheme and font scheme to concrete values.

    Returns:
        {
          "color_scheme": {"dk1": "#989998", "lt1": "#FFFFFF", ..., "accent1": "#34B089", ...},
          "font_scheme": {"major_latin": "Calibri Light", "major_ea_jpan": "游ゴシック Light",
                          "minor_latin": "Calibri", "minor_ea_jpan": "游ゴシック"}
        }
    """
    colors: dict[str, str] = {}
    # clrScheme groups: dk1, lt1, dk2, lt2, accent1..6, hlink, folHlink
    scheme_match = re.search(r"<a:clrScheme\b.*?</a:clrScheme>", theme_xml, re.DOTALL)
    if scheme_match:
        scheme = scheme_match.group(0)
        # Each child of clrScheme is a named tag containing either srgbClr or sysClr
        for role_match in re.finditer(
            r"<a:(dk1|lt1|dk2|lt2|accent1|accent2|accent3|accent4|accent5|accent6|hlink|folHlink)>(.*?)</a:\1>",
            scheme,
            re.DOTALL,
        ):
            role = role_match.group(1)
            inner = role_match.group(2)
            srgb = re.search(r'<a:srgbClr\s+val="([0-9A-Fa-f]{6})"', inner)
            sysclr = re.search(r'<a:sysClr\s+val="[^"]+"\s+lastClr="([0-9A-Fa-f]{6})"', inner)
            if srgb:
                colors[role] = "#" + srgb.group(1).upper()
            elif sysclr:
                colors[role] = "#" + sysclr.group(1).upper()

    fonts: dict[str, str] = {}
    for major_minor in ("majorFont", "minorFont"):
        block = re.search(rf"<a:{major_minor}>(.*?)</a:{major_minor}>", theme_xml, re.DOTALL)
        if not block:
            continue
        body = block.group(1)
        latin = re.search(r'<a:latin\s+typeface="([^"]+)"', body)
        if latin:
            fonts[f"{major_minor}_latin"] = latin.group(1)
        for sc_match in re.finditer(r'<a:font\s+script="([^"]+)"\s+typeface="([^"]+)"', body):
            fonts[f"{major_minor}_{sc_match.group(1).lower()}"] = sc_match.group(2)

    return {"color_scheme": colors, "font_scheme": fonts}


def resolve_color(raw_xml: str, theme_colors: dict[str, str]) -> str | None:
    """Given a small XML fragment that begins with a color tag (srgbClr / schemeClr / sysClr),
    return a resolved "#RRGGBB" string. schemeClr "bg1"/"tx1"/"bg2"/"tx2" map through clrMap
    to lt1/dk1/lt2/dk2 — we assume the standard identity map here (which is almost always true).
    """
    m = re.search(r'<a:srgbClr\s+val="([0-9A-Fa-f]{6})"', raw_xml)
    if m:
        return "#" + m.group(1).upper()
    m = re.search(r'<a:sysClr[^>]*lastClr="([0-9A-Fa-f]{6})"', raw_xml)
    if m:
        return "#" + m.group(1).upper()
    m = re.search(r'<a:schemeClr\s+val="([^"]+)"', raw_xml)
    if m:
        role = m.group(1)
        # Standard clrMap aliases
        alias = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}
        role_resolved = alias.get(role, role)
        return theme_colors.get(role_resolved)
    return None


def parse_fill(fragment: str, theme_colors: dict[str, str]) -> dict[str, Any]:
    """Interpret a fill fragment as solid / gradient / image / noFill / theme.

    Important: Line/border properties (`<a:ln>...</a:ln>`) contain their own fill
    (often `<a:noFill/>`). We must NOT mistake that for the shape's fill. Strip out
    `<a:ln>` blocks before evaluating the shape fill, so a gradient-filled shape
    with a noFill border isn't misclassified as "none".
    """
    # Strip out <a:ln>...</a:ln> (line/border, which has its own fill)
    stripped = re.sub(r"<a:ln\b.*?</a:ln>", "", fragment, flags=re.DOTALL)
    # Also ignore self-closing <a:ln/>
    stripped = re.sub(r"<a:ln\s*/>", "", stripped)

    # Check fill types in order of specificity (most-specific first)
    grad = re.search(r"<a:gradFill\b.*?</a:gradFill>", stripped, re.DOTALL)
    if grad:
        gradient = grad.group(0)
        stops = []
        for stop in re.finditer(r"<a:gs\s+pos=\"(\d+)\">(.*?)</a:gs>", gradient, re.DOTALL):
            pos = int(stop.group(1)) / 100000
            inner = stop.group(2)
            color = resolve_color(inner, theme_colors)
            alpha_m = re.search(r'<a:alpha\s+val="(\d+)"', inner)
            alpha = int(alpha_m.group(1)) / 100000 if alpha_m else 1.0
            stops.append({"position": round(pos, 4), "color": color, "alpha": round(alpha, 4)})
        ang_m = re.search(r'<a:lin\s+ang="(-?\d+)"', gradient)
        angle = None
        if ang_m:
            # angle is in 60000ths of a degree
            angle = (int(ang_m.group(1)) / 60000) % 360
        return {"type": "gradient", "stops": stops, "angle_degrees": angle}
    blip = re.search(r"<a:blipFill\b.*?</a:blipFill>", stripped, re.DOTALL)
    if blip:
        return {"type": "image"}
    solid = re.search(r"<a:solidFill>(.*?)</a:solidFill>", stripped, re.DOTALL)
    if solid:
        color = resolve_color(solid.group(1), theme_colors)
        return {"type": "solid", "color": color}
    # Only call it "none" if an explicit noFill remains after stripping lines
    if "<a:noFill/>" in stripped or "<a:noFill />" in stripped:
        return {"type": "none"}
    return {"type": "unspecified"}


def parse_run(rpr_xml: str, text: str, theme_colors: dict[str, str]) -> dict[str, Any]:
    """Parse a <a:r> run, returning style info for its text."""
    size_m = re.search(r'\bsz="(\d+)"', rpr_xml)
    font_size_pt = int(size_m.group(1)) / 100 if size_m else None
    bold = 'b="1"' in rpr_xml
    italic = 'i="1"' in rpr_xml
    latin = re.search(r'<a:latin\s+typeface="([^"]+)"', rpr_xml)
    ea = re.search(r'<a:ea\s+typeface="([^"]+)"', rpr_xml)
    # Text color: the first solidFill inside rPr
    text_color = None
    fill_m = re.search(r"<a:solidFill>(.*?)</a:solidFill>", rpr_xml, re.DOTALL)
    if fill_m:
        text_color = resolve_color(fill_m.group(1), theme_colors)
    return {
        "text": text,
        "font_size_pt": font_size_pt,
        "bold": bold,
        "italic": italic,
        "font_latin": latin.group(1) if latin else None,
        "font_ea": ea.group(1) if ea else None,
        "color": text_color,
    }


def parse_shape(sp_xml: str, theme_colors: dict[str, str]) -> dict[str, Any]:
    """Extract position, size, fill and text runs from a <p:sp> shape."""
    off = re.search(r'<a:off\s+x="(-?\d+)"\s+y="(-?\d+)"/>', sp_xml)
    ext = re.search(r'<a:ext\s+cx="(\d+)"\s+cy="(\d+)"/>', sp_xml)

    # Shape fill: look inside the FIRST <p:spPr>...</p:spPr> block
    sppr_m = re.search(r"<p:spPr\b.*?</p:spPr>", sp_xml, re.DOTALL)
    shape_fill = parse_fill(sppr_m.group(0), theme_colors) if sppr_m else {"type": "unspecified"}

    # Text runs: each <a:r><a:rPr>...</a:rPr><a:t>...</a:t></a:r>
    runs = []
    for run in re.finditer(r"<a:r>\s*<a:rPr\b(.*?)</a:rPr>\s*<a:t>(.*?)</a:t>\s*</a:r>", sp_xml, re.DOTALL):
        runs.append(parse_run(run.group(1), run.group(2), theme_colors))

    combined_text = " ".join(r["text"] for r in runs if r["text"].strip())

    return {
        "pos_inch": {"x": emu_to_inch(off.group(1)) if off else None,
                      "y": emu_to_inch(off.group(2)) if off else None},
        "size_inch": {"w": emu_to_inch(ext.group(1)) if ext else None,
                       "h": emu_to_inch(ext.group(2)) if ext else None},
        "shape_fill": shape_fill,
        "runs": runs,
        "combined_text": combined_text.strip(),
    }


def parse_picture(pic_xml: str) -> dict[str, Any]:
    off = re.search(r'<a:off\s+x="(-?\d+)"\s+y="(-?\d+)"/>', pic_xml)
    ext = re.search(r'<a:ext\s+cx="(\d+)"\s+cy="(\d+)"/>', pic_xml)
    embed = re.search(r'r:embed="([^"]+)"', pic_xml)
    return {
        "pos_inch": {"x": emu_to_inch(off.group(1)) if off else None,
                      "y": emu_to_inch(off.group(2)) if off else None},
        "size_inch": {"w": emu_to_inch(ext.group(1)) if ext else None,
                       "h": emu_to_inch(ext.group(2)) if ext else None},
        "r_embed": embed.group(1) if embed else None,
    }


def parse_slide(slide_xml: str, theme_colors: dict[str, str]) -> dict[str, Any]:
    # Slide background
    bg = None
    bg_m = re.search(r"<p:bg\b.*?</p:bg>", slide_xml, re.DOTALL)
    if bg_m:
        bg = parse_fill(bg_m.group(0), theme_colors)

    shapes = [parse_shape(m.group(0), theme_colors) for m in re.finditer(r"<p:sp\b.*?</p:sp>", slide_xml, re.DOTALL)]
    pictures = [parse_picture(m.group(0)) for m in re.finditer(r"<p:pic\b.*?</p:pic>", slide_xml, re.DOTALL)]

    # Layout hint heuristics
    layout_hint = detect_layout(shapes, pictures)

    return {
        "background": bg,
        "shapes": shapes,
        "pictures": pictures,
        "layout_hint": layout_hint,
    }


def detect_layout(shapes: list[dict[str, Any]], pictures: list[dict[str, Any]]) -> str:
    """Very rough layout classifier to bootstrap the prose section of DESIGN.md."""
    has_big_pic = any(
        p["size_inch"]["w"] and p["size_inch"]["w"] >= 8 for p in pictures if p.get("size_inch")
    )
    text_left = any(
        s["combined_text"]
        and s["pos_inch"].get("x") is not None
        and s["pos_inch"]["x"] < 8
        for s in shapes
    )
    text_right = any(
        s["combined_text"]
        and s["pos_inch"].get("x") is not None
        and s["pos_inch"]["x"] >= 13
        for s in shapes
    )
    ba_labels = set()
    for s in shapes:
        t = s["combined_text"].lower()
        if t.strip() == "before":
            ba_labels.add("before")
        if t.strip() == "after":
            ba_labels.add("after")

    if ba_labels == {"before", "after"}:
        return "before-after-comparison"
    if has_big_pic and text_left and not text_right:
        return "two-column-text-left-image-right"
    if text_left and text_right:
        return "two-column-split"
    return "single-column"


def detect_watermark(shapes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A watermark is a noFill shape containing a very large text run whose color is
    light/pale (e.g. #F7F7F7). Return the first such shape if found."""
    for s in shapes:
        if s["shape_fill"]["type"] != "none":
            continue
        for r in s["runs"]:
            if r["font_size_pt"] and r["font_size_pt"] >= 100:
                color = r.get("color") or ""
                if color and _is_light_color(color):
                    return {
                        "text": r["text"],
                        "font_size_pt": r["font_size_pt"],
                        "color": color,
                        "font": r["font_latin"] or r["font_ea"],
                        "bold": r["bold"],
                        "pos_inch": s["pos_inch"],
                        "size_inch": s["size_inch"],
                    }
    return None


def _is_light_color(hex_color: str) -> bool:
    """Light but not pure white — i.e. plausibly a "barely visible" watermark.

    Pure white text on a gradient or dark background is a title, not a watermark, so we
    exclude very-high luminance. Likewise very dark colors aren't watermarks.
    """
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        # perceived luminance
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        # watermark range: light but not pure white (so it contrasts subtly against white bg)
        return 220 < lum < 253
    except Exception:
        return False


def analyze(pptx_path: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        unpack_pptx(pptx_path, tmp)
        root = Path(tmp)

        theme_path = next(iter(root.glob("ppt/theme/theme1.xml")), None)
        if not theme_path:
            raise FileNotFoundError("ppt/theme/theme1.xml not found — is this a valid .pptx?")
        theme = parse_theme(read_xml(str(theme_path)))

        # Slide size
        pres_path = root / "ppt" / "presentation.xml"
        pres_xml = read_xml(str(pres_path))
        sz_m = re.search(r'<p:sldSz\s+cx="(\d+)"\s+cy="(\d+)"', pres_xml)
        slide_size = {
            "width_inch": emu_to_inch(sz_m.group(1)) if sz_m else None,
            "height_inch": emu_to_inch(sz_m.group(2)) if sz_m else None,
            "width_emu": int(sz_m.group(1)) if sz_m else None,
            "height_emu": int(sz_m.group(2)) if sz_m else None,
        }

        # Slide master (for default text sizes etc.)
        master_xml = read_xml(str(root / "ppt" / "slideMasters" / "slideMaster1.xml"))
        master_title_sz = re.search(r"<p:titleStyle>.*?<a:defRPr\s+sz=\"(\d+)\"", master_xml, re.DOTALL)
        master_body_sz = re.search(r"<p:bodyStyle>.*?<a:defRPr\s+sz=\"(\d+)\"", master_xml, re.DOTALL)

        # Slides
        slides_dir = root / "ppt" / "slides"
        slide_files = sorted(slides_dir.glob("slide*.xml"),
                              key=lambda p: int(re.search(r"(\d+)", p.name).group(1)))
        slides = []
        for sf in slide_files:
            slides.append({
                "name": sf.name,
                **parse_slide(read_xml(str(sf)), theme["color_scheme"]),
            })

        # Detect watermark presence across slides
        for s in slides:
            s["watermark"] = detect_watermark(s["shapes"])

        # Aggregate font usage & color usage
        font_counter: dict[str, int] = {}
        text_color_counter: dict[str, int] = {}
        shape_fill_counter: dict[str, int] = {}
        for s in slides:
            for sh in s["shapes"]:
                ft = sh["shape_fill"]["type"]
                shape_fill_counter[ft] = shape_fill_counter.get(ft, 0) + 1
                if sh["shape_fill"].get("color"):
                    shape_fill_counter[sh["shape_fill"]["color"]] = shape_fill_counter.get(sh["shape_fill"]["color"], 0) + 1
                for r in sh["runs"]:
                    for f in (r.get("font_latin"), r.get("font_ea")):
                        if f:
                            font_counter[f] = font_counter.get(f, 0) + 1
                    if r.get("color"):
                        text_color_counter[r["color"]] = text_color_counter.get(r["color"], 0) + 1

        return {
            "file": os.path.basename(pptx_path),
            "slide_size": slide_size,
            "theme": theme,
            "master_defaults": {
                "title_font_size_pt": int(master_title_sz.group(1)) / 100 if master_title_sz else None,
                "body_font_size_pt": int(master_body_sz.group(1)) / 100 if master_body_sz else None,
            },
            "slides": slides,
            "aggregate": {
                "font_usage": sorted(font_counter.items(), key=lambda kv: -kv[1]),
                "text_color_usage": sorted(text_color_counter.items(), key=lambda kv: -kv[1]),
                "shape_fill_usage": sorted(shape_fill_counter.items(), key=lambda kv: -kv[1]),
            },
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pptx", help="Path to the .pptx file")
    ap.add_argument("--out", default=None, help="Output JSON path (default: stdout)")
    args = ap.parse_args()

    report = analyze(args.pptx)
    js = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(js)
        print(f"Wrote {args.out}")
    else:
        sys.stdout.write(js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())