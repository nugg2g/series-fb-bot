import os
import sys
import unittest

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.caption_generator import CaptionGenerator

class TestFilenameMovieTitles(unittest.TestCase):
    def setUp(self):
        self.config = {
            "title_mode": "filename_clean",
            "add_episode_number": False,
            "caption_template": "🎬 {title}\n\n🔥 ซีรีส์สั้นจีน AI ดราม่าเข้มข้น สุดมันส์!\n📌 ติดตามเรื่องใหม่ๆ ได้ทุกวัน อย่าลืมกด Like & Share!\n\n{tags}",
            "tags_count": 4,
            "hashtag_pool": ["#หนังสั้นจีน", "#ซีรีส์จีน", "#ละครสั้น", "#chinaai"],
            "ai_caption": {"enabled": False}
        }
        self.generator = CaptionGenerator(self.config)

    def test_scraped_movie_titles_extraction(self):
        test_cases = [
            (
                "1.1M views · 25K reactions ｜ เต็มเรื่อง 🎬 สนมอ้วนพร้อมระบบ ｜ มินิซีรี่ย์จีน [1091750576836625].mp4",
                "สนมอ้วนพร้อมระบบ"
            ),
            (
                "124K views · 3.2K reactions ｜ [FULL] ชายหนุ่มช่วยเด็กหญิงไว้ก่อนพบความจริงร้อยปี [1429700722391859].mp4",
                "ชายหนุ่มช่วยเด็กหญิงไว้ก่อนพบความจริงร้อยปี"
            ),
            (
                "126K views · 3.5K reactions ｜ (เต็มเรื่องในตอนเดียว) เถ้าถ่านเก้าดินแดน #ซีรีย์ส [1003021159367422].mp4",
                "เถ้าถ่านเก้าดินแดน"
            ),
            (
                "132K views · 5K reactions ｜ 🔥[เต็มเรื่อง] รักนิรันดร์ขององค์รัชทายาท 👉 ฝากกด ไลก [1606651551117405].mp4",
                "รักนิรันดร์ขององค์รัชทายาท"
            ),
            (
                "136K views · 3.8K reactions ｜ [Full] เกิดใหม่แล้ว ฉันไม่แต่งงานกับไฮโซ เลือกเงิน [1854253842207681].mp4",
                "เกิดใหม่แล้ว ฉันไม่แต่งงานกับไฮโซ เลือกเงิน"
            ),
            (
                "156K views · 4.9K reactions ｜ (เต็มเรื่อง) บะหมี่อันแสนวิเศษ ｜ เสื้อยืดปลีก-ส่ง [1127904003438667].mp4",
                "บะหมี่อันแสนวิเศษ"
            ),
            (
                "164K views · 4.7K reactions ｜ (เต็มเรื่อง) ตื่นจากหลับมา 100 ปี ทวงสัญญา 4 ตระกู [4490079987941633].mp4",
                "ตื่นจากหลับมา 100 ปี ทวงสัญญา 4 ตระกูลใหญ่"
            ),
            (
                "142K views · 4.7K reactions ｜ FULL- น้องสาวจ้างหนุ่มหน้าตาอัปลักษณ์ให้ปลอมเป็นสา [1801784687687325].mp4",
                "น้องสาวจ้างหนุ่มหน้าตาอัปลักษณ์ให้ปลอมเป็นสามี"
            )
        ]

        for filename, expected_title in test_cases:
            res = self.generator.build_caption(filename, index=1, title_prefix="[เต็มเรื่อง] ")
            self.assertEqual(res["source"], "filename")
            self.assertEqual(res["title"], f"[เต็มเรื่อง] {expected_title}")
            self.assertIn(f"[เต็มเรื่อง] {expected_title}", res["caption"])

    def test_scraped_spam_without_title_falls_back(self):
        # When filename contains only views and boilerplate like "กดติดตาม เพื่อจะได้ไม่พลาด"
        spam_filename = "122K views · 3.6K reactions ｜ เต็มเรือง) 🎬 กดติดตาม เพื่อจะได้ไม่พลาดซีรีย์ใหม่ๆ [1640042604506337].mp4"
        res = self.generator.build_caption(spam_filename, index=1, title_prefix="[เต็มเรื่อง] ")
        # Should gracefully fall back to curated drama pool since no real title is in the filename
        self.assertEqual(res["source"], "curated_drama_pool")
        self.assertTrue(len(res["title"]) > 5)

if __name__ == "__main__":
    unittest.main()
