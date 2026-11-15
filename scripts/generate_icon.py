"""High-Resolution Application Icon Generator.

Generates official-grade election commission / electoral roll app icons
in PNG (512x512) and multi-resolution Windows ICO (16, 24, 32, 48, 64, 128, 256).
Features deep navy shield, Indian tricolor accent, ballot register document,
and embossed emerald verification checkmark.
"""

from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def create_app_icon(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    size = 1024  # Draw at 1024x1024 for supersampled razor-sharp antialiasing
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Outer Rounded Shield / Square with Deep Navy Gradient and Soft Drop Shadow
    pad = 64
    r = 180  # Corner radius

    # Shadow layer
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        [pad + 8, pad + 24, size - pad + 8, size - pad + 24],
        radius=r,
        fill=(10, 15, 30, 140),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(32))
    img.alpha_composite(shadow)

    # Base Deep Navy Gradient Shield
    shield = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(shield)
    for y in range(pad, size - pad):
        factor = (y - pad) / (size - 2 * pad)
        # Gradient from Rich Navy #1E3A8A to Midnight Navy #0B1938
        r_c = int(30 * (1 - factor) + 11 * factor)
        g_c = int(58 * (1 - factor) + 25 * factor)
        b_c = int(138 * (1 - factor) + 56 * factor)
        sh_draw.line([(pad, y), (size - pad, y)], fill=(r_c, g_c, b_c, 255))

    # Mask with rounded rectangle
    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=r, fill=255)
    img.paste(shield, (0, 0), mask)

    # Gold / Amber Border Stroke
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=r,
        outline=(245, 158, 11, 230),
        width=16,
    )

    # 2. Indian Tricolor Ribbon / Header Bar at Top of Shield
    tc_mask = Image.new("L", (size, size), 0)
    tc_m_draw = ImageDraw.Draw(tc_mask)
    tc_m_draw.rounded_rectangle([pad + 16, pad + 16, size - pad - 16, pad + 110], radius=40, fill=255)

    tc_bar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tc_draw = ImageDraw.Draw(tc_bar)
    # Saffron stripe
    tc_draw.rectangle([pad, pad + 16, size - pad, pad + 48], fill=(255, 103, 31, 255))
    # White stripe
    tc_draw.rectangle([pad, pad + 48, size - pad, pad + 78], fill=(255, 255, 255, 255))
    # Green stripe
    tc_draw.rectangle([pad, pad + 78, size - pad, pad + 110], fill=(4, 106, 56, 255))

    # Ashoka Navy Chakra dot in center of white stripe
    chakra_x = size // 2
    chakra_y = pad + 63
    tc_draw.ellipse([chakra_x - 9, chakra_y - 9, chakra_x + 9, chakra_y + 9], outline=(0, 0, 128, 255), width=3)
    tc_draw.ellipse([chakra_x - 3, chakra_y - 3, chakra_x + 3, chakra_y + 3], fill=(0, 0, 128, 255))

    img.paste(tc_bar, (0, 0), tc_mask)

    # 3. Voter Register / Document Sheet in Center
    doc_x1, doc_y1 = pad + 140, pad + 170
    doc_x2, doc_y2 = size - pad - 140, size - pad - 110
    doc_r = 36

    # Document shadow
    doc_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ds_draw = ImageDraw.Draw(doc_shadow)
    ds_draw.rounded_rectangle([doc_x1 + 6, doc_y1 + 12, doc_x2 + 6, doc_y2 + 12], radius=doc_r, fill=(0, 0, 0, 100))
    doc_shadow = doc_shadow.filter(ImageFilter.GaussianBlur(16))
    img.alpha_composite(doc_shadow)

    # Crisp White Register Sheet with subtle warm tone
    draw.rounded_rectangle([doc_x1, doc_y1, doc_x2, doc_y2], radius=doc_r, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=8)

    # Document Header Band (Election Blue)
    draw.rounded_rectangle([doc_x1 + 14, doc_y1 + 14, doc_x2 - 14, doc_y1 + 90], radius=20, fill=(30, 58, 138, 255))
    # Header mini lines (Title simulation)
    draw.rounded_rectangle([doc_x1 + 40, doc_y1 + 38, doc_x1 + 220, doc_y1 + 52], radius=6, fill=(255, 255, 255, 240))
    draw.rounded_rectangle([doc_x1 + 40, doc_y1 + 62, doc_x1 + 160, doc_y1 + 72], radius=4, fill=(208, 225, 253, 200))

    # Voter Roll Grid / Table Entries (Simulating voter lists)
    line_y_starts = [doc_y1 + 130, doc_y1 + 200, doc_y1 + 270, doc_y1 + 340]
    for ly in line_y_starts:
        # Checkbox / Serial avatar
        draw.rounded_rectangle([doc_x1 + 40, ly, doc_x1 + 76, ly + 36], radius=8, fill=(241, 245, 249, 255), outline=(203, 213, 225, 255), width=3)
        # Voter name bar
        draw.rounded_rectangle([doc_x1 + 96, ly + 4, doc_x1 + 300, ly + 18], radius=6, fill=(51, 65, 85, 220))
        # Relative / Age bar
        draw.rounded_rectangle([doc_x1 + 96, ly + 24, doc_x1 + 240, ly + 34], radius=4, fill=(148, 163, 184, 180))
        # Serial no / house no pill on right
        draw.rounded_rectangle([doc_x2 - 120, ly + 8, doc_x2 - 40, ly + 28], radius=10, fill=(237, 233, 254, 255))

    # 4. Prominent Emerald Verification Checkmark (Symbolizing Verified Match)
    chk_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    chk_draw = ImageDraw.Draw(chk_img)

    # Checkmark circle badge on bottom right
    badge_cx, badge_cy, badge_rad = size - pad - 130, size - pad - 120, 110
    # Badge shadow
    chk_draw.ellipse(
        [badge_cx - badge_rad - 6, badge_cy - badge_rad + 10, badge_cx + badge_rad + 6, badge_cy + badge_rad + 10],
        fill=(0, 0, 0, 90),
    )
    chk_img = chk_img.filter(ImageFilter.GaussianBlur(12))
    img.alpha_composite(chk_img)

    # Badge circle (Emerald Green with gold rim)
    draw.ellipse(
        [badge_cx - badge_rad, badge_cy - badge_rad, badge_cx + badge_rad, badge_cy + badge_rad],
        fill=(16, 185, 129, 255),
        outline=(255, 255, 255, 255),
        width=12,
    )

    # Crisp White Bold Tick/Checkmark
    p1 = (badge_cx - 48, badge_cy + 2)
    p2 = (badge_cx - 14, badge_cy + 42)
    p3 = (badge_cx + 52, badge_cy - 44)

    draw.line([p1, p2], fill=(255, 255, 255, 255), width=24)
    draw.line([p2, p3], fill=(255, 255, 255, 255), width=24)
    # Smooth joint caps
    draw.ellipse([p1[0] - 12, p1[1] - 12, p1[0] + 12, p1[1] + 12], fill=(255, 255, 255, 255))
    draw.ellipse([p2[0] - 12, p2[1] - 12, p2[0] + 12, p2[1] + 12], fill=(255, 255, 255, 255))
    draw.ellipse([p3[0] - 12, p3[1] - 12, p3[0] + 12, p3[1] + 12], fill=(255, 255, 255, 255))

    # 5. Export Master High-Res PNG (512x512)
    png_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
    png_path = output_dir / "icon.png"
    png_512.save(png_path, "PNG")

    # 6. Export Multi-Size Windows ICO File
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_images = [img.resize(s, Image.Resampling.LANCZOS) for s in ico_sizes]
    ico_path = output_dir / "icon.ico"
    ico_images[-1].save(
        ico_path,
        format="ICO",
        sizes=ico_sizes,
        append_images=ico_images[:-1],
    )

    print(f"Generated PNG: {png_path} ({png_path.stat().st_size} bytes)")
    print(f"Generated ICO: {ico_path} ({ico_path.stat().st_size} bytes)")
    return png_path, ico_path


if __name__ == "__main__":
    target_dir = Path(__file__).resolve().parent.parent / "voter_match" / "data"
    create_app_icon(target_dir)
