import os
import sys
import json
import tempfile
import unittest

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.caption_generator import CaptionGenerator
from core.queue_manager import QueueManager

class TestBotComponents(unittest.TestCase):
    def setUp(self):
        self.config = {
            "caption_template": "{title}\n\nຕິດຕາມຄລິບໃໝ່ໆ!\n\n{tags}",
            "tags_count": 4,
            "hashtag_pool": ["#reels", "#viral", "#fyp", "#trending", "#laos", "#shorts"],
            "video_folder": "./test_videos",
            "completed_folder": "./test_completed",
            "history_file": "./test_history.json",
            "move_completed_videos": False
        }

    def test_caption_cleaning(self):
        filename = "ep01_funny_dog_playing_[1080p]_fhd.mp4"
        clean = CaptionGenerator.clean_filename(filename)
        self.assertNotIn("[1080p]", clean)
        self.assertNotIn("fhd", clean.lower())
        self.assertIn("Funny Dog Playing", clean)

    def test_caption_template_building(self):
        cfg = dict(self.config)
        cfg["title_mode"] = "filename_clean"
        generator = CaptionGenerator(cfg)
        result = generator.build_caption("funny_cat_video.mp4", index=1)
        self.assertIn("Funny Cat Video", result["title"])
        self.assertIn("ຕິດຕາມຄລິບໃໝ່ໆ!", result["caption"])
        self.assertTrue("#" in result["caption"])

    def test_meaningful_filename_detection(self):
        self.assertTrue(CaptionGenerator.is_meaningful_filename("ປະທານປອມຕົວ_ep1.mp4"))
        self.assertTrue(CaptionGenerator.is_meaningful_filename("ceo_revenge_part1.mp4"))
        self.assertFalse(CaptionGenerator.is_meaningful_filename("12345.mp4"))
        self.assertFalse(CaptionGenerator.is_meaningful_filename("vid_01.mp4"))
        self.assertFalse(CaptionGenerator.is_meaningful_filename("clip001.mp4"))
        self.assertFalse(CaptionGenerator.is_meaningful_filename("a1b2c3d4e5f6071829.mp4"))
        # Test scraped Facebook junk filenames are correctly detected as non-meaningful
        self.assertFalse(CaptionGenerator.is_meaningful_filename("1.5M views · 40K reactions ｜ เต็มเรื่อง ｜ หัวจะปวด [1045610895020596].mp4"))
        self.assertFalse(CaptionGenerator.is_meaningful_filename("(เต็มเรื่อง) 🎬 กดติดตาม เพื่อจะได้ไม่พลาดซีรีย์ใหม่ๆ เต็ม เรื่อง.mp4"))
        self.assertFalse(CaptionGenerator.is_meaningful_filename("1.7M views · 56K reactions ｜ ภาพยนตร์ดังข้ามเวลา(เต็มเรื่อง) 👉https：⧸⧸heylink.me.mp4"))

    def test_china_ai_movie_fallback(self):
        cfg = dict(self.config)
        cfg["ai_caption"] = {"enabled": False}
        generator = CaptionGenerator(cfg)
        # Test generic file generates catchy China drama title
        result = generator.build_caption("123456.mp4", index=1)
        self.assertIn(result["source"], ["curated_drama_pool", "catchy_drama_engine"])
        self.assertTrue(len(result["title"]) > 5)
        self.assertNotIn("ตอนที่ 1", result["title"])

    def test_queue_manager(self):
        # Create temp folder with dummy files
        with tempfile.TemporaryDirectory() as temp_dir:
            v_dir = os.path.join(temp_dir, "vids")
            c_dir = os.path.join(temp_dir, "comp")
            h_file = os.path.join(temp_dir, "hist.json")
            os.makedirs(v_dir)
            os.makedirs(c_dir)

            test_file = os.path.join(v_dir, "video1.mp4")
            with open(test_file, "w") as f:
                f.write("dummy")

            qm_cfg = {
                "video_folder": v_dir,
                "completed_folder": c_dir,
                "failed_folder": os.path.join(temp_dir, "failed"),
                "history_file": h_file,
                "move_completed_videos": False
            }
            qm = QueueManager(qm_cfg)
            pending = qm.get_pending_videos()
            self.assertEqual(len(pending), 1)

            # Mark completed
            qm.mark_completed(test_file, {"caption": "test"})
            pending_after = qm.get_pending_videos()
            self.assertEqual(len(pending_after), 0)

            stats = qm.get_stats()
            self.assertEqual(stats["total_uploaded"], 1)

            # Test duplicate by hash even with different filename
            test_file_renamed = os.path.join(v_dir, "renamed_video1.mp4")
            with open(test_file_renamed, "w") as f:
                f.write("dummy") # identical content -> identical hash
            
            is_dup, reason = qm.is_already_uploaded(test_file_renamed)
            self.assertTrue(is_dup)
            self.assertIn("ໄຟລ໌ຊ້ຳ", reason)

            # Ensure it is excluded from pending queue
            pending_list = qm.get_pending_videos()
            self.assertNotIn(test_file_renamed, pending_list)

if __name__ == "__main__":
    unittest.main()
