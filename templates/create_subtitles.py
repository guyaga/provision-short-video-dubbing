"""
Provision Short Video Dubbing - ASS Subtitle Creator
=====================================================
Creates styled ASS (Advanced SubStation Alpha) subtitles from
translated segments with full control over font, colors, outline,
shadow, positioning, and RTL language support.

Usage:
    from create_subtitles import create_ass_subtitles

    segments = [
        {"start": 0.0, "end": 3.5, "text": "Hola, bienvenidos"},
        {"start": 3.5, "end": 7.0, "text": "Este es nuestro nuevo producto"},
    ]
    config = {"font": "Arial", "size": 20}
    create_ass_subtitles(segments, "output/subtitles.ass", config)
"""

import os
import sys
from pathlib import Path


def seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds (float) to ASS timestamp format: H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    # ASS uses centiseconds (2 decimal places)
    return f"{h}:{m:02d}:{s:05.2f}"


def create_ass_subtitles(
    segments: list[dict],
    output_path: str,
    config: dict | None = None,
) -> str:
    """
    Create a styled ASS subtitle file from translated segments.

    Args:
        segments: List of dicts with keys:
            - start (float): Start time in seconds
            - end (float): End time in seconds
            - text (str): Subtitle text to display
        output_path: Path to write the .ass file
        config: Optional dict with styling parameters:
            - font (str): Font name (default: "Arial")
            - size (int): Font size in pixels (default: 20)
            - primary_color (str): Text color in ASS hex (default: "&H00FFFFFF" white)
            - secondary_color (str): Secondary color (default: "&H000000FF" blue)
            - outline_color (str): Outline color in ASS hex (default: "&H00000000" black)
            - back_color (str): Shadow/background color (default: "&H80000000" semi-transparent black)
            - bold (bool): Bold text (default: True)
            - italic (bool): Italic text (default: False)
            - outline_width (int): Outline thickness (default: 2)
            - shadow_offset (int): Shadow distance (default: 1)
            - alignment (int): Numpad-style alignment (default: 2, bottom center)
            - margin_l (int): Left margin (default: 10)
            - margin_r (int): Right margin (default: 10)
            - margin_v (int): Vertical margin from bottom (default: 30)
            - video_width (int): Video width for PlayResX (default: 1920)
            - video_height (int): Video height for PlayResY (default: 1080)
            - rtl (bool): Right-to-left language support (default: False)
            - encoding (int): Character encoding (default: 1 for default)

    Returns:
        Path to the created .ass file.
    """
    if config is None:
        config = {}

    # Style parameters with defaults
    font = config.get("font", "Arial")
    size = config.get("size", 20)
    primary_color = config.get("primary_color", "&H00FFFFFF")       # White
    secondary_color = config.get("secondary_color", "&H000000FF")   # Blue
    outline_color = config.get("outline_color", "&H00000000")       # Black
    back_color = config.get("back_color", "&H80000000")             # Semi-transparent black
    bold = -1 if config.get("bold", True) else 0
    italic = -1 if config.get("italic", False) else 0
    outline_width = config.get("outline_width", 2)
    shadow_offset = config.get("shadow_offset", 1)
    alignment = config.get("alignment", 2)  # Bottom center
    margin_l = config.get("margin_l", 10)
    margin_r = config.get("margin_r", 10)
    margin_v = config.get("margin_v", 30)
    video_width = config.get("video_width", 1920)
    video_height = config.get("video_height", 1080)
    rtl = config.get("rtl", False)
    encoding = config.get("encoding", 1)

    # For RTL languages (Hebrew, Arabic), adjust alignment to right
    if rtl and alignment == 2:
        alignment = 3  # Bottom right for RTL

    # Build ASS file content
    # -----------------------------------------------------------------------
    # [Script Info] section
    # -----------------------------------------------------------------------
    ass_content = f"""[Script Info]
Title: Provision Short Video Dubbing Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary_color},{secondary_color},{outline_color},{back_color},{bold},{italic},0,0,100,100,0,0,1,{outline_width},{shadow_offset},{alignment},{margin_l},{margin_r},{margin_v},{encoding}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # -----------------------------------------------------------------------
    # [Events] section - dialogue lines
    # -----------------------------------------------------------------------
    for seg in segments:
        start_time = seconds_to_ass_time(seg["start"])
        end_time = seconds_to_ass_time(seg["end"])
        text = seg["text"]

        # Handle multi-line text: replace newlines with ASS line break \N
        text = text.replace("\n", "\\N")

        # For RTL languages, prepend Unicode RTL mark
        if rtl:
            text = "\u200F" + text

        # Escape special ASS characters in text
        # (Curly braces are used for override tags, so literal braces need escaping)
        # Only escape if the text doesn't already contain ASS override tags
        if not text.startswith("{\\"):
            text = text.replace("{", "\\{").replace("}", "\\}")

        ass_content += (
            f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
        )

    # Write the file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)

    print(f"  ASS subtitles created: {output_path} ({len(segments)} dialogue lines)")
    return output_path


def create_ass_from_json(
    segments_json_path: str,
    output_path: str,
    config: dict | None = None,
    text_field: str = "refined_text",
) -> str:
    """
    Convenience function: create ASS subtitles from a JSON segments file.

    Args:
        segments_json_path: Path to JSON file with segment data
        output_path: Path to write .ass file
        config: Subtitle styling config dict
        text_field: Which text field to use from segments
            (e.g., "refined_text", "translated_text", "text")

    Returns:
        Path to the created .ass file.
    """
    import json

    with open(segments_json_path, "r", encoding="utf-8") as f:
        raw_segments = json.load(f)

    # Normalize to expected format
    segments = []
    for seg in raw_segments:
        text = seg.get(text_field) or seg.get("translated_text") or seg.get("text", "")
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": text,
        })

    return create_ass_subtitles(segments, output_path, config)


# ===========================================================================
# CLI Entry Point (standalone usage)
# ===========================================================================

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Create styled ASS subtitles from translated segments"
    )
    parser.add_argument(
        "--segments", type=str, required=True,
        help="Path to JSON file with translated segments",
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="Output path for .ass subtitle file",
    )
    parser.add_argument(
        "--text-field", type=str, default="refined_text",
        help="JSON field to use for subtitle text (default: refined_text)",
    )
    parser.add_argument(
        "--font", type=str, default="Arial",
        help="Font name (default: Arial)",
    )
    parser.add_argument(
        "--size", type=int, default=20,
        help="Font size (default: 20)",
    )
    parser.add_argument(
        "--outline", type=int, default=2,
        help="Outline width (default: 2)",
    )
    parser.add_argument(
        "--rtl", action="store_true",
        help="Enable RTL language support",
    )
    args = parser.parse_args()

    config = {
        "font": args.font,
        "size": args.size,
        "outline_width": args.outline,
        "rtl": args.rtl,
    }

    create_ass_from_json(args.segments, args.output, config, args.text_field)
