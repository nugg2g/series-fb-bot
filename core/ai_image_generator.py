"""
core/ai_image_generator.py — ລະບົບສ້າງຮູບພາບ AI ໂປສເຕີ/ສາກໜັງຈີນ & ຂຽນ Caption ເຊີນຊວນຕິດຕາມບໍ່ຊ້ຳກັນ 100%

ສະຖາປັດຕະຍະກຳ 100% Pure AI Cinema Synthesizer (ບໍ່ໃຊ້ຮູບປົກ ຫຼື ເຟຣມວິດີໂອເດັດຂາດ):
1. 100% Pure Generative AI Imagery: ສ້າງຮູບພາບພື້ນຫຼັງດ້ວຍ AI ສັງເຄາະ 100% (Gemini Image API / AI Cinema Backdrops Pool).
2. Cinema Color Grading: ແຕ່ງສີ Cinema Teal/Gold/Purple, Contrast, Vignette ໃຫ້ຄົມຊັດລະດັບ Ultra HD.
3. Gemini AI Visual Director: ວິເຄາະພາບ AI ແລະ ສ້າງຊື່ເລື່ອງສຸດມັນ, ຄຳໂປຣໂມດ, ແລະ Caption ຊວນກົດຕິດຕາມ (ພາສາໄທລ້ວນ 100%).
4. Typography & Badges: ໃສ່ກອບ Luxury Gold/Neon, ປ້າຍ "🎬 ຊີຣີຈີນເຕັມເລື່ອງ", ແລະ ປ້າຍ Follower CTA ແບບມືອາຊີບ.
"""

import os
import io
import json
import time
import glob
import random
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from core.caption_generator import CaptionGenerator


