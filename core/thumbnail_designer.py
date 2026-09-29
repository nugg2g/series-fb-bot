import os
import sys
import re
import math
import time
import random
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from pythainlp.tokenize import word_tokenize
    HAS_PYTHAINLP = True
except ImportError:
    HAS_PYTHAINLP = False


def get_thai_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Finds best available Thai font on Windows or returns default."""
    windir = os.environ.get("WINDIR", "C:\\Windows")
    font_dir = os.path.join(windir, "Fonts")
    
    candidates = [
        "leelawdb.ttf",      # Leelawadee Bold (Clean modern sans-serif Thai)
        "LeelaUIb.ttf",      # Leelawadee UI Bold
        "tahomabd.ttf",      # Tahoma Bold
        "leelawad.ttf",      # Leelawadee Regular
        "tahoma.ttf",        # Tahoma Regular
        "cordiab.ttf",       # Cordia Bold
        "angsab.ttf",        # Angsana Bold
        "arialbd.ttf"
    ]
    for c in candidates:
        p = os.path.join(font_dir, c)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def build_flux_prompt(title: str, platform: str = "youtube") -> str:
    """Builds a rich cinematic visual prompt matching high-CTR Asian drama posters."""
    t_lower = title.lower()
    
    if any(w in t_lower for w in ["เซียน", "ฝึก", "ย้อนเวลา", "เกิดใหม่", "สวรรค์", "กระบี่", "วิญญาณ", "มาร"]):
        theme = (
            "handsome Asian celestial sword immortal cultivator with ethereal flowing silver-white robes, "
            "mystical glowing aura, floating ancient Chinese temple in misty mountain clouds, "
            "celestial energy, dramatic volumetric lighting, Xianxia epic fantasy art"
        )
    elif any(w in t_lower for w in ["ฮ่องเต้", "องค์ชาย", "รัชทายาท", "วังหลวง", "แม่ทัพ", "สนม", "หงส์"]):
        theme = (
            "majestic ancient Chinese crown prince in imperial black and gold dragon robes, "
            "grand forbidden palace courtyard backdrop, burning lanterns, dramatic cinematic atmosphere"
        )
    elif any(w in t_lower for w in ["ยากจน", "จน", "ขอทาน", "บ้านนอก", "ตกอับ", "ลูกเขย"]):
        theme = (
            "intense Asian male protagonist in simple clothes transforming into luxury billionaire suit, "
            "dramatic contrast lighting, rain-soaked city street meeting luxury penthouse skyline"
        )
    else:
        # Default: High-CTR Modern CEO / Revenge / Luxury drama
        theme = (
            "handsome ruthless Asian CEO male lead in sharp luxury black suit with fierce intense eyes, "
            "gorgeous glamorous Asian female lead in striking red evening gown, "
            "luxurious high-rise penthouse background with illuminated modern city skyline bokeh, "
            "shiny Rolls-Royce limousine, floating stacks of golden banknotes, dramatic rim lighting, "
            "cinematic photography"
        )

    aspect_desc = "widescreen 16 by 9 composition" if platform == "youtube" else "vertical mobile portrait composition"
    return (
        f"Masterpiece 8k Asian drama poster scene, {theme}, "
        f"{aspect_desc}, hyperrealistic, ultra-detailed faces, octane render style, trending on ArtStation"
    )


def extract_video_frame(video_path: str, target_w: int, target_h: int) -> Optional[Image.Image]:
    """Fallback: extracts a sharp frame from the actual video if available."""
    if not video_path or not os.path.exists(video_path):
        return None
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        # Pick frame around 5-10 seconds in (avoids black intro)
        target_f = min(int(fps * 8), max(0, total_frames // 4))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_f)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            # Convert BGR to RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(rgb)
            # Crop/resize to target dimensions
            return im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"[Thumbnail Designer] Note: Frame extraction fallback failed: {e}")
    return None


def download_flux_artwork(prompt: str, platform: str, final_w: int, final_h: int, output_path: str) -> bool:
    """Downloads AI background artwork from Flux within free tier limits and upscales sharply."""
    # Free tier supported dimensions: 576x1024 (9:16) and 768x768 (1:1)
    if platform == "youtube":
        req_w, req_h = 768, 768
    else:
        req_w, req_h = 576, 1024

    encoded = urllib.parse.quote(prompt)
    seed = random.randint(1000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={req_w}&height={req_h}&nologo=true&seed={seed}"
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = resp.read()
                if len(data) > 10000:
                    import io
                    raw_img = Image.open(io.BytesIO(data)).convert("RGB")
                    
                    if platform == "youtube":
                        # Crop 16:9 from center of 768x768 (768 x 432)
                        crop_h = int(768 * 9 / 16)
                        top = (768 - crop_h) // 2
                        cropped = raw_img.crop((0, top, 768, top + crop_h))
                        final_img = cropped.resize((final_w, final_h), Image.Resampling.LANCZOS)
                    else:
                        # 576x1024 is already 9:16 -> clean Lanczos resize to 720x1280
                        final_img = raw_img.resize((final_w, final_h), Image.Resampling.LANCZOS)
                        
                    final_img.save(output_path, "JPEG", quality=95)
                    return True
        except Exception as e:
            print(f"[Thumbnail Designer] ⚠️ Flux fetch attempt {attempt+1} error: {e}")
            time.sleep(2)
    return False


def split_thai_title(title: str, max_chars_per_line: int = 16) -> List[str]:
    """
    Intelligently splits a Thai title into 1 or 2 lines using natural word boundaries.
    Ensures real drama title is preserved without mid-word breaks.
    """
    title = title.strip()
    # If already short enough, return single line
    if len(title) <= max_chars_per_line:
        return [title]
        
    # Check if there's an existing space or punctuation break
    if " " in title:
        parts = [p.strip() for p in title.split(" ") if p.strip()]
        if len(parts) == 2:
            return parts
        elif len(parts) > 2:
            mid = len(parts) // 2
            return [" ".join(parts[:mid]), " ".join(parts[mid:])]
            
    # Use PyThaiNLP word tokenization for natural split
    if HAS_PYTHAINLP:
        tokens = word_tokenize(title, engine="newmm")
        total_len = sum(len(t) for t in tokens)
        half_len = total_len / 2.0
        
        line1_tokens = []
        cur_len = 0
        split_idx = 1
        for i, t in enumerate(tokens):
            line1_tokens.append(t)
            cur_len += len(t)
            if cur_len >= half_len:
                split_idx = i + 1
                break
        line1 = "".join(line1_tokens)
        line2 = "".join(tokens[split_idx:])
        if line1 and line2:
            return [line1, line2]

    # Fallback character midpoint
    mid = len(title) // 2
    return [title[:mid], title[mid:]]


def draw_text_with_effects(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill_color: Tuple[int, int, int],
    stroke_color: Tuple[int, int, int] = (0, 0, 0),
    stroke_width: int = 8,
    shadow_offset: Tuple[int, int] = (6, 8)
):
    """Draws punchy 3D-styled typography with thick stroke and drop shadow."""
    x, y = xy
    # 1. 3D Drop Shadow (Multiple layers for depth)
    for off in range(1, shadow_offset[1] + 1, 2):
        sx = x + int(shadow_offset[0] * (off / shadow_offset[1]))
        sy = y + off
        draw.text((sx, sy), text, font=font, fill=(0, 0, 0), stroke_width=stroke_width + 1, stroke_fill=(0, 0, 0))
    
    # 2. Main Stroke & Fill
    draw.text((x, y), text, font=font, fill=fill_color, stroke_width=stroke_width, stroke_fill=stroke_color)


def add_dark_vignette(image: Image.Image, region: str = "bottom", strength: float = 0.85) -> Image.Image:
    """Adds a smooth dark gradient overlay so text stands out crisply on any scene."""
    w, h = image.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    if region == "bottom":
        start_y = int(h * 0.40)
        for y in range(start_y, h):
            ratio = (y - start_y) / (h - start_y)
            alpha = int(255 * strength * (ratio ** 1.35))
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    elif region == "center":
        # Safe center zone for Facebook Reels (Smooth cosine falloff)
        center_y = int(h * 0.54)
        band_h = int(h * 0.45)
        top_y = center_y - band_h // 2
        bot_y = center_y + band_h // 2
        for y in range(top_y, bot_y):
            dist = abs(y - center_y) / (band_h / 2.0)
            if dist < 1.0:
                factor = 0.5 * (1.0 + math.cos(math.pi * dist))
                alpha = int(255 * strength * factor)
                draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
            
    base_rgba = image.convert("RGBA")
    combined = Image.alpha_composite(base_rgba, overlay)
    return combined.convert("RGB")


def draw_dubbed_badge(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], scale: float = 1.0, text: str = "เต็มเรื่อง"):
    """
    Renders the signature red pill badge: ▶ เต็มเรื่อง
    Uses sharp vector-drawn play icon + clean bold Thai typography.
    """
    bx, by = xy
    bw = int(190 * scale)
    bh = int(48 * scale)
    r = int(14 * scale)
    
    # Drop shadow
    draw.rounded_rectangle(
        [(bx + 2, by + 3), (bx + bw + 2, by + bh + 3)],
        radius=r,
        fill=(0, 0, 0, 180)
    )
    # Red Background Pill (#E50914) with White Border
    draw.rounded_rectangle(
        [(bx, by), (bx + bw, by + bh)],
        radius=r,
        fill=(229, 9, 20),
        outline=(255, 255, 255),
        width=int(2 * scale)
    )
    
    # Draw crisp play icon (white triangle)
    px = bx + int(20 * scale)
    py = by + int(14 * scale)
    draw.polygon(
        [
            (px, py),
            (px + int(16 * scale), py + int(10 * scale)),
            (px, py + int(20 * scale))
        ],
        fill=(255, 255, 255)
    )

    # Badge Thai Text: เต็มเรื่อง
    font_size = int(25 * scale)
    font = get_thai_font(font_size, bold=True)
    text_x = px + int(24 * scale)
    text_y = by + int(8 * scale)
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255))



def create_high_ctr_thumbnail(
    title: str,
    platform: str = "youtube",
    video_path: Optional[str] = None,
    output_path: Optional[str] = None
) -> Optional[str]:
    """
    Generates a high-converting, click-worthy thumbnail/cover for YouTube (16:9) or Facebook Reels (9:16).
    
    - STRICT: Uses the real drama title provided (no hallucination).
    - Adds the iconic '🔊 พากย์ไทย' red badge.
    - Customizes composition and safe zones based on platform.
    """
    clean_title = title.strip()
    if not clean_title:
        clean_title = "ซีรีส์จีนยอดฮิต"

    # Set platform-specific dimensions
    if platform.lower() in ["fb", "facebook", "reels"]:
        target_platform = "facebook"
        width, height = 720, 1280
    else:
        target_platform = "youtube"
        width, height = 1280, 720

    if not output_path:
        out_dir = Path("Z:/Projects/YouTube Shorts Auto Bot/data/thumbnails")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"thumb_{target_platform}_{int(time.time())}_{random.randint(100, 999)}.jpg"
        output_path = str(out_dir / safe_name)
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"[Thumbnail Designer] 🎬 Generating {target_platform.upper()} ({width}x{height}) cover for: '{clean_title}'")

    # Step 1: AI Background Artwork via Flux
    flux_prompt = build_flux_prompt(clean_title, platform=target_platform)
    raw_bg_path = output_path + ".raw.jpg"
    success = download_flux_artwork(
        prompt=flux_prompt,
        platform=target_platform,
        final_w=width,
        final_h=height,
        output_path=raw_bg_path
    )
    
    base_img = None
    if success and os.path.exists(raw_bg_path):
        base_img = Image.open(raw_bg_path).convert("RGB")
        try:
            os.remove(raw_bg_path)
        except Exception:
            pass
    elif video_path:
        # Fallback to high-res keyframe from video
        print("[Thumbnail Designer] 🎥 Extracting keyframe from drama video file...")
        base_img = extract_video_frame(video_path, width, height)

    if base_img is None:
        # Fallback: High quality cinematic gradient backdrop
        print("[Thumbnail Designer] ⚠️ Flux artwork unavailable, creating fallback cinematic background...")
        base_img = Image.new("RGB", (width, height), color=(15, 12, 28))
        draw_fb = ImageDraw.Draw(base_img)
        for y in range(height):
            r = int(15 + 20 * (y / height))
            g = int(12 + 10 * (y / height))
            b = int(28 + 35 * (y / height))
            draw_fb.line([(0, y), (width, y)], fill=(r, g, b))

    # Step 2: Dark Vignette for maximum text readability
    vignette_region = "bottom" if target_platform == "youtube" else "center"
    base_img = add_dark_vignette(base_img, region=vignette_region, strength=0.85)
    draw = ImageDraw.Draw(base_img)

    # Step 3: Draw '▶ เต็มเรื่อง' Badge
    if target_platform == "youtube":
        # YouTube: Top Right corner
        draw_dubbed_badge(draw, (width - 225, 36), scale=1.0, text="เต็มเรื่อง")
    else:
        # Facebook Reels: Top safe area (below status bar, above middle UI)
        draw_dubbed_badge(draw, (width - 225, 150), scale=1.0, text="เต็มเรื่อง")

    # Step 4: Render Real Drama Title
    max_chars = 18 if target_platform == "youtube" else 14
    lines = split_thai_title(clean_title, max_chars_per_line=max_chars)
    
    if target_platform == "youtube":
        # YouTube 16:9 Layout (Text placed in lower section)
        font_size = 58 if len(lines) == 2 else 66
        font = get_thai_font(font_size, bold=True)
        
        # Colors: Line 1 = Golden Yellow (#FFD700), Line 2 = Bright Cyan (#00E5FF)
        colors = [(255, 220, 0), (0, 235, 255)] if len(lines) > 1 else [(255, 225, 30)]
        
        line_height = font_size + 14
        total_text_h = len(lines) * line_height
        start_y = height - total_text_h - 45
        
        for i, line_text in enumerate(lines):
            bbox = font.getbbox(line_text)
            text_w = bbox[2] - bbox[0]
            text_x = max(30, (width - text_w) // 2)
            cur_y = start_y + (i * line_height)
            
            draw_text_with_effects(
                draw=draw,
                xy=(text_x, cur_y),
                text=line_text,
                font=font,
                fill_color=colors[i % len(colors)],
                stroke_color=(0, 0, 0),
                stroke_width=8,
                shadow_offset=(6, 8)
            )
            
    else:
        # Facebook Reels 9:16 Layout (Text strictly in center safe zone)
        # Safe zone: y centered between 500 and 800 (keeps away from reels bottom icons & comments)
        font_size = 52 if len(lines) >= 2 else 60
        font = get_thai_font(font_size, bold=True)
        
        colors = [(255, 225, 0), (255, 65, 45)] if len(lines) > 1 else [(255, 225, 30)]
        
        line_height = font_size + 18
        total_text_h = len(lines) * line_height
        start_y = int(height * 0.53) - (total_text_h // 2)
        
        for i, line_text in enumerate(lines):
            bbox = font.getbbox(line_text)
            text_w = bbox[2] - bbox[0]
            text_x = max(24, (width - text_w) // 2)
            cur_y = start_y + (i * line_height)
            
            draw_text_with_effects(
                draw=draw,
                xy=(text_x, cur_y),
                text=line_text,
                font=font,
                fill_color=colors[i % len(colors)],
                stroke_color=(0, 0, 0),
                stroke_width=8,
                shadow_offset=(5, 7)
            )

    # Save output with high JPEG quality
    base_img.save(output_path, "JPEG", quality=95)
    print(f"[Thumbnail Designer] ✅ Successfully saved thumbnail: {output_path} ({os.path.getsize(output_path)} bytes)")
    return output_path


if __name__ == "__main__":
    test_title = "คุณชายถูกทิ้งกลับมา ขยี้ทุกคำเยาะเย้ย!"
    print("Testing YouTube (16:9)...")
    yt_thumb = create_high_ctr_thumbnail(
        title=test_title,
        platform="youtube",
        output_path="Z:/Projects/YouTube Shorts Auto Bot/data/thumbnails/test_yt.jpg"
    )
    print("YouTube thumbnail:", yt_thumb)
    
    print("\nTesting Facebook Reels (9:16)...")
    fb_thumb = create_high_ctr_thumbnail(
        title=test_title,
        platform="facebook",
        output_path="Z:/Projects/YouTube Shorts Auto Bot/data/thumbnails/test_fb.jpg"
    )
    print("Facebook Reels thumbnail:", fb_thumb)
