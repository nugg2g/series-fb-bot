import os
import sys
import shutil
import tempfile
import unittest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.queue_manager import QueueManager
from core.caption_generator import CaptionGenerator
from core.uploader import ReelsUploader

class TestCompanionTextAndPhotos(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.videos_dir = os.path.join(self.temp_dir, "videos")
        self.completed_dir = os.path.join(self.temp_dir, "completed")
        self.failed_dir = os.path.join(self.temp_dir, "failed")
        os.makedirs(self.videos_dir, exist_ok=True)
        os.makedirs(self.completed_dir, exist_ok=True)
        os.makedirs(self.failed_dir, exist_ok=True)

        self.config = {
            "video_folder": self.videos_dir,
            "completed_folder": self.completed_dir,
            "failed_folder": self.failed_dir,
            "history_file": os.path.join(self.temp_dir, "history.json"),
            "move_completed_videos": True,
            "gemini_api_key": "" # fallback mode
        }
        self.qm = QueueManager(self.config)
        self.cg = CaptionGenerator(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_media_extensions(self):
        self.assertTrue(QueueManager.is_image_file("test.jpg"))
        self.assertTrue(QueueManager.is_image_file("photo.PNG"))
        self.assertTrue(QueueManager.is_image_file("pic.webp"))
        self.assertFalse(QueueManager.is_image_file("clip.mp4"))

        self.assertTrue(QueueManager.is_video_file("clip.mp4"))
        self.assertTrue(QueueManager.is_video_file("movie.MOV"))
        self.assertFalse(QueueManager.is_video_file("photo.jpg"))

    def test_find_companion_text_file(self):
        # 1. name.txt
        p1 = os.path.join(self.videos_dir, "clip1.mp4")
        t1 = os.path.join(self.videos_dir, "clip1.txt")
        with open(p1, "wb") as f: f.write(b"video content")
        with open(t1, "w", encoding="utf-8") as f: f.write("Hello Thai Text")
        self.assertEqual(QueueManager.find_companion_text_file(p1), t1)

        # 2. photo.caption.txt
        p2 = os.path.join(self.videos_dir, "photo1.jpg")
        t2 = os.path.join(self.videos_dir, "photo1.caption.txt")
        with open(p2, "wb") as f: f.write(b"image content")
        with open(t2, "w", encoding="utf-8") as f: f.write("Photo caption")
        self.assertEqual(QueueManager.find_companion_text_file(p2), t2)

        # 3. no companion txt
        p3 = os.path.join(self.videos_dir, "clip3.mp4")
        with open(p3, "wb") as f: f.write(b"video 3 content")
        self.assertIsNone(QueueManager.find_companion_text_file(p3))

    def test_companion_txt_encodings(self):
        # UTF-8 with BOM
        bom_file = os.path.join(self.videos_dir, "bom.txt")
        with open(bom_file, "w", encoding="utf-8-sig") as f:
            f.write("น้องข้าวหอมไปโรงเรียน\nสดใส น่ารักมากก")
        read_bom = CaptionGenerator.read_companion_text_file(bom_file)
        self.assertIn("น้องข้าวหอมไปโรงเรียน", read_bom)

        # CP874 (Thai Windows encoding)
        cp874_file = os.path.join(self.videos_dir, "cp874.txt")
        with open(cp874_file, "w", encoding="cp874") as f:
            f.write("สาวขี้ดื้อแจกความน่ารัก")
        read_cp874 = CaptionGenerator.read_companion_text_file(cp874_file)
        self.assertIn("สาวขี้ดื้อแจกความน่ารัก", read_cp874)

    def test_build_caption_with_companion_txt(self):
        # Video with companion txt
        v_path = os.path.join(self.videos_dir, "khaohom_01.mp4")
        txt_path = os.path.join(self.videos_dir, "khaohom_01.txt")
        with open(v_path, "wb") as f: f.write(b"dummy video")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("วันนี้แกล้งคุณครู สนุกมากก\nความน่ารักของน้องข้าวหอม วันนี้พกความสดใสมาเต็มเปี่ยม ฝากติดตามหนูด้วยน้า")

        res = self.cg.build_caption(
            video_path=v_path,
            content_type="lao_girl_khaohom"
        )
        self.assertEqual(res["source"], "companion_txt_file")
        self.assertEqual(res["title"], "วันนี้แกล้งคุณครู สนุกมากก")
        self.assertIn("ความน่ารักของน้องข้าวหอม", res["caption"])
        # Hashtags auto-appended
        self.assertIn("#น้องข้าวหอม", res["caption"])

    def test_build_caption_with_companion_txt_having_hashtags(self):
        # Photo with companion txt that already contains hashtags
        p_path = os.path.join(self.videos_dir, "photo_01.jpg")
        txt_path = os.path.join(self.videos_dir, "photo_01.txt")
        with open(p_path, "wb") as f: f.write(b"dummy image")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("ภาพน่ารักวันหยุด\nมาแจกความสดใสค่ะ ✨\n#น้องข้าวหอม #สาวขี้ดื้อ #วันหยุดน่ารัก")

        res = self.cg.build_caption(
            video_path=p_path,
            content_type="lao_girl_khaohom"
        )
        self.assertEqual(res["source"], "companion_txt_file")
        self.assertEqual(res["title"], "ภาพน่ารักวันหยุด")
        self.assertIn("#วันหยุดน่ารัก", res["caption"])

    def test_mark_completed_moves_both_media_and_companion_txt(self):
        # Create media and txt
        m_path = os.path.join(self.videos_dir, "post1.jpg")
        t_path = os.path.join(self.videos_dir, "post1.txt")
        with open(m_path, "wb") as f: f.write(b"test image 123")
        with open(t_path, "w", encoding="utf-8") as f: f.write("caption for post 1")

        self.assertTrue(os.path.exists(m_path))
        self.assertTrue(os.path.exists(t_path))

        self.qm.mark_completed(m_path)

        # Both should be gone from videos_dir
        self.assertFalse(os.path.exists(m_path))
        self.assertFalse(os.path.exists(t_path))

        # Both should be in completed_dir
        comp_m = os.path.join(self.completed_dir, "post1.jpg")
        comp_t = os.path.join(self.completed_dir, "post1.txt")
        self.assertTrue(os.path.exists(comp_m))
        self.assertTrue(os.path.exists(comp_t))

    def test_mark_failed_moves_both_media_and_companion_txt(self):
        m_path = os.path.join(self.videos_dir, "failed_clip.mp4")
        t_path = os.path.join(self.videos_dir, "failed_clip.txt")
        with open(m_path, "wb") as f: f.write(b"failed clip")
        with open(t_path, "w", encoding="utf-8") as f: f.write("failed clip caption")

        self.qm.mark_failed(m_path, error_message="Network error")

        # Both should be moved to failed_dir
        fail_m = os.path.join(self.failed_dir, "failed_clip.mp4")
        fail_t = os.path.join(self.failed_dir, "failed_clip.txt")
        self.assertTrue(os.path.exists(fail_m))
        self.assertTrue(os.path.exists(fail_t))

    def test_uploader_has_upload_photo(self):
        self.assertTrue(hasattr(ReelsUploader, "upload_photo"))
        self.assertTrue(callable(getattr(ReelsUploader, "upload_photo")))
        self.assertTrue(hasattr(ReelsUploader, "POST_COMPOSER_URL"))

if __name__ == "__main__":
    unittest.main()