class AiImageGenerator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_dir = os.path.abspath(config.get("cta_images_folder", "./cta_images"))
        os.makedirs(self.output_dir, exist_ok=True)
        self.ai_backdrops_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "ai_cinema_backdrops"))
        os.makedirs(self.ai_backdrops_dir, exist_ok=True)
        self.caption_gen = CaptionGenerator(config)
        self.cta_cache_file = os.path.abspath("./logs/today_cta_cache.json")

    def get_cached_today_cta(self) -> Optional[Tuple[str, str, str]]:
        """Returns cached CTA image, caption, and title for today if available."""
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            if os.path.exists(self.cta_cache_file):
                with open(self.cta_cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == today:
                    img = data.get("image_path", "")
                    if img and os.path.exists(img):
                        return img, data.get("caption", ""), data.get("title", "")
        except Exception:
            pass
        return None

    def store_cached_today_cta(self, image_path: str, caption: str, title: str):
        """Persists today's generated CTA post so all target pages reuse it without extra API cost."""
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            os.makedirs(os.path.dirname(self.cta_cache_file), exist_ok=True)
            with open(self.cta_cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "date": today,
                    "image_path": image_path,
                    "caption": caption,
                    "title": title
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def generate_unique_cta_post(self, video_path: Optional[str] = None) -> Tuple[str, str, str]:
        """
        ສ້າງຮູບພາບໂປສເຕີ AI 100% ແລະ Caption ເຊີນຊວນຕິດຕາມເພຈ Facebook ແບບບໍ່ຊ້ຳກັນ (ພາສາໄທລ້ວນ)
        ໝາຍເຫດ: ບໍ່ໃຊ້ຮູບປົກ ຫຼື ເຟຣມວິດີໂອຈາກຄັງໜັງເດັດຂາດ (Pure Generative AI 100%)
        Returns:
            (saved_image_path, ai_caption_text, title)
        """
        # 0. Check Today's Cache (Credit Saver - 1 generation per day shared across pages/retries)
        cached = self.get_cached_today_cta()
        if cached:
            print(f"[AiImageGenerator] ⚡ [Credit Saver] Reusing today's cached AI CTA poster: {os.path.basename(cached[0])}")
            return cached

        # 1. ສ້າງ ຫຼື ດຶງຮູບພາບພື້ນຫຼັງ AI Gen 100% (Zero video frames)
        base_img = self._get_pure_ai_backdrop()

        # 2. ໃຫ້ Gemini AI ວິເຄາະຮູບພາບ AI ແລະ ສ້າງຊື່ເລື່ອງ + Caption (ພາສາໄທລ້ວນ 100%)
        title, subtitle, caption = self._generate_ai_content(base_img)

        # 3. ຕົກແຕ່ງຮູບດ້ວຍ Cinema Typography, Badges ແລະ ກອບຫຼູຫຼາ
        final_img = self._composite_cinema_poster(base_img, title, subtitle)

        # 4. ບັນທຶກຮູບພາບດ້ວຍ Timestamp ສະເພາະ
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_cta_{timestamp_str}_{random.randint(100, 999)}.jpg"
        save_path = os.path.join(self.output_dir, filename)
        final_img.save(save_path, quality=95)

        # Cache today's CTA post to prevent spending credits on repeated generations
        self.store_cached_today_cta(save_path, caption, title)

        return save_path, caption, title

    def _get_pure_ai_backdrop(self) -> Image.Image:
        """
        ສ້າງ ຫຼື ດຶງຮູບພາບພື້ນຫຼັງທີ່ເປັນ Generative AI 100%
        (ບໍ່ໃຊ້ຮູບປົກ ຫຼື ວິດີໂອຈາກຄັງໜັງເດັດຂາດ ຕາມຄຳສັ່ງຂອງຜູ້ໃຊ້)
        """
        # 1. ດຶງຈາກຄັງຮູບພາບ AI Cinema Backdrops ທີ່ AI ສ້າງຂຶ້ນມາ 100%
        candidates = []
        if os.path.exists(self.ai_backdrops_dir):
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                candidates.extend(glob.glob(os.path.join(self.ai_backdrops_dir, ext)))

        if candidates:
            chosen_path = random.choice(candidates)
            try:
                with Image.open(chosen_path) as src:
                    pil_img = src.convert("RGB")
                    # Resize/crop to 1080x1080 Square
                    w, h = pil_img.size
                    min_dim = min(w, h)
                    left = (w - min_dim) // 2
                    top = (h - min_dim) // 2
                    cropped = pil_img.crop((left, top, left + min_dim, top + min_dim))
                    resized = cropped.resize((1080, 1080), Image.Resampling.LANCZOS)

                    # Subtle dynamic color enhancement so every run is unique
                    color_factor = random.uniform(1.05, 1.20)
                    contrast_factor = random.uniform(1.05, 1.15)
                    enhanced = ImageEnhance.Color(resized).enhance(color_factor)
                    final_base = ImageEnhance.Contrast(enhanced).enhance(contrast_factor)
                    print(f"[AiImageGenerator] 🎨 Loaded 100% AI Backdrop: {os.path.basename(chosen_path)}")
                    return final_base
            except Exception as e:
                print(f"[AiImageGenerator] Could not load backdrop {chosen_path}: {e}")

        # 2. ຖ້າບໍ່ມີໄຟລ໌ໃນຄັງ, ລອງສ້າງຜ່ານ Gemini Image API ຖ້າເປີດໃຊ້ງານ
        if self.config.get("ai_image_gen", {}).get("use_live_api", False):
            live_img = self._try_generate_live_gemini_image()
            if live_img is not None:
                return live_img

        # 3. Fallback: Procedural Cinema Luxury Backdrop
        return self._generate_procedural_backdrop()

    def _try_generate_live_gemini_image(self) -> Optional[Image.Image]:
        """ພະຍາຍາມຮຽກໃຊ້ Gemini Image Generation Model ຖ້າມີ Credit/Quota."""
        keys, _ = self.caption_gen.get_api_keys()
        if not keys:
            return None

        prompt = "Cinematic movie poster of ancient Chinese fantasy martial arts emperor in majestic dragon armor, dramatic lighting, photorealistic 8k, clean with no text"

        try:
            from google import genai
            client = genai.Client(api_key=keys[0])
            res = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[prompt]
            )
            if res and res.parts:
                for part in res.parts:
                    if part.inline_data:
                        img = part.as_image().convert("RGB")
                        img = img.resize((1080, 1080), Image.Resampling.LANCZOS)
                        print(f"[AiImageGenerator] ✨ Live Gemini AI image generated successfully!")
                        return img
        except Exception as e:
            print(f"[AiImageGenerator] Live Gemini image gen skipped: {e}")

        return None

    def _generate_procedural_backdrop(self) -> Image.Image:
        """ສ້າງສາກຫຼັງ Cinema Luxury Gradient ໃນກໍລະນີສຸກເສີນ."""
        img = Image.new("RGB", (1080, 1080), color=(15, 12, 28))
        draw = ImageDraw.Draw(img)

        themes = [
            ((20, 10, 40), (80, 20, 90), (255, 180, 50)),   # Royal Purple & Gold
            ((5, 15, 35), (10, 50, 90), (0, 210, 255)),      # Sci-Fi Cyber Blue
            ((35, 10, 15), (90, 20, 30), (255, 140, 40)),   # Crimson Drama
        ]
        c1, c2, accent = random.choice(themes)

        for y in range(1080):
            ratio = y / 1080.0
            r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
            g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
            b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
            draw.line([(0, y), (1080, y)], fill=(r, g, b))

        glow = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        for r in range(400, 0, -20):
            alpha = int((1 - r / 400) * 80)
            gdraw.ellipse([540 - r, 540 - r, 540 + r, 540 + r], fill=(accent[0], accent[1], accent[2], alpha))
        img.paste(glow, (0, 0), glow)

        return img

    def _generate_ai_content(self, frame_img: Image.Image) -> Tuple[str, str, str]:
        """ໃຊ້ Gemini AI ສ້າງຊື່ເລື່ອງ, ຄຳໂປຣໂມດ ແລະ Caption ເຊີນຊວນຕິດຕາມເພຈ ເປັນພາສາໄທລ້ວນ 100%."""
        import re

        ai_cfg = self.config.get("ai_caption", {})
        if ai_cfg.get("enabled", True):
            try:
                from google import genai
                from google.genai import types
                keys, _ = self.caption_gen.get_api_keys()
                if keys:
                    prompt = (
                        "Generate a viral, catchy Thai drama title and engaging follower invitation caption in 100% PURE THAI LANGUAGE (ภาษาไทยล้วน) for a Chinese mini-series Facebook page.\n"
                        "CRITICAL: Absolutely NO Lao characters (ห้ามมีภาษาลาวโดยเด็ดขาด 100%).\n"
                        "Respond ONLY with valid JSON:\n"
                        "{\n"
                        '  "title": "[ชื่อซีรีส์จีนสุดมันส์ เช่น ศึกจอมราชันย์ ทวงบัลลังก์]",\n'
                        '  "subtitle": "[คำโปรย เช่น ซีรีส์จีนดราม่าสุดเข้มข้น พากย์ไทยเต็มเรื่อง]",\n'
                        '  "caption": "🎬 ✨ [ชื่อเรื่อง] ✨\\n\\n🔥 [คำโปรย]\\n\\n📌 ติดตามเรื่องราวความสนุกและซีรีส์จีนเรื่องใหม่ๆ ก่อนใคร!\\n👉 ฝากกด Like 👍 และกด Follow (ติดตามเพจ) เพื่อเป็นกำลังใจให้ทีมงานด้วยนะครับ ❤️\\n✨ รับชมซีรีส์เต็มเรื่อง ดูฟรีไม่มีโฆษณาคั่นได้ที่นี่ทุกวัน!\\n\\n#ซีรีส์จีน #หนังสั้นจีน #ซีรีส์จีนเต็มเรื่อง #พากย์ไทย #ละครสั้น #reels #reelsfb #viral #กดติดตาม"\n'
                        "}"
                    )
                    http_opts = types.HttpOptions(
                        timeout=8000,
                        retry_options=types.HttpRetryOptions(attempts=1)
                    )
                    for k in keys[:2]:
                        try:
                            client = genai.Client(api_key=k, http_options=http_opts)
                            res = client.models.generate_content(
                                model="gemini-3.5-flash-lite",
                                contents=[prompt]
                            )
                            if res and res.text:
                                match = re.search(r'\{.*\}', res.text, re.DOTALL)
                                if match:
                                    data = json.loads(match.group(0))
                                    t = data.get("title", "").strip()
                                    s = data.get("subtitle", "").strip()
                                    c = data.get("caption", "").strip()
                                    t = re.sub(r'[\u0E80-\u0EFF]', '', t).strip()
                                    s = re.sub(r'[\u0E80-\u0EFF]', '', s).strip()
                                    c = re.sub(r'[\u0E80-\u0EFF]', '', c).strip()
                                    if t and c:
                                        print(f"[AiImageGenerator] 🤖 Generated Thai AI Content via Gemini: '{t}'")
                                        return t, s or "ซีรีส์จีนดราม่าสุดเข้มข้น พากย์ไทยเต็มเรื่อง", c
                        except Exception:
                            continue
            except Exception as e:
                print(f"[AiImageGenerator] AI Content generation skipped: {e}")

        # Curated Fallback (100% Pure Thai)
        fallback_titles = [
            "ศึกจอมราชันย์ ทวงบัลลังກ์",
            "เล่ห์รักจอมใจ ข้ามมิติ 100 ปี",
            "หวนคืนบัลลังก์จักรพรรดิ",
            "เทพยุทธ์สะท้านภพ ชะตาแค้น",
            "ความแค้นคุณหนูใหญ่ตระกูลหลิน",
            "ทะลุมิติมาเป็นชายาจำยอม",
            "ยอดฝีมือไร้พ่าย กู้บัลลังก์ทอง",
            "ประธานหมื่นล้าน ปลอมตัวลองใจรัก",
            "คุณหนูตกอับ หวนคืนล้างแค้นตระกูลดัง"
        ]
        fallback_subtitles = [
            "ซีรีส์จีนดราม่าสุดเข้มข้น พากย์ไทยเต็มเรื่อง",
            "เรื่องราวสุดมันส์ หักมุมทุกตอน ห้ามพลาด!",
            "ความรักและการแก้แค้น สนุกจนหยุดดูไม่ได้",
            "อัปเดตตอนใหม่เต็มเรื่องจุใจ ทุกวัน!",
        ]
        t = random.choice(fallback_titles)
        t = re.sub(r'[\u0E80-\u0EFF]', '', t).strip()
        s = random.choice(fallback_subtitles)
        c = (
            f"🎬 ✨ {t} ✨\n\n"
            f"🔥 {s}\n\n"
            f"📌 ติดตามเรื่องราวความสนุกและซีรีส์จีนเรื่องใหม่ๆ ก่อนใคร!\n"
            f"👉 ฝากกด Like 👍 และกด Follow (ติดตามเพจ) เพื่อเป็นกำลังใจให้ทีมงานด้วยนะครับ ❤️\n"
            f"✨ รับชมซีรีส์เต็มเรื่อง ดูฟรีไม่มีโฆษณาคั่นได้ที่นี่ทุกวัน!\n\n"
            f"#ซีรีส์จีน #หนังสั้นจีน #ซีรีส์จีนเต็มเรื่อง #พากย์ไทย #ละครสั้น #reels #reelsfb #viral #กดติดตาม"
        )
        return t, s, c

    def _composite_cinema_poster(self, base_img: Image.Image, title: str, subtitle: str) -> Image.Image:
        """ຕົກແຕ່ງຮູບດ້ວຍປ້າຍ Cinema, ກອບຫຼູຫຼາ, ແລະ ຂໍ້ຄວາມຄຸນນະພາບສູງ."""
        poster = base_img.copy()

        # 1. Dark Vignette Gradients (ເທິງ ແລະ ລຸ່ມ ເພື່ອໃຫ້ຂໍ້ຄວາມອ່ານງ່າຍ ແລະ ເດັ່ນຊັດ)
        overlay = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)

        # Top shadow
        for y in range(260):
            alpha = int(220 * (1 - y / 260))
            odraw.line([(0, y), (1080, y)], fill=(0, 0, 0, alpha))

        # Bottom shadow
        for y in range(780, 1080):
            alpha = int(240 * ((y - 780) / 300))
            odraw.line([(0, y), (1080, y)], fill=(0, 0, 0, alpha))

        poster = Image.alpha_composite(poster.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(poster)

        # 2. Font Loading
        font_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        font_title = self._load_font(font_dir, ["tahomabd.ttf", "arialbd.ttf", "seguisb.ttf"], size=54)
        font_sub = self._load_font(font_dir, ["tahoma.ttf", "arial.ttf", "segoeui.ttf"], size=30)
        font_badge = self._load_font(font_dir, ["tahomabd.ttf", "arialbd.ttf"], size=28)
        font_cta = self._load_font(font_dir, ["tahomabd.ttf", "arialbd.ttf"], size=36)

        # 3. Top Cinema Badge
        badge_text = "ซีรีส์จีน เต็มเรื่อง (Full Episode)"
        self._draw_pill_badge(draw, 540, 70, badge_text, font_badge, bg_color=(230, 57, 70), text_color=(255, 255, 255))

        # 4. Title & Subtitle at Lower Section
        # Title Background Banner Box
        t_w, t_h = self._get_text_size(draw, title, font_title)
        title_y = 830
        draw.rectangle([50, title_y - 12, 1030, title_y + t_h + 16], fill=(15, 15, 25, 220))
        # Gold accent line
        draw.line([(50, title_y - 12), (1030, title_y - 12)], fill=(255, 215, 0), width=3)

        # Title text with shadow
        draw.text((540 - t_w // 2 + 2, title_y + 2), title, font=font_title, fill=(0, 0, 0))
        draw.text((540 - t_w // 2, title_y), title, font=font_title, fill=(255, 240, 160))

        # Subtitle
        s_w, s_h = self._get_text_size(draw, subtitle, font_sub)
        sub_y = title_y + t_h + 26
        draw.text((540 - s_w // 2, sub_y), subtitle, font=font_sub, fill=(200, 225, 255))

        # 5. Bottom Big Follower CTA Bar
        cta_y = 980
        cta_text = "► กดติดตามเพจ เพื่อรับชมตอนใหม่ฟรี! ◄"
        self._draw_pill_badge(
            draw, 540, cta_y, cta_text, font_cta,
            bg_color=(255, 183, 3), text_color=(15, 15, 25),
            padding=(35, 14), border_color=(255, 255, 255), border_width=2
        )

        # 6. Luxury Golden Frame Border
        border_color = (255, 215, 0)
        draw.rectangle([16, 16, 1064, 1064], outline=border_color, width=3)
        draw.rectangle([24, 24, 1056, 1056], outline=(255, 215, 0, 140), width=1)
        # Corner accents
        corner_len = 50
        for x, y, dx, dy in [(16, 16, 1, 1), (1064, 16, -1, 1), (16, 1064, 1, -1), (1064, 1064, -1, -1)]:
            draw.line([(x, y), (x + dx * corner_len, y)], fill=(255, 255, 255), width=4)
            draw.line([(x, y), (x, y + dy * corner_len)], fill=(255, 255, 255), width=4)

        return poster

    def _draw_pill_badge(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, text: str, font: ImageFont.ImageFont,
                         bg_color=(230, 57, 70), text_color=(255, 255, 255), padding=(25, 8),
                         border_color=None, border_width=0):
        tw, th = self._get_text_size(draw, text, font)
        pad_x, pad_y = padding
        x1 = cx - tw // 2 - pad_x
        y1 = cy - th // 2 - pad_y
        x2 = cx + tw // 2 + pad_x
        y2 = cy + th // 2 + pad_y
        radius = (y2 - y1) // 2

        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=bg_color)
        if border_color and border_width > 0:
            draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=border_color, width=border_width)

        draw.text((cx - tw // 2, cy - th // 2 - 2), text, font=font, fill=text_color)

    def _get_text_size(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _load_font(self, font_dir: str, font_names: list, size: int) -> ImageFont.ImageFont:
        for fname in font_names:
            p = os.path.join(font_dir, fname)
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
        return ImageFont.load_default()
