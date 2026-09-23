import os
import sys
import json
import subprocess
from datetime import datetime

# Ensure current working directory is always the project directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QSpinBox, QCheckBox,
    QComboBox, QFileDialog, QTabWidget, QGroupBox, QRadioButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QInputDialog,
    QDialog, QFormLayout, QScrollArea, QFrame
)
from PySide6.QtGui import QFont, QIcon, QColor, QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PySide6.QtNetwork import QNetworkCookie

from core.engine import ReelUploadEngine
from core.caption_generator import CaptionGenerator, CONTENT_PRESETS
from core.queue_manager import QueueManager
from core.browser_manager import BrowserManager

CONFIG_PATH = os.path.abspath("./config.json")

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")

class WorkerThread(QThread):
    log_signal = Signal(str)
    status_signal = Signal(dict)
    progress_signal = Signal(int, str)
    finished_signal = Signal()

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.engine = ReelUploadEngine(
            config,
            log_cb=self.emit_log,
            status_cb=self.emit_status,
            progress_cb=self.emit_progress
        )

    def emit_log(self, msg: str):
        self.log_signal.emit(msg)

    def emit_status(self, stats: dict):
        self.status_signal.emit(stats)

    def emit_progress(self, pct: int, text: str):
        self.progress_signal.emit(pct, text)

    def run(self):
        self.engine._run_loop()
        self.finished_signal.emit()

    def pause(self):
        self.engine.pause()

    def stop(self):
        self.engine.stop()


class CheckPageThread(QThread):
    finished_signal = Signal(dict)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def run(self):
        from core.browser_manager import BrowserManager
        mgr = BrowserManager(self.config)
        t_name = self.config.get("page_name", "")
        t_id = str(self.config.get("page_id", ""))
        info = mgr.check_active_page_info(target_page_name=t_name, target_page_id=t_id)
        try:
            mgr.close()
        except Exception:
            pass
        self.finished_signal.emit(info)


class PostCtaThread(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def run(self):
        from core.engine import ReelUploadEngine
        engine = ReelUploadEngine(
            self.config,
            log_cb=self.log_signal.emit,
            progress_cb=self.progress_signal.emit
        )
        ok = engine.post_follower_cta()
        self.finished_signal.emit(ok)



class LoginThread(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.mgr = BrowserManager(config)

    def run(self):
        b_type = str(self.config.get("browser_type", "chromium")).lower()
        b_name = "Chromium (Browser ภายใน)" if b_type == "chromium" else ("Microsoft Edge" if b_type in ["msedge", "edge"] else "Google Chrome")
        self.log_signal.emit(f"🌐 กำลังเปิด {b_name}... กรุณา Login เข้าสู่ระบบ Facebook / Meta Business Suite และเลือก Page ที่ต้องการ.")
        try:
            page = self.mgr.open_for_manual_login()
            is_logged_in = False
            logged_in_notified = False
            for _ in range(600):
                import time
                time.sleep(2)
                if page.is_closed():
                    break
                try:
                    url = page.url.lower()
                    if "business.facebook.com" in url and "login" not in url and "checkpoint" not in url:
                        is_logged_in = True
                        if not logged_in_notified:
                            self.log_signal.emit(f"✅ ตรวจพบการ Login สำเร็จใน {b_name}! (สามารถเลือก Page แล้วปิดหน้าต่าง Browser ได้)")
                            logged_in_notified = True
                except Exception:
                    break
            self.mgr.close()
            self.finished_signal.emit(is_logged_in)
        except Exception as e:
            self.log_signal.emit(f"❌ เกิดข้อผิดพลาด: {e}")
            self.finished_signal.emit(False)


class EditHistoryDialog(QDialog):
    def __init__(self, parent=None, filename="", current_title="", current_caption="", current_status="pending"):
        super().__init__(parent)
        self.setWindowTitle(f"แก้ไขชื่อเรื่อง & แคปชั่น - {filename}")
        self.resize(620, 500)
        self.filename = filename

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.lbl_file = QLabel(filename)
        self.lbl_file.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 13px;")
        form.addRow("ชื่อไฟล์:", self.lbl_file)

        self.txt_title = QLineEdit(current_title)
        self.txt_title.setPlaceholderText("ใส่ชื่อเรื่อง Title ภาษาไทย เช่น 'ซีรีส์จีนสุดมันส์...'")
        form.addRow("ชื่อเรื่อง (Title):", self.txt_title)

        self.txt_caption = QTextEdit()
        self.txt_caption.setPlainText(current_caption)
        self.txt_caption.setPlaceholderText("ใส่ Caption หรือคำบรรยายพร้อมแท็ก...")
        form.addRow("แคปชั่น (Caption):", self.txt_caption)

        self.combo_status = QComboBox()
        self.combo_status.addItems(["pending (รออัปโหลด)", "success (อัปโหลดสำเร็จแล้ว)", "failed (ล้มเหลว)"])
        if current_status == "success":
            self.combo_status.setCurrentIndex(1)
        elif current_status == "failed":
            self.combo_status.setCurrentIndex(2)
        else:
            self.combo_status.setCurrentIndex(0)
        form.addRow("สถานะ:", self.combo_status)

        self.chk_requeue = QCheckBox("นำกลับเข้าคิวอัปโหลดใหม่ (Re-queue & Reset Duplicate Hash)")
        self.chk_requeue.setChecked(current_status != "pending")
        form.addRow("", self.chk_requeue)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 บันทึก")
        btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 16px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("ยกเลิก")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def get_data(self):
        status_map = {0: "pending", 1: "success", 2: "failed"}
        return {
            "title": self.txt_title.text().strip(),
            "caption": self.txt_caption.toPlainText().strip(),
            "status": status_map.get(self.combo_status.currentIndex(), "pending"),
            "requeue": self.chk_requeue.isChecked()
        }


class CustomWebEnginePage(QWebEnginePage):
    def createWindow(self, _type):
        return self


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.worker: WorkerThread = None
        self.login_worker: LoginThread = None

        self.setWindowTitle("Facebook Reels Auto Bot [2] 🤖 - ละครสั้นจีน AI (Thai Edition)")
        self.resize(1050, 780)
        self.setMinimumSize(950, 680)

        # In-App WebEngine Profile configuration (lazy loaded to prevent startup freeze)
        self.web_profile_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "webengine_profile"))
        self.web_profile = None
        self.webview = None
        self.browser_initialized = False
        self.cookies_cache = {}

        # Start Mobile Remote Monitor (Web Dashboard & Cloud Relay)
        from core.web_monitor import start_web_monitor, STATE as WEB_STATE, get_local_ip
        self.web_state = start_web_monitor(self.config, action_callback=self.handle_remote_action)
        local_p = self.config.get("web_monitor", {}).get("port", 5555)
        self.mobile_local_url = f"http://{get_local_ip()}:{local_p}"

        self.init_ui()
        self.apply_styles()
        self.load_cached_cookies()
        self.update_dashboard_pages_display()
        self.refresh_queue_stats()

        # Connect tab change listener
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Background warm-up of In-App browser after UI is already rendered
        QTimer.singleShot(1200, self.ensure_browser_initialized)

        # Setup auto refresh timer (lightweight signature check every 15s to prevent any UI stutter)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.auto_refresh_tick)
        self.refresh_timer.start(15000)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_dashboard_tab(), "🚀 แดชบอร์ด & อัปโหลด (Dashboard)")
        self.tabs.addTab(self.create_browser_tab(), "🌐 เบราว์เซอร์ในตัว (In-App Browser)")
        self.tabs.addTab(self.create_caption_tab(), "✍️ แคปชั่น & แท็ก (Caption Studio)")
        self.tabs.addTab(self.create_queue_tab(), "📋 คิว & ประวัติ (Queue & History)")
        self.tabs.addTab(self.create_settings_tab(), "⚙️ ตั้งค่าระบบ (Settings)")

        main_layout.addWidget(self.tabs)

    def create_dashboard_tab(self) -> QWidget:
        # Wrap everything in a smooth QScrollArea to prevent clipping and clutter
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # -------------------------------------------------------------
        # CARD 1: 🌐 ສະຖານະການເຊື່ອມຕໍ່ & ບັນຊີ (Connection & System Bar)
        # -------------------------------------------------------------
        card_conn = QFrame()
        card_conn.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #313244; border-radius: 8px; padding: 10px; }")
        conn_layout = QVBoxLayout(card_conn)
        conn_layout.setSpacing(8)

        # Row 1: Login Status + Browser Buttons
        c_r1 = QHBoxLayout()
        self.login_status_lbl = QLabel("🔴 ສະຖານະ: ຍັງບໍ່ໄດ້ກວດສອບ Login")
        self.login_status_lbl.setFont(QFont("Leelawadee UI", 10, QFont.Bold))
        c_r1.addWidget(self.login_status_lbl, stretch=2)

        btn_dash_auto = QPushButton("🔄 ດຶງ Cookies (1-Click)")
        btn_dash_auto.setStyleSheet("background-color: #7209b7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px;")
        btn_dash_auto.clicked.connect(self.auto_extract_cookies_from_browsers)
        c_r1.addWidget(btn_dash_auto)

        btn_open_inapp = QPushButton("🌐 ເປີດ In-App Browser")
        btn_open_inapp.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px;")
        btn_open_inapp.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        c_r1.addWidget(btn_open_inapp)

        b_type = str(self.config.get("browser_type", "chromium")).lower()
        b_name = "Chromium" if b_type == "chromium" else ("Microsoft Edge" if b_type in ["msedge", "edge"] else "Google Chrome")
        self.btn_login = QPushButton(f"🪟 ຫຼືເປີດ ({b_name})")
        self.btn_login.setStyleSheet("background-color: #3b4252; color: #d8dee9; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        self.btn_login.clicked.connect(self.handle_manual_login)
        c_r1.addWidget(self.btn_login)
        conn_layout.addLayout(c_r1)

        # Row 2: AI Status & Mobile Remote Link Bar
        c_r2 = QHBoxLayout()
        self.lbl_gemini_status = QLabel("🤖 Gemini AI: 🟢 ພ້ອມໃຊ້ງານ (Gemini 3.6 Flash)")
        self.lbl_gemini_status.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 11px;")
        c_r2.addWidget(self.lbl_gemini_status)

        c_r2.addSpacing(16)

        cloud_u = self.config.get("web_monitor", {}).get("cloud_relay_url", "").strip()
        if cloud_u:
            self.lbl_cloud_status = QLabel(f"☁️ <b>Mobile Web (24/7):</b> <a href='{cloud_u}' style='color: #38bdf8;'>{cloud_u}</a> <span style='background: #065f46; color: #34d399; padding: 2px 6px; border-radius: 4px; font-size: 10px;'>🟢 Online</span>")
        else:
            self.lbl_cloud_status = QLabel("☁️ <b>Mobile Web:</b> <span style='color: #94a3b8;'>ຍັງບໍ່ໄດ້ເຊື່ອມ Render.com</span>")
        self.lbl_cloud_status.setOpenExternalLinks(True)
        self.lbl_cloud_status.setTextFormat(Qt.RichText)
        c_r2.addWidget(self.lbl_cloud_status, stretch=2)

        self.lbl_mobile_link = QLabel(f"🏠 Wi-Fi: <a href='{self.mobile_local_url}' style='color: #4cc9f0;'>{self.mobile_local_url}</a>")
        self.lbl_mobile_link.setOpenExternalLinks(True)
        self.lbl_mobile_link.setTextFormat(Qt.RichText)
        self.lbl_mobile_link.setStyleSheet("font-size: 11px;")
        c_r2.addWidget(self.lbl_mobile_link)

        btn_qr_m = QPushButton("📲 QR Code ມືຖື")
        btn_qr_m.setStyleSheet("background-color: #6366f1; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        btn_qr_m.clicked.connect(self.show_mobile_qr_dialog)
        c_r2.addWidget(btn_qr_m)

        conn_layout.addLayout(c_r2)
        layout.addWidget(card_conn)

        # Hidden/Backwards-compatible Page 1 line edits
        self.txt_dash_page_name = QLineEdit(self.config.get("page_name", ""))
        self.txt_dash_page_name.setVisible(False)
        self.txt_dash_page_id = QLineEdit(str(self.config.get("page_id", "")))
        self.txt_dash_page_id.setVisible(False)

        # -------------------------------------------------------------
        # CARD 2: 🎯 ລາຍຊື່ 4 Facebook Pages & ໂຟນເດີວິດີໂອ
        # -------------------------------------------------------------
        pages_group = QGroupBox("🎯 ລາຍຊື່ 4 Facebook Pages (Round-Robin ສະຫຼັບກຸ່ມອັດຕະໂນມັດ)")
        pages_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 6px; padding: 10px; }")
        pg_layout = QVBoxLayout(pages_group)
        pg_layout.setSpacing(10)

        # 2 Columns for Groups
        pg_cols = QHBoxLayout()

        # Group 1 Card (3 Pages)
        self.card_g1 = QFrame()
        self.card_g1.setStyleSheet("background: #1e1e2e; border: 1px solid #2563eb; border-radius: 6px; padding: 8px;")
        g1_l = QVBoxLayout(self.card_g1)
        self.lbl_g1_hdr = QLabel("🔵 <b>ກຸ່ມ 1: 3 Pages ຮ່ວມກັນ</b> (ໜັງສັ້ນ/ຊີຣີສ໌ຈີນ AI [ເຕັມເລື່ອງ])")
        self.lbl_g1_hdr.setStyleSheet("color: #89b4fa; font-size: 12px;")
        g1_l.addWidget(self.lbl_g1_hdr)

        self.lbl_dash_g1_p1 = QLabel("1️⃣ <b>Page 1:</b> ซี่รีย์จีน เต็มเรื่อง (ID: 1332661329928072)")
        self.lbl_dash_g1_p2 = QLabel("2️⃣ <b>Page 2:</b> ติ่งซีรีส์จีน - ดูฟรีเต็มเรื่อง (ID: 1311717205364831)")
        self.lbl_dash_g1_p3 = QLabel("3️⃣ <b>Page 3:</b> ສະຫະພັນບານເຕະແຂວງສະຫວັນນະເຂດ (ID: 104640754387216)")
        self.lbl_dash_g1_fld = QLabel("📁 Folder: Y:/Movies FB")
        self.lbl_dash_g1_fld.setStyleSheet("color: #94a3b8; font-size: 11px;")

        for w in [self.lbl_dash_g1_p1, self.lbl_dash_g1_p2, self.lbl_dash_g1_p3, self.lbl_dash_g1_fld]:
            w.setStyleSheet("font-size: 11px; padding: 1px;")
            g1_l.addWidget(w)
        pg_cols.addWidget(self.card_g1, stretch=3)

        # Group 2 Card (1 Page)
        self.card_g2 = QFrame()
        self.card_g2.setStyleSheet("background: #1e1e2e; border: 1px solid #a855f7; border-radius: 6px; padding: 8px;")
        g2_l = QVBoxLayout(self.card_g2)
        self.lbl_g2_hdr = QLabel("🟣 <b>ກຸ່ມ 2: 1 Page ສະເພາະຕົວ</b> (ນ້ອງເຂົ້າຫອມ ສາວຂີ້ດື້)")
        self.lbl_g2_hdr.setStyleSheet("color: #cba6f7; font-size: 12px;")
        g2_l.addWidget(self.lbl_g2_hdr)

        self.lbl_dash_g2_p1 = QLabel("4️⃣ <b>Page 4:</b> น้องข้าวหอม สาวขี้ดื้อ (ID: 1384777811375983)")
        self.lbl_dash_g2_fld = QLabel("📁 Folder: Y:/Movies FB Dedicated")
        self.lbl_dash_g2_fld.setStyleSheet("color: #94a3b8; font-size: 11px;")
        for w in [self.lbl_dash_g2_p1, self.lbl_dash_g2_fld]:
            w.setStyleSheet("font-size: 11px; padding: 1px;")
            g2_l.addWidget(w)
        g2_l.addStretch()
        pg_cols.addWidget(self.card_g2, stretch=2)

        pg_layout.addLayout(pg_cols)

        # Quick Group Switcher & Folder Controls Row
        fld_row = QHBoxLayout()
        fld_row.addWidget(QLabel("📁 ໂຟນເດີວິດີໂອ:"))
        self.txt_folder = QLineEdit(self.config.get("video_folder", "./videos"))
        self.txt_folder.setMinimumHeight(30)
        self.txt_folder.textChanged.connect(self.on_folder_changed)
        fld_row.addWidget(self.txt_folder, stretch=3)

        btn_switch_g1 = QPushButton("🔵 ກຸ່ມ 1")
        btn_switch_g1.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-weight: bold; padding: 5px 10px; border-radius: 4px;")
        btn_switch_g1.clicked.connect(lambda: self.switch_active_dashboard_group(0))
        fld_row.addWidget(btn_switch_g1)

        btn_switch_g2 = QPushButton("🟣 ກຸ່ມ 2")
        btn_switch_g2.setStyleSheet("background-color: #581c87; color: #d8b4fe; font-weight: bold; padding: 5px 10px; border-radius: 4px;")
        btn_switch_g2.clicked.connect(lambda: self.switch_active_dashboard_group(1))
        fld_row.addWidget(btn_switch_g2)

        btn_browse = QPushButton("📁 ເລືອກ...")
        btn_browse.clicked.connect(self.browse_folder)
        fld_row.addWidget(btn_browse)

        btn_open_folder = QPushButton("📂 ເປີດ")
        btn_open_folder.clicked.connect(self.open_current_folder)
        fld_row.addWidget(btn_open_folder)

        btn_refresh = QPushButton("🔄 ອັບເດດຄິວ")
        btn_refresh.clicked.connect(self.manual_refresh_queue)
        fld_row.addWidget(btn_refresh)
        pg_layout.addLayout(fld_row)

        # Verification Row
        pg_act_row = QHBoxLayout()
        btn_config_pages = QPushButton("⚙️ ແກ້ໄຂ / ຕັ້ງຄ່າ 4 Pages")
        btn_config_pages.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
        btn_config_pages.clicked.connect(lambda: self.tabs.setCurrentIndex(4))
        pg_act_row.addWidget(btn_config_pages)

        pg_act_row.addWidget(QLabel("ກວດສອບ:"))
        self.cmb_dash_verify_page = QComboBox()
        self.cmb_dash_verify_page.setStyleSheet("background: #181825; color: #fab387; font-weight: bold; padding: 4px 8px; border: 1px solid #45475a; border-radius: 4px;")
        pg_act_row.addWidget(self.cmb_dash_verify_page, stretch=1)

        self.btn_verify_page = QPushButton("🔍 Verify Page")
        self.btn_verify_page.setStyleSheet("background-color: #0d9488; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
        self.btn_verify_page.clicked.connect(self.verify_selected_dashboard_page)
        pg_act_row.addWidget(self.btn_verify_page)

        self.lbl_verify_result = QLabel("🛡️ Strict Page Guard: ພ້ອມກວດສອບ Page ກ່ອນອັບໂຫຼດ")
        self.lbl_verify_result.setStyleSheet("color: #a6adc8; font-size: 11px;")
        pg_act_row.addWidget(self.lbl_verify_result, stretch=1)

        pg_layout.addLayout(pg_act_row)
        layout.addWidget(pages_group)

        # -------------------------------------------------------------
        # CARD 3: 🚀 ການຄວບຄຸມ & ຄວາມຄືບໜ້າ (Control Center & Progress)
        # -------------------------------------------------------------
        ctrl_card = QGroupBox("🚀 ສູນຄວບຄຸມ ແລະ ຄວາມຄືບໜ້າ (Control Center)")
        ctrl_card.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 6px; padding: 10px; }")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setSpacing(10)

        # 4 Stats Badges
        stats_layout = QHBoxLayout()
        self.lbl_stat_total = QLabel("📦 ທັງໝົດ: 0")
        self.lbl_stat_pending = QLabel("⏳ ລໍຖ້າ: 0")
        self.lbl_stat_duplicates = QLabel("⚠️ ໄຟລ໌ຊ້ຳ: 0")
        self.lbl_stat_uploaded = QLabel("✅ ສຳເລັດ: 0")
        for lbl in [self.lbl_stat_total, self.lbl_stat_pending, self.lbl_stat_duplicates, self.lbl_stat_uploaded]:
            lbl.setStyleSheet("background: #181825; color: #f1f5f9; padding: 8px 14px; border-radius: 6px; font-weight: bold; border: 1px solid #313244;")
            stats_layout.addWidget(lbl)
        ctrl_layout.addLayout(stats_layout)

        # Live Progress Bar
        self.upload_progress_lbl = QLabel("⏳ ສະຖານະ: ພ້ອມເຮັດວຽກ (Ready)")
        self.upload_progress_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #89b4fa;")
        ctrl_layout.addWidget(self.upload_progress_lbl)

        self.upload_progress_bar = QProgressBar()
        self.upload_progress_bar.setRange(0, 100)
        self.upload_progress_bar.setValue(0)
        self.upload_progress_bar.setTextVisible(True)
        self.upload_progress_bar.setFixedHeight(26)
        self.upload_progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #11111b;
                border: 1px solid #45475a;
                border-radius: 6px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:0.5 #7c3aed, stop:1 #06b6d4);
                border-radius: 5px;
            }
        """)
        ctrl_layout.addWidget(self.upload_progress_bar)

        # Settings options row
        opt_row = QHBoxLayout()
        self.rb_publish_now = QRadioButton("🚀 ໂພສທັນທີ")
        self.rb_schedule = QRadioButton("⏰ ຕັ້ງເວລາ")
        if self.config.get("post_mode", "now") == "schedule":
            self.rb_schedule.setChecked(True)
        else:
            self.rb_publish_now.setChecked(True)
        opt_row.addWidget(self.rb_publish_now)
        opt_row.addWidget(self.rb_schedule)

        opt_row.addSpacing(15)
        opt_row.addWidget(QLabel("ພັກລະຫວ່າງຄລິບ:"))
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(1, 180)
        self.spin_delay.setValue(int(self.config.get("delay_between_posts_minutes", 60)))
        self.spin_delay.setSuffix(" ນາທີ")
        opt_row.addWidget(self.spin_delay)

        opt_row.addSpacing(15)
        self.chk_headless = QCheckBox("Headless")
        self.chk_headless.setChecked(self.config.get("headless", True))
        opt_row.addWidget(self.chk_headless)

        self.chk_mark_ai = QCheckBox("🏷️ ເນື້ອຫາ AI")
        self.chk_mark_ai.setChecked(self.config.get("mark_as_ai_content", True))
        self.chk_mark_ai.setStyleSheet("color: #89b4fa; font-weight: bold;")
        opt_row.addWidget(self.chk_mark_ai)

        self.chk_auto_watch = QCheckBox("🔄 Continuous Watch")
        self.chk_auto_watch.setChecked(self.config.get("auto_watch_new_files", True))
        self.chk_auto_watch.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        opt_row.addWidget(self.chk_auto_watch)
        opt_row.addStretch()
        ctrl_layout.addLayout(opt_row)

        # Big Action Buttons Row
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("▶️ ເລີ່ມ Auto Upload (Start)")
        self.btn_start.setStyleSheet("background-color: #059669; color: white; font-weight: bold; font-size: 13px; padding: 10px; border-radius: 6px;")
        self.btn_start.clicked.connect(self.start_upload)

        self.btn_pause = QPushButton("⏸️ ພັກຊົ່ວຄາວ (Pause)")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setStyleSheet("background-color: #d97706; color: white; font-weight: bold; font-size: 13px; padding: 10px; border-radius: 6px;")
        self.btn_pause.clicked.connect(self.pause_upload)

        self.btn_stop = QPushButton("🛑 ຢຸດການເຮັດວຽກ (Stop)")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; font-size: 13px; padding: 10px; border-radius: 6px;")
        self.btn_stop.clicked.connect(self.stop_upload)

        btn_dash_cta = QPushButton("📸 Post CTA ມື້ນີ້ (AI)")
        btn_dash_cta.setStyleSheet("background-color: #7c3aed; color: white; font-weight: bold; font-size: 13px; padding: 10px; border-radius: 6px;")
        btn_dash_cta.setToolTip("ສັ່ງ Gen ຮູບພາບ AI ແລະ ໂພສເຊີນຊວນຕິດຕາມ Page ທັນທີ")
        btn_dash_cta.clicked.connect(self.execute_remote_cta)

        btn_row.addWidget(self.btn_start, stretch=2)
        btn_row.addWidget(self.btn_pause, stretch=1)
        btn_row.addWidget(self.btn_stop, stretch=1)
        btn_row.addWidget(btn_dash_cta, stretch=2)
        ctrl_layout.addLayout(btn_row)

        layout.addWidget(ctrl_card)

        # -------------------------------------------------------------
        # CARD 4: 📜 Real-time Execution Logs
        # -------------------------------------------------------------
        log_group = QGroupBox("📜 Real-time Execution Log (ບັນທຶກການເຮັດວຽກສົດ)")
        log_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 6px; padding: 8px; }")
        log_layout = QVBoxLayout(log_group)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9))
        self.txt_log.setMinimumHeight(160)
        self.txt_log.setStyleSheet("background-color: #11111b; color: #cdd6f4; border-radius: 6px; border: 1px solid #313244; padding: 6px;")
        log_layout.addWidget(self.txt_log)

        log_act_row = QHBoxLayout()
        btn_clear_log = QPushButton("🗑️ ລ້າງ Log")
        btn_clear_log.setStyleSheet("background-color: #313244; color: #a6adc8; padding: 4px 12px; border-radius: 4px;")
        btn_clear_log.clicked.connect(self.txt_log.clear)
        log_act_row.addStretch()
        log_act_row.addWidget(btn_clear_log)
        log_layout.addLayout(log_act_row)

        layout.addWidget(log_group)

        scroll.setWidget(widget)
        return scroll

    def update_account_display(self, source_info: str = ""):
        page_name = self.config.get("page_name", "").strip()
        page_id = str(self.config.get("page_id", "")).strip()

        # Find c_user from cache or cookies.json
        c_user = ""
        for c in self.cookies_cache.values():
            if c.get("name") == "c_user":
                c_user = str(c.get("value", ""))
                break

        if not c_user:
            cookies_file = os.path.join(self.config.get("user_profile_dir", "./user_profile"), "cookies.json")
            if os.path.exists(cookies_file):
                try:
                    with open(cookies_file, "r", encoding="utf-8") as f:
                        cookies = json.load(f)
                        c_user = str(next((c.get("value") for c in cookies if c.get("name") == "c_user"), ""))
                except Exception:
                    pass

        has_session = bool(c_user or any(c.get("name") in ["c_user", "xs"] for c in self.cookies_cache.values()))

        current_page = self.config.get("page_name", "").strip()
        current_id = str(self.config.get("page_id", "")).strip()

        if hasattr(self, 'txt_dash_page_name') and not self.txt_dash_page_name.hasFocus():
            self.txt_dash_page_name.setText(current_page)
        if hasattr(self, 'txt_dash_page_id') and not self.txt_dash_page_id.hasFocus():
            self.txt_dash_page_id.setText(current_id)
        if hasattr(self, 'txt_page_name') and not self.txt_page_name.hasFocus():
            self.txt_page_name.setText(current_page)
        if hasattr(self, 'txt_page_id') and not self.txt_page_id.hasFocus():
            self.txt_page_id.setText(current_id)

        if has_session:
            status_parts = ["🟢 สถานะ: Login แล้ว"]
            if source_info:
                status_parts[0] += f" ({source_info})"
            if page_name:
                status_parts.append(f"📄 Page: {page_name}")
            if page_id:
                status_parts.append(f"ID: {page_id}")
            if c_user:
                status_parts.append(f"👤 UID: {c_user}")

            full_text = " | ".join(status_parts)
            self.login_status_lbl.setText(full_text)
            self.login_status_lbl.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 11px;")

            if hasattr(self, 'lbl_inapp_status'):
                inapp_parts = ["🟢 Login สำเร็จแล้ว"]
                if page_name:
                    inapp_parts.append(f"Page: {page_name}")
                if page_id:
                    inapp_parts.append(f"(ID: {page_id})")
                if c_user:
                    inapp_parts.append(f"(UID: {c_user})")
                self.lbl_inapp_status.setText(" | ".join(inapp_parts))
                self.lbl_inapp_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")

            base_title = "Facebook Reels Auto Bot [2] 🤖 - ละครสั้นจีน AI (Thai Edition)"
            if page_name:
                self.setWindowTitle(f"{base_title} - [{page_name}] (ID: {page_id})")
            else:
                self.setWindowTitle(base_title)
        else:
            msg = "🔴 สถานะ: ยังไม่ได้ Login"
            if page_name:
                msg += f" | 📄 Page: {page_name}"
            if page_id:
                msg += f" (ID: {page_id})"
            self.login_status_lbl.setText(msg)
            self.login_status_lbl.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 11px;")

            if hasattr(self, 'lbl_inapp_status'):
                self.lbl_inapp_status.setText("🔴 ยังไม่ได้ Login Facebook")
                self.lbl_inapp_status.setStyleSheet("color: #f38ba8; font-weight: bold;")

    def save_dash_page_name(self):
        new_name = self.txt_dash_page_name.text().strip()
        new_id = self.txt_dash_page_id.text().strip() if hasattr(self, 'txt_dash_page_id') else ""
        if not new_name and not new_id:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาใส่ชื่อ Facebook Page หรือ Page ID ที่ต้องการโพสต์.")
            return
        if new_name:
            self.config["page_name"] = new_name
            if hasattr(self, 'txt_page_name'):
                self.txt_page_name.setText(new_name)
        if new_id:
            self.config["page_id"] = new_id
            if hasattr(self, 'txt_page_id'):
                self.txt_page_id.setText(new_id)

        target_pages = self.config.get("target_pages", [])
        if not target_pages:
            self.config["target_pages"] = [{"page_name": new_name, "page_id": new_id}]
        else:
            self.config["target_pages"][0]["page_name"] = new_name
            self.config["target_pages"][0]["page_id"] = new_id

        if hasattr(self, 'txt_target_pages'):
            lines = [f"{p.get('page_name', '')} | {p.get('page_id', '')}" for p in self.config["target_pages"]]
            self.txt_target_pages.setPlainText("\n".join(lines))

        save_config(self.config)
        self.update_account_display()
        self.log_message(f"💾 บันทึก Facebook Page: {new_name} (ID: {new_id})")
        QMessageBox.information(self, "สำเร็จ", f"บันทึก Facebook Page เรียบร้อยแล้ว:\n{new_name}\nPage ID: {new_id}")

    def on_webengine_cookie_added(self, cookie: QNetworkCookie):
        try:
            c_name = cookie.name().data().decode('utf-8', errors='ignore')
            c_val = cookie.value().data().decode('utf-8', errors='ignore')
            domain = cookie.domain()
            path = cookie.path()

            pw_cookie = {
                'name': c_name,
                'value': c_val,
                'domain': domain if domain.startswith('.') else f".{domain}",
                'path': path or '/',
                'secure': cookie.isSecure(),
                'httpOnly': cookie.isHttpOnly()
            }
            if not cookie.isSessionCookie() and cookie.expirationDate().isValid():
                pw_cookie['expires'] = cookie.expirationDate().toSecsSinceEpoch()

            key = f"{domain}:{path}:{c_name}"
            self.cookies_cache[key] = pw_cookie

            if c_name in ["c_user", "xs"]:
                self.save_cookies_to_file()
                self.update_account_display()
        except Exception:
            pass

    def save_cookies_to_file(self):
        cookies_list = list(self.cookies_cache.values())
        if not cookies_list:
            return
        cookies_file = os.path.join(self.config.get("user_profile_dir", "./user_profile"), "cookies.json")
        os.makedirs(os.path.dirname(os.path.abspath(cookies_file)), exist_ok=True)
        try:
            with open(cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies_list, f, indent=2)
        except Exception as e:
            print(f"Error saving cookies.json: {e}")

    def load_cached_cookies(self):
        cookies_file = os.path.join(self.config.get("user_profile_dir", "./user_profile"), "cookies.json")
        has_valid_session = False
        if os.path.exists(cookies_file):
            try:
                with open(cookies_file, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    for c in cookies:
                        key = f"{c.get('domain')}:{c.get('path')}:{c.get('name')}"
                        self.cookies_cache[key] = c
                        if c.get("name") in ["c_user", "xs"]:
                            has_valid_session = True
            except Exception:
                pass

        # If no saved session, automatically search Firefox / Chrome / Edge for active Facebook login!
        if not has_valid_session:
            try:
                from core.cookie_extractor import extract_facebook_cookies
                auto_cookies, b_name = extract_facebook_cookies()
                if auto_cookies and any(c.get("name") in ["c_user", "xs"] for c in auto_cookies):
                    for c in auto_cookies:
                        key = f"{c.get('domain')}:{c.get('path')}:{c.get('name')}"
                        self.cookies_cache[key] = c
                    self.save_cookies_to_file()
                    has_valid_session = True
                    print(f"[AutoCookies] Automatically loaded {len(auto_cookies)} Facebook cookies from {b_name}!")
            except Exception as e:
                print(f"[AutoCookies] Notice: {e}")

        self.update_account_display()

    def auto_extract_cookies_from_browsers(self):
        try:
            from core.cookie_extractor import extract_facebook_cookies
            cookies, b_name = extract_facebook_cookies()
            if not cookies or not any(c.get("name") in ["c_user", "xs"] for c in cookies):
                QMessageBox.warning(
                    self,
                    "ไม่พบข้อมูล Login",
                    "ระบบค้นหาใน Firefox, Chrome, Edge, Brave, Opera แล้ว\nแต่ยังไม่พบบัญชี Facebook ที่เข้าสู่ระบบอยู่\n\nกรุณาเข้าสู่ระบบ Facebook ใน Browser ตามปกติก่อน แล้วกดปุ่มนี้อีกครั้ง"
                )
                return

            for c in cookies:
                key = f"{c.get('domain', '.facebook.com')}:{c.get('path', '/')}:{c.get('name')}"
                self.cookies_cache[key] = c
                try:
                    q_cookie = QNetworkCookie(c.get('name', '').encode('utf-8'), c.get('value', '').encode('utf-8'))
                    q_cookie.setDomain(c.get('domain', '.facebook.com'))
                    q_cookie.setPath(c.get('path', '/'))
                    self.web_profile.cookieStore().setCookie(q_cookie)
                except Exception:
                    pass

            self.save_cookies_to_file()
            self.update_account_display(f"ดึงจาก {b_name}")
            if hasattr(self, 'webview'):
                self.webview.load(QUrl("https://business.facebook.com/latest/home"))

            u_id = next((c['value'] for c in cookies if c['name'] == 'c_user'), '')
            QMessageBox.information(
                self,
                "สำเร็จ",
                f"ดึง Cookies Facebook จาก {b_name} สำเร็จแล้ว!\n(Facebook User ID: {u_id})\n\nระบบพร้อมใช้งานในการอัปโหลดทันที!"
            )
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการดึง Cookies: {e}")

    def manual_save_inapp_cookies(self):
        self.save_cookies_to_file()
        self.update_account_display()
        has_session = any(c.get("name") in ["c_user", "xs"] for c in self.cookies_cache.values())
        if has_session:
            QMessageBox.information(self, "สำเร็จ", "ตรวจพบและบันทึก Session Facebook สำเร็จแล้ว!\nระบบพร้อมใช้งานในการอัปโหลด Reels.")
        else:
            QMessageBox.warning(self, "แจ้งเตือน", "ยังไม่พบ Session การ Login Facebook\nกรุณาเข้าสู่ระบบ Facebook ให้เรียบร้อยก่อนกดปุ่มนี้.")

    def create_browser_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Toolbar
        bar = QHBoxLayout()
        btn_back = QPushButton("⬅️")
        btn_fwd = QPushButton("➡️")
        btn_reload = QPushButton("🔄")
        btn_back.setToolTip("ย้อนกลับ")
        btn_fwd.setToolTip("ถัดไป")
        btn_reload.setToolTip("รีเฟรช")

        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("https://business.facebook.com...")
        self.txt_url.returnPressed.connect(self.navigate_to_url)
        btn_go = QPushButton("🔍 ไปที่ลิงก์")
        btn_go.clicked.connect(self.navigate_to_url)

        btn_fb = QPushButton("📘 Facebook.com")
        btn_mbs = QPushButton("💼 Meta Business Suite")
        btn_auto = QPushButton("🔄 ดึงจาก Browser อัตโนมัติ")
        btn_auto.setStyleSheet("background-color: #7209b7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_auto.clicked.connect(self.auto_extract_cookies_from_browsers)

        btn_save = QPushButton("💾 บันทึก Cookies")
        btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_save.clicked.connect(self.manual_save_inapp_cookies)

        btn_paste = QPushButton("📋 วาง Cookies")
        btn_paste.setStyleSheet("background-color: #4361ee; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_paste.clicked.connect(self.prompt_paste_cookies)

        self.lbl_inapp_status = QLabel("⚪ กำลังตรวจสอบสถานะ...")
        self.lbl_inapp_status.setFont(QFont("Leelawadee UI", 9, QFont.Bold))

        self.btn_web_back = btn_back
        self.btn_web_fwd = btn_fwd
        self.btn_web_reload = btn_reload
        self.btn_web_fb = btn_fb
        self.btn_web_mbs = btn_mbs
        self.btn_web_save = btn_save

        bar.addWidget(btn_back)
        bar.addWidget(btn_fwd)
        bar.addWidget(btn_reload)
        bar.addWidget(self.txt_url)
        bar.addWidget(btn_go)
        bar.addWidget(btn_fb)
        bar.addWidget(btn_mbs)
        bar.addWidget(btn_auto)
        bar.addWidget(btn_save)
        bar.addWidget(btn_paste)
        bar.addWidget(self.lbl_inapp_status)
        layout.addLayout(bar)

        # Progress bar
        self.web_progress = QProgressBar()
        self.web_progress.setMaximumHeight(3)
        self.web_progress.setTextVisible(False)
        self.web_progress.setStyleSheet("QProgressBar::chunk { background-color: #06d6a0; } QProgressBar { border: none; background: transparent; }")
        layout.addWidget(self.web_progress)

        # Lazy Container for WebEngine View (prevents 2s startup lag)
        self.browser_content_layout = layout
        self.browser_placeholder = QLabel("🌐 ກຳລັງຕຽມພ້ອມ In-App Browser... (ກົດທີ່ແທັບນີ້ເພື່ອເປີດ Facebook & Meta Business Suite)")
        self.browser_placeholder.setAlignment(Qt.AlignCenter)
        self.browser_placeholder.setStyleSheet("color: #89b4fa; font-size: 13px; padding: 40px;")
        layout.addWidget(self.browser_placeholder)

        # Quick return banner
        banner_layout = QHBoxLayout()
        lbl_hint = QLabel("💡 เข้าสู่ระบบ Facebook และเลือก Page ในหน้านี้ได้โดยตรง เมื่อ Login เสร็จระบบจะจำ Cookies อัตโนมัติ")
        lbl_hint.setStyleSheet("color: #89b4fa; font-style: italic;")
        btn_go_dash = QPushButton("🚀 ไปที่หน้าแดชบอร์ดเพื่อเริ่มอัปโหลด (Go to Dashboard)")
        btn_go_dash.setStyleSheet("background-color: #2a9d8f; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_go_dash.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        banner_layout.addWidget(lbl_hint)
        banner_layout.addStretch()
        banner_layout.addWidget(btn_go_dash)
        layout.addLayout(banner_layout)

        return widget

    def ensure_browser_initialized(self):
        """Initializes heavy Chromium WebEngine on-demand without blocking initial startup window."""
        if getattr(self, 'browser_initialized', False):
            return
        self.browser_initialized = True

        try:
            if not self.web_profile:
                os.makedirs(self.web_profile_path, exist_ok=True)
                self.web_profile = QWebEngineProfile("FBInAppProfile2", self)
                self.web_profile.setPersistentStoragePath(self.web_profile_path)
                self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
                self.web_profile.setHttpUserAgent(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
                )
                settings = self.web_profile.settings()
                settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
                self.web_profile.cookieStore().cookieAdded.connect(self.on_webengine_cookie_added)
                self.web_profile.cookieStore().loadAllCookies()

            # Initialize WebEngine View
            self.webview = QWebEngineView()
            self.webpage = CustomWebEnginePage(self.web_profile, self.webview)
            self.webview.setPage(self.webpage)

            if hasattr(self, 'btn_web_back'):
                self.btn_web_back.clicked.connect(self.webview.back)
            if hasattr(self, 'btn_web_fwd'):
                self.btn_web_fwd.clicked.connect(self.webview.forward)
            if hasattr(self, 'btn_web_reload'):
                self.btn_web_reload.clicked.connect(self.webview.reload)
            if hasattr(self, 'btn_web_fb'):
                self.btn_web_fb.clicked.connect(lambda: self.webview.load(QUrl("https://www.facebook.com")))
            if hasattr(self, 'btn_web_mbs'):
                self.btn_web_mbs.clicked.connect(lambda: self.webview.load(QUrl("https://business.facebook.com/latest/home")))
            if hasattr(self, 'btn_web_save'):
                self.btn_web_save.clicked.connect(self.manual_save_inapp_cookies)

            self.webview.urlChanged.connect(lambda u: self.txt_url.setText(u.toString()))
            self.webview.loadProgress.connect(self.on_load_progress)
            self.webview.loadFinished.connect(self.on_load_finished)

            if hasattr(self, 'browser_placeholder') and self.browser_placeholder:
                self.browser_placeholder.setParent(None)
                self.browser_placeholder = None

            if hasattr(self, 'browser_content_layout'):
                self.browser_content_layout.insertWidget(2, self.webview)

            self.webview.load(QUrl("https://business.facebook.com/latest/home"))
        except Exception as e:
            print(f"[AppGUI] Error initializing In-App WebEngine: {e}")

    def navigate_to_url(self):
        text = self.txt_url.text().strip()
        if not text:
            return
        if not text.startswith("http://") and not text.startswith("https://"):
            text = "https://" + text
        self.webview.load(QUrl(text))

    def on_load_progress(self, progress: int):
        self.web_progress.setValue(progress)
        if progress >= 100:
            self.web_progress.setVisible(False)
        else:
            self.web_progress.setVisible(True)

    def on_load_finished(self, ok: bool):
        self.web_progress.setVisible(False)
        self.web_profile.cookieStore().loadAllCookies()
        current_url = self.webview.url().toString().lower()
        if "business.facebook.com" in current_url and "login" not in current_url and "checkpoint" not in current_url:
            self.save_cookies_to_file()
            self.update_account_display()

    def prompt_paste_cookies(self):
        text, ok = QInputDialog.getMultiLineText(
            self,
            "วาง Cookies Facebook",
            "กรุณาวาง Cookies ของ Facebook ที่คัดลอกมาจาก Browser อื่น\n(รองรับรูปแบบ c_user=...; xs=... หรือ JSON):",
            ""
        )
        if ok and text.strip():
            cookies = self.parse_cookie_input(text.strip())
            if not cookies:
                QMessageBox.warning(self, "แจ้งเตือน", "ไม่พบรูปแบบ Cookies ที่ถูกต้อง\nกรุณาตรวจสอบว่ามีค่า c_user และ xs")
                return

            for c in cookies:
                key = f"{c.get('domain', '.facebook.com')}:{c.get('path', '/')}:{c.get('name')}"
                self.cookies_cache[key] = c
                try:
                    q_cookie = QNetworkCookie(c.get('name', '').encode('utf-8'), c.get('value', '').encode('utf-8'))
                    q_cookie.setDomain(c.get('domain', '.facebook.com'))
                    q_cookie.setPath(c.get('path', '/'))
                    self.web_profile.cookieStore().setCookie(q_cookie)
                except Exception:
                    pass

            self.save_cookies_to_file()
            self.update_account_display()
            has_session = any(c.get("name") in ["c_user", "xs"] for c in self.cookies_cache.values())
            if has_session:
                self.webview.load(QUrl("https://business.facebook.com/latest/home"))
                QMessageBox.information(self, "สำเร็จ", "นำเข้า Cookies Facebook สำเร็จแล้ว!\nกำลังโหลดหน้า Meta Business Suite...")
            else:
                QMessageBox.warning(self, "แจ้งเตือน", "Cookies ที่วางไม่มี c_user หรือ xs ของ Facebook.")

    def parse_cookie_input(self, raw: str) -> list:
        raw = raw.strip()
        if raw.startswith("[") or raw.startswith("{"):
            try:
                import json
                data = json.loads(raw)
                return [data] if isinstance(data, dict) else data
            except Exception:
                pass
        results = []
        for p in raw.split(";"):
            if "=" in p:
                k, v = p.strip().split("=", 1)
                k = k.strip()
                v = v.strip()
                if k:
                    results.append({
                        "name": k,
                        "value": v,
                        "domain": ".facebook.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": False
                    })
        return results

    def create_caption_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Template Box
        tpl_group = QGroupBox("Caption Template (รูปแบบแคปชั่น)")
        tpl_layout = QVBoxLayout(tpl_group)

        tags_bar = QHBoxLayout()
        tags_bar.addWidget(QLabel("คลิกเพื่อแทรกตัวแปร:"))
        for token in ["{title}", "{tags}", "{date}", "{time}", "{index}", "{filename}"]:
            btn = QPushButton(token)
            btn.clicked.connect(lambda _, t=token: self.insert_token(t))
            tags_bar.addWidget(btn)
        tpl_layout.addLayout(tags_bar)

        self.txt_template = QTextEdit()
        self.txt_template.setPlainText(self.config.get("caption_template", "{title}\n\n{tags}"))
        self.txt_template.textChanged.connect(self.update_preview)
        tpl_layout.addWidget(self.txt_template)

        layout.addWidget(tpl_group)

        # Hashtags & Tag count
        tag_group = QGroupBox("Hashtags Pool (คลังแฮชแท็กสำหรับสุ่มใส่)")
        tag_layout = QVBoxLayout(tag_group)

        tag_count_row = QHBoxLayout()
        tag_count_row.addWidget(QLabel("จำนวน Tag ที่ต้องการใส่ต่อ 1 คลิป:"))
        self.spin_tags_count = QSpinBox()
        self.spin_tags_count.setRange(1, 30)
        self.spin_tags_count.setValue(int(self.config.get("tags_count", 6)))
        self.spin_tags_count.valueChanged.connect(self.update_preview)
        tag_count_row.addWidget(self.spin_tags_count)
        tag_count_row.addStretch()
        tag_layout.addLayout(tag_count_row)

        self.txt_hashtags = QTextEdit()
        pool = self.config.get("hashtag_pool", ["#หนังสั้นจีน", "#ซีรีส์จีน", "#chinaai"])
        self.txt_hashtags.setPlainText("\n".join(pool))
        self.txt_hashtags.textChanged.connect(self.update_preview)
        tag_layout.addWidget(self.txt_hashtags)

        layout.addWidget(tag_group)

        # China AI Movie & Intelligent Title Mode
        china_group = QGroupBox("🇨🇳 ระบบตั้งชื่อเรื่อง & วิเคราะห์หน้าปก (Intelligent Drama Title Engine)")
        china_layout = QVBoxLayout(china_group)
        
        mode_row = QHBoxLayout()
        self.rb_title_auto = QRadioButton("🌟 สร้างชื่อเรื่องดราม่า AI อัตโนมัติทุกคลิป (วิเคราะห์หน้าปก + ไม่สนชื่อไฟล์เดิม)")
        self.rb_title_filename = QRadioButton("📁 ใช้ชื่อจากไฟล์วิดีโอ (เฉพาะเมื่อตั้งชื่อไฟล์เอง)")
        
        t_mode = self.config.get("title_mode", "auto_ai_drama")
        if t_mode == "filename_clean":
            self.rb_title_filename.setChecked(True)
        else:
            self.rb_title_auto.setChecked(True)
            
        self.rb_title_auto.toggled.connect(self.update_preview)
        self.rb_title_filename.toggled.connect(self.update_preview)
        
        mode_row.addWidget(self.rb_title_auto)
        mode_row.addWidget(self.rb_title_filename)
        mode_row.addStretch()
        china_layout.addLayout(mode_row)

        self.chk_add_episode_number = QCheckBox("ใส่วลี 'ตอนที่ 1, ตอนที่ 2...' ต่อท้ายชื่อเรื่อง (หากไม่เลือก จะเป็นชื่อเรื่องเดี่ยวๆ แบบเต็มเรื่องจบ)")
        self.chk_add_episode_number.setChecked(self.config.get("add_episode_number", False))
        self.chk_add_episode_number.toggled.connect(self.update_preview)
        china_layout.addWidget(self.chk_add_episode_number)

        info_lbl = QLabel(
            "💡 แนะนำ: เลือก 'สร้างชื่อเรื่องดราม่า AI อัตโนมัติ' เพื่อให้ระบบใช้ Gemini AI วิเคราะห์ภาพหน้าปก\n"
            "และเติมเต็มประโยคชื่อเรื่องให้สมบูรณ์ น่าติดตาม แบบเต็มเรื่องจบ โดยไม่ต้องมานั่งเปลี่ยนชื่อไฟล์เอง!"
        )
        info_lbl.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        china_layout.addWidget(info_lbl)

        btn_test_video = QPushButton("🎬 ทดสอบวิเคราะห์ชื่อเรื่องจากไฟล์วิดีโอจริง...")
        btn_test_video.setStyleSheet("background-color: #3b4252; color: #88c0d0; font-weight: bold;")
        btn_test_video.clicked.connect(self.test_video_analysis)
        china_layout.addWidget(btn_test_video)

        layout.addWidget(china_group)

        # Live Preview
        prev_group = QGroupBox("ตัวอย่าง Caption ที่จะโพสต์ (Live Preview สมมติ)")
        prev_layout = QVBoxLayout(prev_group)
        self.txt_preview = QTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setStyleSheet("background-color: #242526; color: #e4e6eb; padding: 8px;")
        prev_layout.addWidget(self.txt_preview)
        layout.addWidget(prev_group)

        btn_save_tpl = QPushButton("💾 บันทึกการตั้งค่า Caption & Tags")
        btn_save_tpl.clicked.connect(self.save_caption_settings)
        layout.addWidget(btn_save_tpl)

        self.update_preview()
        return widget

    def create_queue_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        top_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 Refresh คิว")
        btn_refresh.clicked.connect(self.refresh_queue_table)

        btn_restore = QPushButton("🔄 กู้คืนวิดีโอจาก Completed กลับมาคิว (Restore All)")
        btn_restore.setStyleSheet("background-color: #d97706; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_restore.clicked.connect(self.restore_all_completed_action)

        btn_edit = QPushButton("✏️ แก้ไขชื่อเรื่อง / Re-queue")
        btn_edit.setStyleSheet("background-color: #4361ee; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_edit.clicked.connect(self.edit_selected_history_item)

        btn_clear_hist = QPushButton("🗑️ ล้างประวัติ Upload")
        btn_clear_hist.clicked.connect(self.clear_history)
        btn_open_completed = QPushButton("📂 เปิดโฟลเดอร์ Completed")
        btn_open_completed.clicked.connect(self.open_completed_folder)

        top_row.addWidget(btn_refresh)
        top_row.addWidget(btn_restore)
        top_row.addWidget(btn_edit)
        top_row.addWidget(btn_clear_hist)
        top_row.addWidget(btn_open_completed)
        top_row.addStretch()
        layout.addLayout(top_row)

        lbl_hint = QLabel("💡 เคล็ดลับ: ดับเบิลคลิกที่แถววิดีโอเพื่อแก้ไขชื่อเรื่อง (Title), แคปชั่น หรือนำกลับเข้าคิวใหม่อัตโนมัติ")
        lbl_hint.setStyleSheet("color: #a6adc8; font-size: 11px; padding: 2px;")
        layout.addWidget(lbl_hint)

        self.table_queue = QTableWidget()
        self.table_queue.setColumnCount(6)
        self.table_queue.setHorizontalHeaderLabels(["#", "ชื่อไฟล์วิดีโอ", "Title ที่ตั้งไว้", "สถานะ (Status)", "เวลาอัปโหลด", "เส้นทางไฟล์"])
        self.table_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_queue.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_queue.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_queue.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table_queue.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_queue.doubleClicked.connect(self.on_table_row_double_clicked)
        layout.addWidget(self.table_queue)

        # Table will populate when user clicks Tab 3 (on_tab_changed) or via deferred singleShot
        return widget

    def create_settings_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #181825;
            }
            QScrollBar:vertical {
                border: none;
                background: #1e1e2e;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #45475a;
                min-height: 25px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #585b70;
            }
        """)

        widget = QWidget()
        widget.setStyleSheet("background-color: #181825;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 24)
        layout.setSpacing(16)

        # -------------------------------------------------------------
        # CARD 1: Multi-Page & Multi-Folder Groups Management
        # -------------------------------------------------------------
        groups_box = QGroupBox("🗂️ ຈັດການກຸ່ມ Facebook Pages & Folder ວິດີໂອ (Multi-Page & Multi-Folder)")
        groups_layout = QVBoxLayout(groups_box)
        groups_layout.setSpacing(12)
        groups_layout.setContentsMargins(12, 16, 12, 16)

        lbl_groups_hint = QLabel("ກຳນົດ Folder ວິດີໂອ ແລະ ລາຍຊື່ Facebook Pages ແຍກຕາມແຕ່ລະກຸ່ມ (ປ້ອງກັນລົງຜິດເພຈ 100%):")
        lbl_groups_hint.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 11px; padding: 2px;")
        groups_layout.addWidget(lbl_groups_hint)

        p_groups = self.config.get("page_groups", [])
        g1_data = p_groups[0] if len(p_groups) > 0 else {}
        g2_data = p_groups[1] if len(p_groups) > 1 else {}

        g1_pages = g1_data.get("pages", [])
        g1_p1 = g1_pages[0] if len(g1_pages) > 0 else {"page_name": self.config.get("page_name", ""), "page_id": str(self.config.get("page_id", ""))}
        g1_p2 = g1_pages[1] if len(g1_pages) > 1 else {"page_name": "", "page_id": ""}
        g1_p3 = g1_pages[2] if len(g1_pages) > 2 else {"page_name": "", "page_id": ""}

        g2_pages = g2_data.get("pages", [])
        g2_p1 = g2_pages[0] if len(g2_pages) > 0 else {"page_name": "", "page_id": ""}

        # --- Group 1 Box ---
        g1_box = QGroupBox("🔵 ກຸ່ມທີ 1: 3 Pages (ເນື້ອຫາຮ່ວມກັນ / Shared Content)")
        g1_box.setStyleSheet("QGroupBox { font-weight: bold; color: #89b4fa; border: 1px solid #3b82f6; border-radius: 6px; margin-top: 6px; padding: 12px; }")
        g1_layout = QVBoxLayout(g1_box)
        g1_layout.setSpacing(10)

        g1_cat_row = QHBoxLayout()
        g1_cat_row.addWidget(QLabel("🎯 ປະເພດເນື້ອຫາ (Category):"))
        self.cmb_g1_category = QComboBox()
        self.cmb_g1_category.setMinimumHeight(32)
        for cat_id, cat_info in CONTENT_PRESETS.items():
            self.cmb_g1_category.addItem(cat_info["name"], cat_id)
        cur_g1_cat = g1_data.get("content_type", "china_drama")
        idx1 = self.cmb_g1_category.findData(cur_g1_cat)
        if idx1 >= 0:
            self.cmb_g1_category.setCurrentIndex(idx1)
        g1_cat_row.addWidget(self.cmb_g1_category, stretch=2)
        g1_layout.addLayout(g1_cat_row)

        g1_f_row = QHBoxLayout()
        g1_f_row.addWidget(QLabel("📁 Folder ວິດີໂອ:"))
        self.txt_g1_folder = QLineEdit(g1_data.get("video_folder", self.config.get("video_folder", "Y:/Movies FB")))
        self.txt_g1_folder.setMinimumHeight(32)
        btn_g1_browse = QPushButton("📁 ເລືອກ Folder...")
        btn_g1_browse.setStyleSheet("background-color: #1d4ed8; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_g1_browse.clicked.connect(self.browse_g1_folder)
        g1_f_row.addWidget(self.txt_g1_folder, stretch=3)
        g1_f_row.addWidget(btn_g1_browse)
        g1_layout.addLayout(g1_f_row)

        g1_p1_row = QHBoxLayout()
        g1_p1_row.addWidget(QLabel("Page 1:"))
        self.txt_g1_p1_name = QLineEdit(g1_p1.get("page_name", ""))
        self.txt_g1_p1_id = QLineEdit(str(g1_p1.get("page_id", "")))
        self.txt_g1_p1_name.setPlaceholderText("ຊື່ເພຈ 1 (ເຊັ່ນ: ซี่รีย์จีน เต็มเรื่อง)")
        self.txt_g1_p1_id.setPlaceholderText("Page ID 1")
        self.txt_g1_p1_name.setMinimumHeight(32)
        self.txt_g1_p1_id.setMinimumHeight(32)
        g1_p1_row.addWidget(self.txt_g1_p1_name, stretch=2)
        g1_p1_row.addWidget(self.txt_g1_p1_id, stretch=1)
        g1_layout.addLayout(g1_p1_row)

        g1_p2_row = QHBoxLayout()
        g1_p2_row.addWidget(QLabel("Page 2:"))
        self.txt_g1_p2_name = QLineEdit(g1_p2.get("page_name", ""))
        self.txt_g1_p2_id = QLineEdit(str(g1_p2.get("page_id", "")))
        self.txt_g1_p2_name.setPlaceholderText("ຊື່ເພຈ 2")
        self.txt_g1_p2_id.setPlaceholderText("Page ID 2")
        self.txt_g1_p2_name.setMinimumHeight(32)
        self.txt_g1_p2_id.setMinimumHeight(32)
        g1_p2_row.addWidget(self.txt_g1_p2_name, stretch=2)
        g1_p2_row.addWidget(self.txt_g1_p2_id, stretch=1)
        g1_layout.addLayout(g1_p2_row)

        g1_p3_row = QHBoxLayout()
        g1_p3_row.addWidget(QLabel("Page 3:"))
        self.txt_g1_p3_name = QLineEdit(g1_p3.get("page_name", ""))
        self.txt_g1_p3_id = QLineEdit(str(g1_p3.get("page_id", "")))
        self.txt_g1_p3_name.setPlaceholderText("ຊື່ເພຈ 3")
        self.txt_g1_p3_id.setPlaceholderText("Page ID 3")
        self.txt_g1_p3_name.setMinimumHeight(32)
        self.txt_g1_p3_id.setMinimumHeight(32)
        g1_p3_row.addWidget(self.txt_g1_p3_name, stretch=2)
        g1_p3_row.addWidget(self.txt_g1_p3_id, stretch=1)
        g1_layout.addLayout(g1_p3_row)

        g1_prefix_row = QHBoxLayout()
        g1_prefix_row.addWidget(QLabel("🏷️ ຄຳກຳກັບໜ້າຊື່ເລື່ອງ (Prefix):"))
        self.txt_g1_prefix = QLineEdit(g1_data.get("title_prefix", "[เต็มเรื่อง] "))
        self.txt_g1_prefix.setPlaceholderText("[เต็มเรื่อง] ")
        self.txt_g1_prefix.setMinimumHeight(32)
        g1_prefix_row.addWidget(self.txt_g1_prefix)
        g1_layout.addLayout(g1_prefix_row)

        lbl_g1_hint = QLabel("💡 ລະບົບຈະໃສ່ຄຳວ່າ [เต็มเรื่อง] ຕໍ່ໜ້າຊື່ເລື່ອງອັດຕະໂນມັດສະເພາະ 3 ເພຈນີ້ ເພື່ອບອກຜູ້ຊົມວ່າເປັນໜັງຈົບເລື່ອງເຕັມ")
        lbl_g1_hint.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        g1_layout.addWidget(lbl_g1_hint)

        groups_layout.addWidget(g1_box)

        # --- Group 2 Box ---
        g2_box = QGroupBox("🟣 ກຸ່ມທີ 2: 1 Page (ເນື້ອຫາສະເພາະຕົວ / Dedicated Content)")
        g2_box.setStyleSheet("QGroupBox { font-weight: bold; color: #cba6f7; border: 1px solid #a855f7; border-radius: 6px; margin-top: 6px; padding: 12px; }")
        g2_layout = QVBoxLayout(g2_box)
        g2_layout.setSpacing(10)

        g2_cat_row = QHBoxLayout()
        g2_cat_row.addWidget(QLabel("🎯 ປະເພດເນື້ອຫາ (Category):"))
        self.cmb_g2_category = QComboBox()
        self.cmb_g2_category.setMinimumHeight(32)
        for cat_id, cat_info in CONTENT_PRESETS.items():
            self.cmb_g2_category.addItem(cat_info["name"], cat_id)
        cur_g2_cat = g2_data.get("content_type", "lao_girl_khaohom")
        idx2 = self.cmb_g2_category.findData(cur_g2_cat)
        if idx2 >= 0:
            self.cmb_g2_category.setCurrentIndex(idx2)
        g2_cat_row.addWidget(self.cmb_g2_category, stretch=2)
        g2_layout.addLayout(g2_cat_row)

        g2_f_row = QHBoxLayout()
        g2_f_row.addWidget(QLabel("📁 Folder ວິດີໂອ / ຮູບພາບ:"))
        self.txt_g2_folder = QLineEdit(g2_data.get("video_folder", "Y:/Movies FB Dedicated"))
        self.txt_g2_folder.setMinimumHeight(32)
        btn_g2_browse = QPushButton("📁 ເລືອກ Folder...")
        btn_g2_browse.setStyleSheet("background-color: #7e22ce; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_g2_browse.clicked.connect(self.browse_g2_folder)
        g2_f_row.addWidget(self.txt_g2_folder, stretch=3)
        g2_f_row.addWidget(btn_g2_browse)
        g2_layout.addLayout(g2_f_row)

        g2_p1_row = QHBoxLayout()
        g2_p1_row.addWidget(QLabel("Page 4:"))
        self.txt_g2_p1_name = QLineEdit(g2_p1.get("page_name", ""))
        self.txt_g2_p1_id = QLineEdit(str(g2_p1.get("page_id", "")))
        self.txt_g2_p1_name.setPlaceholderText("ຊື່ເພຈ 4 ສະເພາະຕົວ (ເຊັ່ນ: ນ້ອງເຂົ້າຫອມ ສາວຂີ້ດື້)")
        self.txt_g2_p1_id.setPlaceholderText("Page ID 4")
        self.txt_g2_p1_name.setMinimumHeight(32)
        self.txt_g2_p1_id.setMinimumHeight(32)
        g2_p1_row.addWidget(self.txt_g2_p1_name, stretch=2)
        g2_p1_row.addWidget(self.txt_g2_p1_id, stretch=1)
        g2_layout.addLayout(g2_p1_row)

        lbl_g2_hint = QLabel("💡 ໝວດ 'ນ້ອງເຂົ້າຫອມ ສາວຂີ້ດື້' ຈະສ້າງ Caption & Title ພາສາໄທສໄຕລ໌ສາວນັກຮຽນລາວໜ້າຮັກ 14-16 ປີ ແຈກຄວາມສົດໃສ (ຮອງຮັບທັງ Video Reels ແລະ ຮູບພາບ Photos + txt)")
        lbl_g2_hint.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        g2_layout.addWidget(lbl_g2_hint)

        groups_layout.addWidget(g2_box)

        btn_save_groups = QPushButton("💾 ບັນທຶກການຕັ້ງຄ່າທັງ 4 Pages & Folders")
        btn_save_groups.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 10px 18px; border-radius: 6px; font-size: 13px;")
        btn_save_groups.clicked.connect(self.save_multi_page_groups_settings)
        groups_layout.addWidget(btn_save_groups)

        layout.addWidget(groups_box)

        # -------------------------------------------------------------
        # CARD 2: Google Gemini AI & API Keys
        # -------------------------------------------------------------
        ai_group = QGroupBox("🤖 Google Gemini AI (Title & Caption Generator)")
        ai_layout = QVBoxLayout(ai_group)
        ai_layout.setSpacing(10)
        ai_layout.setContentsMargins(12, 16, 12, 16)

        # 1-Click Pull Button right at the top
        btn_pull_key = QPushButton("🔄 ດຶງ API Key ຈາກ 'G:/PG/API' (1-Click Auto Load)")
        btn_pull_key.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; font-size: 13px;")
        btn_pull_key.clicked.connect(self.pull_external_api_key)
        ai_layout.addWidget(btn_pull_key)

        self.chk_ai_enabled = QCheckBox("ເປີດໃຊ້ງານ Gemini AI ສ້າງ Title & Caption ອັດຕະໂນມັດ (ແຍກຕາມໝວດ)")
        ai_cfg = self.config.get("ai_caption", {})
        self.chk_ai_enabled.setChecked(ai_cfg.get("enabled", True))
        ai_layout.addWidget(self.chk_ai_enabled)

        api_row = QHBoxLayout()
        api_row.addWidget(QLabel("Gemini API Key(s):"))
        self.txt_ai_key = QLineEdit(ai_cfg.get("api_key", ""))
        self.txt_ai_key.setMinimumHeight(32)
        self.txt_ai_key.setEchoMode(QLineEdit.Password)
        api_row.addWidget(self.txt_ai_key, stretch=3)

        btn_toggle_key = QPushButton("👁️ ສະແດງ/ເຊື່ອງ Key")
        btn_toggle_key.setStyleSheet("background-color: #3b4252; color: #d8dee9; padding: 6px 12px; border-radius: 4px;")
        btn_toggle_key.clicked.connect(self.toggle_api_key_visibility)
        api_row.addWidget(btn_toggle_key)
        ai_layout.addLayout(api_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Gemini Model:"))
        self.txt_ai_model = QLineEdit(ai_cfg.get("model", "gemini-3.6-flash"))
        self.txt_ai_model.setMinimumHeight(32)
        model_row.addWidget(self.txt_ai_model)
        ai_layout.addLayout(model_row)

        ai_layout.addWidget(QLabel("AI Instructions (ຄຳສັ່ງບອກ AI):"))
        self.txt_ai_prompt = QTextEdit()
        self.txt_ai_prompt.setPlainText(ai_cfg.get("prompt_instructions", "Analyze the cover image of this China AI Movie and create a viral, suspenseful drama title & caption in Thai language."))
        self.txt_ai_prompt.setMaximumHeight(70)
        ai_layout.addWidget(self.txt_ai_prompt)

        layout.addWidget(ai_group)

        # -------------------------------------------------------------
        # CARD 3: Random Delay & Schedule Jitter
        # -------------------------------------------------------------
        time_group = QGroupBox("🎲 การสุ่มเวลาหน่วงและเวลาโพสต์ (Random Delay & Schedule Jitter)")
        time_layout = QVBoxLayout(time_group)
        time_layout.setSpacing(10)
        time_layout.setContentsMargins(12, 16, 12, 16)

        r_delay_row = QHBoxLayout()
        self.chk_random_delay = QCheckBox("เปิดใช้งานสุ่มเวลาพักระหว่างคลิป (Random Delay)")
        self.chk_random_delay.setChecked(self.config.get("randomize_delay", True))
        r_delay_row.addWidget(self.chk_random_delay)

        r_delay_row.addWidget(QLabel("ช่วงสุ่ม (นาที):"))
        self.spin_delay_min = QSpinBox()
        self.spin_delay_min.setRange(1, 120)
        self.spin_delay_min.setValue(int(self.config.get("delay_min_minutes", 15)))
        self.spin_delay_min.setMinimumHeight(30)
        r_delay_row.addWidget(self.spin_delay_min)

        r_delay_row.addWidget(QLabel("ถึง"))
        self.spin_delay_max = QSpinBox()
        self.spin_delay_max.setRange(2, 240)
        self.spin_delay_max.setValue(int(self.config.get("delay_max_minutes", 35)))
        self.spin_delay_max.setMinimumHeight(30)
        r_delay_row.addWidget(self.spin_delay_max)
        r_delay_row.addStretch()
        time_layout.addLayout(r_delay_row)

        r_sch_row = QHBoxLayout()
        self.chk_random_schedule = QCheckBox("สุ่มกระจายนาทีในตารางเวลา (Schedule Jitter ± นาที เพื่อไม่ให้ตรงกันทุกวัน)")
        self.chk_random_schedule.setChecked(self.config.get("randomize_schedule", True))
        r_sch_row.addWidget(self.chk_random_schedule)

        self.spin_jitter = QSpinBox()
        self.spin_jitter.setRange(0, 60)
        self.spin_jitter.setValue(int(self.config.get("schedule_jitter_minutes", 20)))
        self.spin_jitter.setMinimumHeight(30)
        r_sch_row.addWidget(self.spin_jitter)
        r_sch_row.addWidget(QLabel("นาที"))
        r_sch_row.addStretch()
        time_layout.addLayout(r_sch_row)

        layout.addWidget(time_group)

        # -------------------------------------------------------------
        # CARD 4: CTA Photo Posts & WhatsApp Notification
        # -------------------------------------------------------------
        cta_group = QGroupBox("📢 โพสต์รูปภาพชวนคนกดติดตามเพจ (Follower CTA Posts) & แจ้งเตือน")
        cta_layout = QVBoxLayout(cta_group)
        cta_layout.setSpacing(10)
        cta_layout.setContentsMargins(12, 16, 12, 16)

        self.chk_cta_enabled = QCheckBox("เปิดใช้งานสุ่มโพสต์รูปภาพชวนคนกดติดตามเพจ (ช่วยดันผู้ติดตาม & บรรลุเป้าหมายเพจ)")
        self.chk_cta_enabled.setChecked(self.config.get("cta_post_enabled", True))
        cta_layout.addWidget(self.chk_cta_enabled)

        c_row = QHBoxLayout()
        c_row.addWidget(QLabel("โพสต์รูปภาพชวนติดตามทุกๆ:"))
        self.spin_cta_interval = QSpinBox()
        self.spin_cta_interval.setRange(1, 50)
        self.spin_cta_interval.setValue(int(self.config.get("cta_post_interval_reels", 5)))
        self.spin_cta_interval.setMinimumHeight(30)
        c_row.addWidget(self.spin_cta_interval)
        c_row.addWidget(QLabel("คลิปวิดีโอ (แนะนำ: 5-7 คลิปต่อ 1 โพสต์รูปภาพ)"))
        c_row.addStretch()
        cta_layout.addLayout(c_row)

        self.chk_ai_image_gen = QCheckBox("🎨 ให้ AI สังเคราะห์รูปภาพโปสเตอร์ & เขียนแคปชั่นอัตโนมัติ (ไม่ซ้ำใคร 100%)")
        self.chk_ai_image_gen.setChecked(self.config.get("ai_image_gen", {}).get("enabled", True))
        self.chk_ai_image_gen.setStyleSheet("color: #f9e2af; font-weight: bold;")
        cta_layout.addWidget(self.chk_ai_image_gen)

        c_btn_row = QHBoxLayout()
        btn_post_cta_now = QPushButton("📸 โพสต์รูปภาพชวนติดตามตอนนี้ (Post CTA Now)")
        btn_post_cta_now.setStyleSheet("background-color: #7209b7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_post_cta_now.clicked.connect(self.post_cta_photo_action)
        c_btn_row.addWidget(btn_post_cta_now)

        btn_test_ai_gen = QPushButton("🎨 ทดลองให้ AI สังเคราะห์รูปภาพ (Test AI Gen)")
        btn_test_ai_gen.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_test_ai_gen.clicked.connect(self.test_ai_gen_action)
        c_btn_row.addWidget(btn_test_ai_gen)

        btn_open_cta_folder = QPushButton("📂 เปิดโฟลเดอร์รูปภาพ (cta_images)")
        btn_open_cta_folder.clicked.connect(self.open_cta_images_folder)
        c_btn_row.addWidget(btn_open_cta_folder)
        c_btn_row.addStretch()
        cta_layout.addLayout(c_btn_row)

        # WhatsApp sub-section
        wa_cfg = self.config.get("whatsapp_notify", {})
        self.chk_wa_enabled = QCheckBox("📱 เปิดใช้งานแจ้งเตือนผ่าน WhatsApp (CallMeBot ฟรี)")
        self.chk_wa_enabled.setChecked(wa_cfg.get("enabled", True))
        cta_layout.addWidget(self.chk_wa_enabled)

        wa_row1 = QHBoxLayout()
        wa_row1.addWidget(QLabel("เบอร์ WhatsApp:"))
        self.txt_wa_phone = QLineEdit(wa_cfg.get("phone", "+8562055452389"))
        self.txt_wa_phone.setMinimumHeight(30)
        wa_row1.addWidget(self.txt_wa_phone)

        wa_row1.addWidget(QLabel("CallMeBot API Key:"))
        self.txt_wa_key = QLineEdit(wa_cfg.get("apikey", ""))
        self.txt_wa_key.setPlaceholderText("ใส่ CallMeBot API Key (หากมี)")
        self.txt_wa_key.setMinimumHeight(30)
        wa_row1.addWidget(self.txt_wa_key)

        btn_test_wa = QPushButton("🔔 ทดสอบ WhatsApp")
        btn_test_wa.clicked.connect(self.test_send_notification)
        wa_row1.addWidget(btn_test_wa)
        cta_layout.addLayout(wa_row1)

        layout.addWidget(cta_group)

        # -------------------------------------------------------------
        # CARD 5: Browser & Storage Settings
        # -------------------------------------------------------------
        browser_group = QGroupBox("🌐 ລະບົບ Browser & ຈັດການໄຟລ໌")
        b_layout = QVBoxLayout(browser_group)
        b_layout.setSpacing(10)
        b_layout.setContentsMargins(12, 16, 12, 16)

        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("เบราว์เซอร์ที่ใช้ (Browser Engine):"))
        self.combo_browser = QComboBox()
        self.combo_browser.setMinimumHeight(32)
        self.combo_browser.addItem("🌐 Chromium (Browser ในตัว - แนะนำ ไม่ชนบอทอื่น)", "chromium")
        self.combo_browser.addItem("🌐 Microsoft Edge (msedge)", "msedge")
        self.combo_browser.addItem("🌐 Google Chrome (chrome)", "chrome")
        
        current_b = str(self.config.get("browser_type", "chromium")).lower()
        idx = self.combo_browser.findData(current_b)
        if idx >= 0:
            self.combo_browser.setCurrentIndex(idx)
        else:
            self.combo_browser.setCurrentIndex(0)
        b_row.addWidget(self.combo_browser)
        b_layout.addLayout(b_row)

        self.chk_move_completed = QCheckBox("ຍ້າຍໄຟລ໌ (ວິດີໂອ/ຮູບພາບ + txt) ທີ່ອັບໂຫຼດສຳເລັດແລ້ວໄປໂຟນເດີ 'completed'")
        self.chk_move_completed.setChecked(self.config.get("move_completed_videos", True))
        b_layout.addWidget(self.chk_move_completed)

        layout.addWidget(browser_group)

        # -------------------------------------------------------------
        # CARD 6: Cloud Relay Web Dashboard (Render.com) & Remote Mobile Access
        # -------------------------------------------------------------
        cloud_group = QGroupBox("☁️ ລະບົບ Cloud Web Dashboard (Render.com) ສຳລັບມືຖື 24/7")
        cloud_layout = QVBoxLayout(cloud_group)
        cloud_layout.setSpacing(10)
        cloud_layout.setContentsMargins(12, 16, 12, 16)

        lbl_cloud_desc = QLabel(
            "💡 <b>ເວັບຖາວອນສຳລັບຈັດການຜ່ານມືຖື 24/7:</b><br>"
            "ເອົາໂປຣເຈັກໄປ Deploy ຂຶ້ນ <b>Render.com</b> (ຟຣີ 100%) ແລ້ວນຳ URL ມາໃສ່ບ່ອນນີ້.<br>"
            "ທ່ານຈະສາມາດເປີດເບິ່ງ ແລະ ສັ່ງງານ Bot ຈາກມືຖື (iPhone/Android) ຜ່ານ 4G/5G ໄດ້ຕະຫຼອດເວລາ ບໍ່ມີຫຼຸດ."
        )
        lbl_cloud_desc.setTextFormat(Qt.RichText)
        lbl_cloud_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        cloud_layout.addWidget(lbl_cloud_desc)

        cloud_row = QHBoxLayout()
        cloud_row.addWidget(QLabel("Cloud Relay URL:"))
        self.txt_cloud_relay_url = QLineEdit(self.config.get("web_monitor", {}).get("cloud_relay_url", ""))
        self.txt_cloud_relay_url.setPlaceholderText("https://xxxxxx.onrender.com")
        self.txt_cloud_relay_url.setMinimumHeight(32)
        cloud_row.addWidget(self.txt_cloud_relay_url, stretch=3)

        btn_open_cloud = QPushButton("🌐 ເປີດ Web")
        btn_open_cloud.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_open_cloud.clicked.connect(self.open_cloud_dashboard_url)
        cloud_row.addWidget(btn_open_cloud)
        cloud_layout.addLayout(cloud_row)

        layout.addWidget(cloud_group)

        # -------------------------------------------------------------
        # Save All Settings Button
        # -------------------------------------------------------------
        btn_save_adv = QPushButton("💾 ບັນທຶກການຕັ້ງຄ່າທັງໝົດ (Save All Settings)")
        btn_save_adv.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 12px; font-size: 14px; border-radius: 6px;")
        btn_save_adv.clicked.connect(self.save_advanced_settings)
        layout.addWidget(btn_save_adv)

        layout.addStretch()
        scroll.setWidget(widget)
        return scroll

    def apply_styles(self):
        # ໃຊ້ Font ພາສາລາວແທ້ເພື່ອໃຫ້ສະຫຼະ ແລະ ວັນນະຍຸດຈັດຕຳແໜ່ງຢ່າງຖືກຕ້ອງ
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QWidget {
                color: #cdd6f4;
                font-family: 'Sarabun', 'Leelawadee UI', 'Tahoma', 'Noto Sans Thai', 'Phetsarath OT', 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid #45475a;
                background-color: #181825;
            }
            QTabBar::tab {
                background-color: #313244;
                color: #a6adc8;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #89b4fa;
                color: #11111b;
                font-weight: bold;
            }
            QGroupBox {
                border: 1px solid #45475a;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #89b4fa;
            }
            QLineEdit, QTextEdit, QSpinBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px;
                color: #cdd6f4;
            }
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #585b70;
            }
            QTableWidget {
                background-color: #181825;
                border: 1px solid #45475a;
                gridline-color: #313244;
            }
            QHeaderView::section {
                background-color: #313244;
                color: #cdd6f4;
                padding: 4px;
                border: 1px solid #45475a;
            }
        """)

    def insert_token(self, token: str):
        self.txt_template.insertPlainText(token)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์วิดีโอ", self.txt_folder.text())
        if folder:
            self.txt_folder.setText(folder)

    def on_folder_changed(self):
        self.config["video_folder"] = self.txt_folder.text()
        save_config(self.config)
        self.refresh_queue_stats()
        self.refresh_queue_table()

    def open_current_folder(self):
        folder = os.path.abspath(self.txt_folder.text())
        if os.path.exists(folder):
            os.startfile(folder)

    def browse_g1_folder(self):
        cur = self.txt_g1_folder.text() if hasattr(self, 'txt_g1_folder') else ""
        folder = QFileDialog.getExistingDirectory(self, "ເລືອກ Folder ວິດີໂອ Group 1 (3 Pages)", cur)
        if folder and hasattr(self, 'txt_g1_folder'):
            self.txt_g1_folder.setText(folder)

    def browse_g2_folder(self):
        cur = self.txt_g2_folder.text() if hasattr(self, 'txt_g2_folder') else ""
        folder = QFileDialog.getExistingDirectory(self, "ເລືອກ Folder ວິດີໂອ Group 2 (1 Page Dedicated)", cur)
        if folder and hasattr(self, 'txt_g2_folder'):
            self.txt_g2_folder.setText(folder)

    def switch_active_dashboard_group(self, group_idx: int):
        groups = self.config.get("page_groups", [])
        if group_idx < len(groups):
            grp = groups[group_idx]
            folder = grp.get("video_folder", "")
            if folder:
                self.txt_folder.setText(folder)
            pages = grp.get("pages", [])
            if pages and len(pages) > 0:
                p0 = pages[0]
                if hasattr(self, 'txt_dash_page_name'):
                    self.txt_dash_page_name.setText(p0.get("page_name", ""))
                if hasattr(self, 'txt_dash_page_id'):
                    self.txt_dash_page_id.setText(str(p0.get("page_id", "")))
            self.refresh_queue_stats()
            self.refresh_queue_table()

    def save_multi_page_groups_settings(self):
        g1_folder = self.txt_g1_folder.text().strip() if hasattr(self, 'txt_g1_folder') else ""
        g2_folder = self.txt_g2_folder.text().strip() if hasattr(self, 'txt_g2_folder') else ""

        g1_pages = []
        if hasattr(self, 'txt_g1_p1_name') and (self.txt_g1_p1_name.text().strip() or self.txt_g1_p1_id.text().strip()):
            g1_pages.append({"page_name": self.txt_g1_p1_name.text().strip(), "page_id": self.txt_g1_p1_id.text().strip()})
        if hasattr(self, 'txt_g1_p2_name') and (self.txt_g1_p2_name.text().strip() or self.txt_g1_p2_id.text().strip()):
            g1_pages.append({"page_name": self.txt_g1_p2_name.text().strip(), "page_id": self.txt_g1_p2_id.text().strip()})
        if hasattr(self, 'txt_g1_p3_name') and (self.txt_g1_p3_name.text().strip() or self.txt_g1_p3_id.text().strip()):
            g1_pages.append({"page_name": self.txt_g1_p3_name.text().strip(), "page_id": self.txt_g1_p3_id.text().strip()})

        g2_pages = []
        if hasattr(self, 'txt_g2_p1_name') and (self.txt_g2_p1_name.text().strip() or self.txt_g2_p1_id.text().strip()):
            g2_pages.append({"page_name": self.txt_g2_p1_name.text().strip(), "page_id": self.txt_g2_p1_id.text().strip()})

        g1_cat = self.cmb_g1_category.currentData() if hasattr(self, 'cmb_g1_category') else "china_drama"
        g2_cat = self.cmb_g2_category.currentData() if hasattr(self, 'cmb_g2_category') else "lao_girl_khaohom"

        g1_prefix = self.txt_g1_prefix.text().strip() if hasattr(self, 'txt_g1_prefix') else "[เต็มเรื่อง]"
        if g1_prefix and not g1_prefix.endswith(" "):
            g1_prefix += " "

        if "page_groups" not in self.config or len(self.config["page_groups"]) < 2:
            self.config["page_groups"] = [
                {"group_id": "group_shared_3pages", "group_name": "ກຸ່ມ 3 Pages (ເນື້ອຫາຮ່ວມກັນ)", "content_type": g1_cat, "video_folder": g1_folder, "pages": g1_pages, "title_prefix": g1_prefix},
                {"group_id": "group_dedicated_1page", "group_name": "ກຸ່ມ 1 Page (ນ້ອງເຂົ້າຫອມ ສາວຂີ້ດື້)", "content_type": g2_cat, "video_folder": g2_folder, "pages": g2_pages, "title_prefix": ""}
            ]
        else:
            self.config["page_groups"][0]["video_folder"] = g1_folder
            self.config["page_groups"][0]["pages"] = g1_pages
            self.config["page_groups"][0]["title_prefix"] = g1_prefix
            self.config["page_groups"][0]["content_type"] = g1_cat
            self.config["page_groups"][1]["video_folder"] = g2_folder
            self.config["page_groups"][1]["pages"] = g2_pages
            self.config["page_groups"][1]["content_type"] = g2_cat

        if g1_pages:
            self.config["target_pages"] = g1_pages
            self.config["page_name"] = g1_pages[0]["page_name"]
            self.config["page_id"] = g1_pages[0]["page_id"]
            if hasattr(self, 'txt_dash_page_name'):
                self.txt_dash_page_name.setText(g1_pages[0]["page_name"])
            if hasattr(self, 'txt_dash_page_id'):
                self.txt_dash_page_id.setText(g1_pages[0]["page_id"])
        if g1_folder:
            self.config["video_folder"] = g1_folder
            self.txt_folder.setText(g1_folder)

        save_config(self.config)
        self.refresh_queue_stats()
        self.refresh_queue_table()
        QMessageBox.information(
            self,
            "ບັນທຶກສຳເລັດ",
            f"✅ ບັນທຶກການຕັ້ງຄ່າກຸ່ມ Facebook Pages ສຳເລັດ:\n\n"
            f"• ກຸ່ມ 1 (3 Pages): {len(g1_pages)} Pages | Folder: {g1_folder}\n"
            f"• ກຸ່ມ 2 (1 Page): {len(g2_pages)} Page | Folder: {g2_folder}\n\n"
            f"ລະບົບຈະແຍກ Folder ແລະ ກວດສອບຊື່ເພຈກ່ອນອັບໂຫຼດທຸກຄັ້ງ ປ້ອງກັນລົງຜິດເພຈ 100%!"
        )
        self.update_dashboard_pages_display()

    def _get_folder_signature(self) -> tuple:
        folder = self.config.get("video_folder", "./videos")
        if not os.path.exists(folder):
            return (0.0, 0)
        try:
            mtime = os.path.getmtime(folder)
            files_count = len(os.listdir(folder))
            return (mtime, files_count)
        except Exception:
            return (0.0, 0)

    def on_tab_changed(self, index: int):
        if index == 0:
            self.update_dashboard_pages_display()
        elif index == 1:
            self.ensure_browser_initialized()
        elif index == 3:
            self.refresh_queue_stats()
            self.refresh_queue_table()

    def update_dashboard_pages_display(self):
        groups = self.config.get("page_groups", [])
        g1 = groups[0] if len(groups) > 0 else {}
        g2 = groups[1] if len(groups) > 1 else {}

        g1_pages = g1.get("pages", [])
        g2_pages = g2.get("pages", [])

        # Update verify choices combo
        if hasattr(self, 'cmb_dash_verify_page'):
            self.cmb_dash_verify_page.clear()

        # Update G1 P1
        p1 = g1_pages[0] if len(g1_pages) > 0 else {}
        p1_name = p1.get("page_name", self.config.get("page_name", ""))
        p1_id = str(p1.get("page_id", self.config.get("page_id", "")))
        p1_badge = "<span style='color: #a6e3a1;'>[✓ ພ້ອມ]</span>" if p1_id else "<span style='color: #f38ba8;'>[⚠️ ຍັງບໍ່ມີ Page ID]</span>"
        if hasattr(self, 'lbl_dash_g1_p1'):
            self.lbl_dash_g1_p1.setText(f"1️⃣ <b>Page 1:</b> {p1_name or 'ຍັງບໍ່ມີຊື່'} (ID: {p1_id or 'ຍັງບໍ່ໃສ່'}) {p1_badge}")
        if hasattr(self, 'cmb_dash_verify_page') and p1_name:
            self.cmb_dash_verify_page.addItem(f"G1 - Page 1: {p1_name}", {"page_name": p1_name, "page_id": p1_id})

        # Update G1 P2
        p2 = g1_pages[1] if len(g1_pages) > 1 else {}
        p2_name = p2.get("page_name", "")
        p2_id = str(p2.get("page_id", ""))
        p2_badge = "<span style='color: #a6e3a1;'>[✓ ພ້ອມ]</span>" if p2_id else "<span style='color: #f38ba8;'>[⚠️ ຍັງບໍ່ມີ Page ID]</span>"
        if hasattr(self, 'lbl_dash_g1_p2'):
            self.lbl_dash_g1_p2.setText(f"2️⃣ <b>Page 2:</b> {p2_name or 'ຍັງບໍ່ມີຊື່'} (ID: {p2_id or 'ຍັງບໍ່ໃສ່'}) {p2_badge}")
        if hasattr(self, 'cmb_dash_verify_page') and p2_name:
            self.cmb_dash_verify_page.addItem(f"G1 - Page 2: {p2_name}", {"page_name": p2_name, "page_id": p2_id})

        # Update G1 P3
        p3 = g1_pages[2] if len(g1_pages) > 2 else {}
        p3_name = p3.get("page_name", "")
        p3_id = str(p3.get("page_id", ""))
        p3_badge = "<span style='color: #a6e3a1;'>[✓ ພ້ອມ]</span>" if p3_id else "<span style='color: #f38ba8;'>[⚠️ ຍັງບໍ່ມີ Page ID]</span>"
        if hasattr(self, 'lbl_dash_g1_p3'):
            self.lbl_dash_g1_p3.setText(f"3️⃣ <b>Page 3:</b> {p3_name or 'ຍັງບໍ່ມີຊື່'} (ID: {p3_id or 'ຍັງບໍ່ໃສ່'}) {p3_badge}")
        if hasattr(self, 'cmb_dash_verify_page') and p3_name:
            self.cmb_dash_verify_page.addItem(f"G1 - Page 3: {p3_name}", {"page_name": p3_name, "page_id": p3_id})

        # Update G2 P1
        p4 = g2_pages[0] if len(g2_pages) > 0 else {}
        p4_name = p4.get("page_name", "")
        p4_id = str(p4.get("page_id", ""))
        p4_badge = "<span style='color: #a6e3a1;'>[✓ ພ້ອມ]</span>" if p4_id else "<span style='color: #f38ba8;'>[⚠️ ຍັງບໍ່ມີ Page ID]</span>"
        if hasattr(self, 'lbl_dash_g2_p1'):
            self.lbl_dash_g2_p1.setText(f"4️⃣ <b>Page 4:</b> {p4_name or 'ຍັງບໍ່ມີຊື່'} (ID: {p4_id or 'ຍັງບໍ່ໃສ່'}) {p4_badge}")
        if hasattr(self, 'cmb_dash_verify_page') and p4_name:
            self.cmb_dash_verify_page.addItem(f"G2 - Page 4: {p4_name}", {"page_name": p4_name, "page_id": p4_id})

        if hasattr(self, 'lbl_dash_g1_fld'):
            self.lbl_dash_g1_fld.setText(f"📁 Folder: {g1.get('video_folder', 'Y:/Movies FB')}")
        if hasattr(self, 'lbl_dash_g2_fld'):
            self.lbl_dash_g2_fld.setText(f"📁 Folder: {g2.get('video_folder', 'Y:/Movies FB Dedicated')}")

    def verify_selected_dashboard_page(self):
        sel_data = self.cmb_dash_verify_page.currentData() if hasattr(self, 'cmb_dash_verify_page') else None
        if not sel_data:
            p_name = self.config.get("page_name", "")
            p_id = str(self.config.get("page_id", ""))
        else:
            p_name = sel_data.get("page_name", "")
            p_id = sel_data.get("page_id", "")
        self.verify_active_page_action(custom_target={"page_name": p_name, "page_id": p_id})

    def toggle_api_key_visibility(self):
        if hasattr(self, 'txt_ai_key'):
            if self.txt_ai_key.echoMode() == QLineEdit.Password:
                self.txt_ai_key.setEchoMode(QLineEdit.Normal)
            else:
                self.txt_ai_key.setEchoMode(QLineEdit.Password)

    def auto_refresh_tick(self):
        # Update public tunnel URL if ready
        if hasattr(self, 'web_state') and self.web_state and self.web_state.public_url and hasattr(self, 'lbl_public_link'):
            p_url = self.web_state.public_url
            if getattr(self, '_last_rendered_pub_url', '') != p_url:
                self._last_rendered_pub_url = p_url
                self.lbl_public_link.setText(f"🌍 <b>ເບິ່ງຈາກທາງນອກ (4G/5G):</b> <a href='{p_url}' style='color: #a6e3a1; font-weight: bold;'>{p_url}</a>")

        # Fast signature check to avoid blocking the main UI thread with file reads / hashing!
        cur_sig = self._get_folder_signature()
        last_sig = getattr(self, '_last_folder_sig', None)
        if last_sig == cur_sig:
            return  # Zero disk I/O, zero CPU lag, completely silky smooth!

        self._last_folder_sig = cur_sig
        self.refresh_queue_stats()
        # Only refresh the heavy table if the user is actively viewing the Queue tab (tab index 3)
        if hasattr(self, 'tabs') and self.tabs.currentIndex() == 3:
            self.refresh_queue_table()

    def manual_refresh_queue(self):
        self.refresh_queue_stats()
        self.refresh_queue_table()
        self.log_message("🔄 อัปเดตรายการคิววิดีโอเรียบร้อยแล้ว.")

    def refresh_queue_stats(self):
        qm = QueueManager(self.config)
        stats = qm.get_stats()
        self.lbl_stat_total.setText(f"วิดีโอทั้งหมด: {stats['total_in_folder']}")
        self.lbl_stat_pending.setText(f"รออัปโหลด: {stats['pending_in_folder']}")
        self.lbl_stat_duplicates.setText(f"ไฟล์ซ้ำ (ข้าม): {stats.get('duplicates_in_folder', 0)}")
        self.lbl_stat_uploaded.setText(f"อัปโหลดสำเร็จแล้ว: {stats['total_uploaded']}")

    def refresh_queue_table(self):
        qm = QueueManager(self.config)
        all_videos = qm.scan_videos()
        files_map = qm.history.get("files", {})

        active_filenames = set()
        items_to_show = []

        for v_path in all_videos:
            fname = os.path.basename(v_path)
            active_filenames.add(fname)
            items_to_show.append((fname, v_path, True))

        # Add items from history that aren't currently in video_folder (e.g. moved to completed)
        completed_dir = os.path.abspath(self.config.get("completed_folder", "./completed"))
        for fname, rec in files_map.items():
            if fname not in active_filenames:
                c_path = os.path.join(completed_dir, fname)
                if not os.path.exists(c_path):
                    c_path = rec.get("file_path", c_path)
                items_to_show.append((fname, c_path, False))

        self.table_queue.setRowCount(0)
        for row_idx, (fname, v_path, is_in_source) in enumerate(items_to_show):
            self.table_queue.insertRow(row_idx)
            rec = files_map.get(fname, {})
            title = rec.get("title", "-")

            is_dup, dup_reason = (False, "")
            if is_in_source:
                is_dup, dup_reason = qm.is_already_uploaded(v_path)

            uploaded_at = rec.get("uploaded_at", "-")
            if uploaded_at != "-":
                try:
                    uploaded_at = datetime.fromisoformat(uploaded_at).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            self.table_queue.setItem(row_idx, 0, QTableWidgetItem(str(row_idx + 1)))
            self.table_queue.setItem(row_idx, 1, QTableWidgetItem(fname))
            self.table_queue.setItem(row_idx, 2, QTableWidgetItem(title))

            if not is_in_source and rec.get("status") == "success":
                status_item = QTableWidgetItem("📁 สำเร็จ (Completed)")
                status_item.setForeground(QColor("#a6e3a1"))
            elif rec.get("status") == "success":
                status_item = QTableWidgetItem("✅ อัปโหลดแล้ว (Uploaded)")
                status_item.setForeground(QColor("#a6e3a1"))
            elif is_dup:
                status_item = QTableWidgetItem(f"⚠️ ซ้ำแล้ว (Duplicate: {dup_reason})")
                status_item.setForeground(QColor("#fab387"))
            elif rec.get("status") == "failed":
                status_item = QTableWidgetItem("❌ ไม่สำเร็จ (Failed)")
                status_item.setForeground(QColor("#f38ba8"))
            else:
                status_item = QTableWidgetItem("⏳ รอ (Pending) พร้อมอัปโหลด")
                status_item.setForeground(QColor("#89b4fa"))

            self.table_queue.setItem(row_idx, 3, status_item)
            self.table_queue.setItem(row_idx, 4, QTableWidgetItem(uploaded_at))
            self.table_queue.setItem(row_idx, 5, QTableWidgetItem(v_path))

    def restore_all_completed_action(self):
        res = QMessageBox.question(
            self,
            "ยืนยันการกู้คืนวิดีโอ",
            "คุณต้องการกู้คืนไฟล์วิดีโอทั้งหมดจากโฟลเดอร์ 'completed' กลับมายังโฟลเดอร์วิดีโอหลัก\nและรีเซ็ตสถานะเป็น 'รออัปโหลด (pending)' เพื่อให้อัปโหลดใหม่จริงใช่หรือไม่?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            qm = QueueManager(self.config)
            restored = qm.restore_completed_videos()
            self.refresh_queue_stats()
            self.refresh_queue_table()
            count = len(restored) if isinstance(restored, (list, tuple, set)) else int(restored)
            self.log_message(f"🔄 กู้คืนวิดีโอสำเร็จ {count} ไฟล์ กลับเข้าสู่คิวพร้อมอัปโหลดแล้ว!")
            QMessageBox.information(
                self,
                "กู้คืนสำเร็จ",
                f"กู้คืนวิดีโอจำนวน {count} ไฟล์ กลับมายังคิวอัปโหลดเรียบร้อยแล้ว!\nระบบได้ล้าง Hash เพื่อป้องกันการตรวจจับซ้ำแล้ว"
            )

    def edit_selected_history_item(self):
        row = self.table_queue.currentRow()
        if row < 0:
            QMessageBox.information(self, "แจ้งเตือน", "กรุณาคลิกเลือกแถววิดีโอที่ต้องการแก้ไขก่อน")
            return

        fname_item = self.table_queue.item(row, 1)
        if not fname_item:
            return
        fname = fname_item.text().strip()

        qm = QueueManager(self.config)
        rec = qm.history.get("files", {}).get(fname, {})
        current_title = rec.get("title", "")
        current_caption = rec.get("caption", "")
        current_status = rec.get("status", "pending")

        dlg = EditHistoryDialog(self, filename=fname, current_title=current_title, current_caption=current_caption, current_status=current_status)
        if dlg.exec():
            data = dlg.get_data()
            qm.update_video_history(
                filename=fname,
                new_title=data["title"],
                new_caption=data["caption"],
                new_status=data["status"],
                requeue=data["requeue"]
            )
            self.refresh_queue_stats()
            self.refresh_queue_table()
            self.log_message(f"✏️ บันทึกการแก้ไขวิดีโอ: {fname} (Title: {data['title']})")

    def on_table_row_double_clicked(self, index):
        self.edit_selected_history_item()

    def clear_history(self):
        res = QMessageBox.question(self, "ยืนยัน", "คุณต้องการล้างประวัติการอัปโหลดทั้งหมดจริงหรือไม่?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            hist_file = os.path.abspath(self.config.get("history_file", "./history.json"))
            if os.path.exists(hist_file):
                try:
                    os.remove(hist_file)
                except Exception:
                    pass
            self.refresh_queue_stats()
            self.refresh_queue_table()
            self.log_message("🗑️ ล้างประวัติการอัปโหลดเรียบร้อยแล้ว.")

    def open_completed_folder(self):
        completed_dir = os.path.abspath(self.config.get("completed_folder", "./completed"))
        os.makedirs(completed_dir, exist_ok=True)
        try:
            os.startfile(completed_dir)
        except Exception as e:
            QMessageBox.warning(self, "ข้อผิดพลาด", f"ไม่สามารถเปิดโฟลเดอร์ได้: {e}")

    def update_preview(self):
        tags_raw = self.txt_hashtags.toPlainText().split()
        pool = [t for t in tags_raw if t.strip()]
        cfg_copy = dict(self.config)
        cfg_copy["caption_template"] = self.txt_template.toPlainText()
        cfg_copy["hashtag_pool"] = pool
        cfg_copy["tags_count"] = self.spin_tags_count.value()
        cfg_copy["title_mode"] = "auto_ai_drama" if (hasattr(self, 'rb_title_auto') and self.rb_title_auto.isChecked()) else self.config.get("title_mode", "auto_ai_drama")
        cfg_copy["add_episode_number"] = self.chk_add_episode_number.isChecked() if hasattr(self, 'chk_add_episode_number') else self.config.get("add_episode_number", False)

        generator = CaptionGenerator(cfg_copy)
        sample1 = generator.build_caption("sample_movie_01.mp4", index=1)
        sample2 = generator.build_caption("sample_movie_02.mp4", index=2)

        mode_name = "🌟 โหมด AI สร้างชื่อดราม่าให้อัตโนมัติ (ไม่สนชื่อไฟล์เดิม)" if cfg_copy["title_mode"] == "auto_ai_drama" else "📁 โหมดใช้ชื่อจากไฟล์วิดีโอ"
        preview_text = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 สถานะโหมด: {mode_name}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎬 [ตัวอย่างคลิปที่ 1]\n"
            f"📌 Title: {sample1['title']}\n"
            f"📝 Caption:\n{sample1['caption']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎬 [ตัวอย่างคลิปที่ 2]\n"
            f"📌 Title: {sample2['title']}\n"
            f"📝 Caption:\n{sample2['caption']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.txt_preview.setPlainText(preview_text)

    def test_video_analysis(self):
        video_path, _ = QFileDialog.getOpenFileName(
            self, "เลือกไฟล์วิดีโอเพื่อทดสอบวิเคราะห์", "", "Video Files (*.mp4 *.mov *.mkv *.avi *.webm)"
        )
        if not video_path:
            return

        cfg_copy = dict(self.config)
        cfg_copy["caption_template"] = self.txt_template.toPlainText()
        tags_raw = self.txt_hashtags.toPlainText().split()
        cfg_copy["hashtag_pool"] = [t for t in tags_raw if t.strip()]
        cfg_copy["tags_count"] = self.spin_tags_count.value()
        cfg_copy["title_mode"] = "auto_ai_drama" if (hasattr(self, 'rb_title_auto') and self.rb_title_auto.isChecked()) else self.config.get("title_mode", "auto_ai_drama")
        cfg_copy["add_episode_number"] = self.chk_add_episode_number.isChecked() if hasattr(self, 'chk_add_episode_number') else self.config.get("add_episode_number", False)

        generator = CaptionGenerator(cfg_copy)
        res = generator.build_caption(video_path, index=1)

        source_desc = {
            "filename": "ดึงมาจากชื่อไฟล์ (Meaningful Filename)",
            "ai_cover": "วิเคราะห์จากรูปหน้าปกด้วย Gemini AI Vision 🤖",
            "catchy_drama_engine": "สร้างชื่อเรื่อง China AI Drama สุดดึงดูดอัตโนมัติ 🎬"
        }.get(res.get("source"), "อัตโนมัติ")

        msg = (
            f"📁 ชื่อไฟล์เดิม: {os.path.basename(video_path)}\n"
            f"🔍 วิธีการตั้งชื่อ: {source_desc}\n\n"
            f"📌 Title ที่ตั้งให้อัตโนมัติ:\n{res['title']}\n\n"
            f"📝 Caption ที่สร้างให้:\n{res['caption']}"
        )
        QMessageBox.information(self, "ผลการทดสอบวิเคราะห์วิดีโอ", msg)

    def save_caption_settings(self):
        tags_raw = self.txt_hashtags.toPlainText().split()
        pool = [t for t in tags_raw if t.strip()]

        self.config["caption_template"] = self.txt_template.toPlainText()
        self.config["hashtag_pool"] = pool
        self.config["tags_count"] = self.spin_tags_count.value()
        self.config["title_mode"] = "auto_ai_drama" if self.rb_title_auto.isChecked() else "filename_clean"
        if hasattr(self, 'chk_add_episode_number'):
            self.config["add_episode_number"] = self.chk_add_episode_number.isChecked()
        if "china_ai_movie" not in self.config:
            self.config["china_ai_movie"] = {}
        self.config["china_ai_movie"]["enabled"] = self.rb_title_auto.isChecked()
        save_config(self.config)
        QMessageBox.information(self, "สำเร็จ", "บันทึกการตั้งค่า Caption & Tags เรียบร้อย!")

    def pull_external_api_key(self):
        from core.utils import load_external_gemini_key
        keys, model = load_external_gemini_key("G:/PG/API")
        if not keys:
            keys, model = load_external_gemini_key("G:/PG/Auto flow ຂຽນຂ່າວ")
        if keys:
            self.txt_ai_key.setText(keys)
            if model:
                self.txt_ai_model.setText(model)
            self.chk_ai_enabled.setChecked(True)
            self.save_advanced_settings()
            self.lbl_gemini_status.setText(f"🤖 Gemini AI Status: 🟢 ດຶງມາຈາກ G:/PG/API ({model})")
            QMessageBox.information(
                self, "ດຶງ API Key ສຳເລັດ",
                f"✅ ດຶງ API Key ຈາກ 'G:/PG/API' ສຳເລັດແລ້ວ!\n\n• Model: {model}\n• ຈຳນວນ Key ທີ່ພົບ: {len(keys.split(','))} keys\n\nລະບົບໄດ້ບັນທຶກ ແລະ ເປີດໃຊ້ງານ Gemini AI ໃຫ້ທັນທີ!"
            )
        else:
            QMessageBox.warning(self, "ບໍ່ພົບ API Key", "ບໍ່ພົບໄຟລ໌ .env ຫຼື GEMINI_API_KEY ໃນ 'G:/PG/API' ຫຼື 'G:/PG/Auto flow ຂຽນຂ່າວ'")

    def save_advanced_settings(self):
        self.config["browser_type"] = self.combo_browser.currentData()
        self.config["move_completed_videos"] = self.chk_move_completed.isChecked()

        # Parse target pages
        parsed_pages = []
        if hasattr(self, 'txt_target_pages'):
            for line in self.txt_target_pages.toPlainText().strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    parts = line.split("|", 1)
                    p_name = parts[0].strip()
                    p_id = parts[1].strip()
                else:
                    p_name = line
                    p_id = ""
                parsed_pages.append({"page_name": p_name, "page_id": p_id})

        if parsed_pages:
            self.config["target_pages"] = parsed_pages
            if "page_groups" in self.config and len(self.config["page_groups"]) > 0:
                self.config["page_groups"][0]["pages"] = parsed_pages
            self.config["page_name"] = parsed_pages[0]["page_name"]
            self.config["page_id"] = parsed_pages[0]["page_id"]
            if hasattr(self, 'txt_page_name'):
                self.txt_page_name.setText(parsed_pages[0]["page_name"])
            if hasattr(self, 'txt_page_id'):
                self.txt_page_id.setText(parsed_pages[0]["page_id"])
            if hasattr(self, 'txt_dash_page_name'):
                self.txt_dash_page_name.setText(parsed_pages[0]["page_name"])
            if hasattr(self, 'txt_dash_page_id'):
                self.txt_dash_page_id.setText(parsed_pages[0]["page_id"])
        else:
            if hasattr(self, 'txt_page_name'):
                self.config["page_name"] = self.txt_page_name.text().strip()
            if hasattr(self, 'txt_page_id'):
                self.config["page_id"] = self.txt_page_id.text().strip()
            if self.config.get("page_name") or self.config.get("page_id"):
                self.config["target_pages"] = [{"page_name": self.config.get("page_name", ""), "page_id": self.config.get("page_id", "")}]

        if hasattr(self, 'chk_random_delay'):
            self.config["randomize_delay"] = self.chk_random_delay.isChecked()
            self.config["delay_min_minutes"] = self.spin_delay_min.value()
            self.config["delay_max_minutes"] = self.spin_delay_max.value()

        if hasattr(self, 'chk_random_schedule'):
            self.config["randomize_schedule"] = self.chk_random_schedule.isChecked()
            self.config["schedule_jitter_minutes"] = self.spin_jitter.value()

        if hasattr(self, 'chk_cta_enabled'):
            self.config["cta_post_enabled"] = self.chk_cta_enabled.isChecked()
        if hasattr(self, 'spin_cta_interval'):
            self.config["cta_post_interval_reels"] = self.spin_cta_interval.value()

        if hasattr(self, 'chk_ai_image_gen'):
            if "ai_image_gen" not in self.config:
                self.config["ai_image_gen"] = {}
            self.config["ai_image_gen"]["enabled"] = self.chk_ai_image_gen.isChecked()

        if hasattr(self, 'chk_wa_enabled'):
            if "whatsapp_notify" not in self.config:
                self.config["whatsapp_notify"] = {}
            self.config["whatsapp_notify"]["enabled"] = self.chk_wa_enabled.isChecked()
            self.config["whatsapp_notify"]["phone"] = self.txt_wa_phone.text().strip()
            self.config["whatsapp_notify"]["apikey"] = self.txt_wa_key.text().strip()

        b_type = str(self.config.get("browser_type", "chromium")).lower()
        b_name = "Chromium (Browser ในตัว)" if b_type == "chromium" else ("Microsoft Edge" if b_type in ["msedge", "edge"] else "Google Chrome")
        self.btn_login.setText(f"🌐 เปิด {b_name} เพื่อ Login Facebook (ครั้งเดียว)")

        if hasattr(self, 'txt_ai_key'):
            if "ai_caption" not in self.config:
                self.config["ai_caption"] = {}
            self.config["ai_caption"]["enabled"] = self.chk_ai_enabled.isChecked() if hasattr(self, 'chk_ai_enabled') else True
            self.config["ai_caption"]["api_key"] = self.txt_ai_key.text().strip()
            if hasattr(self, 'txt_ai_model'):
                self.config["ai_caption"]["model"] = self.txt_ai_model.text().strip()
            if hasattr(self, 'txt_ai_prompt'):
                self.config["ai_caption"]["prompt_instructions"] = self.txt_ai_prompt.toPlainText().strip()

        if hasattr(self, 'txt_cloud_relay_url'):
            if "web_monitor" not in self.config:
                self.config["web_monitor"] = {}
            cloud_u = self.txt_cloud_relay_url.text().strip()
            self.config["web_monitor"]["cloud_relay_url"] = cloud_u
            if hasattr(self, 'web_state') and self.web_state:
                self.web_state.update(cloud_relay_url=cloud_u)
            if cloud_u and cloud_u.startswith("http"):
                import core.web_monitor as wm
                if wm.CLOUD_SYNC_MGR:
                    wm.CLOUD_SYNC_MGR.stop()
                wm.CLOUD_SYNC_MGR = wm.CloudSyncManager(cloud_url=cloud_u, action_callback=self.handle_remote_action)
                wm.CLOUD_SYNC_MGR.start()

        save_config(self.config)
        # Hot-reload into active background worker if running
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            try:
                self.worker.config.update(self.config)
                if hasattr(self.worker, 'engine') and self.worker.engine:
                    self.worker.engine.config.update(self.config)
            except Exception:
                pass
        self.update_account_display()
        self.update_dashboard_pages_display()
        QMessageBox.information(
            self, "ສຳເລັດ", 
            "✅ ບັນທຶກການຕັ້ງຄ່າທັງໝົດຮຽບຮ້ອຍແລ້ວ!\n\n💡 ລະບົບອັບເດດຄ່າໃໝ່ທັນທີ (Hot-Reload) ໂດຍບໍ່ຈຳເປັນຕ້ອງ Restart ໂປຣແກຣມ."
        )

    def open_cloud_dashboard_url(self):
        url = self.txt_cloud_relay_url.text().strip() if hasattr(self, 'txt_cloud_relay_url') else ""
        if not url:
            url = self.config.get("web_monitor", {}).get("cloud_relay_url", "").strip()
        if not url:
            QMessageBox.information(self, "ແຈ້ງເຕືອນ", "ກະລຸນາໃສ່ Cloud Relay URL (ທີ່ໄດ້ຈາກ Render.com) ກ່ອນ.")
            return
        import webbrowser
        webbrowser.open(url)

    def log_message(self, text: str):
        self.txt_log.append(text)
        if hasattr(self, 'web_state') and self.web_state:
            self.web_state.add_log(text)

    def handle_manual_login(self):
        self.btn_login.setEnabled(False)
        self.login_worker = LoginThread(self.config)
        self.login_worker.log_signal.connect(self.log_message)
        self.login_worker.finished_signal.connect(self.on_login_finished)
        self.login_worker.start()

    def on_login_finished(self, success: bool):
        self.btn_login.setEnabled(True)
        if success:
            self.load_cached_cookies()
            self.update_account_display()
            QMessageBox.information(self, "Login สำเร็จ", "เชื่อมต่อ Facebook / Meta Business Suite สำเร็จแล้ว!")
        else:
            self.update_account_display()

    def start_upload(self):
        self.config["video_folder"] = self.txt_folder.text()
        self.config["post_mode"] = "schedule" if self.rb_schedule.isChecked() else "now"
        self.config["delay_between_posts_minutes"] = self.spin_delay.value()
        self.config["headless"] = self.chk_headless.isChecked()
        self.config["mark_as_ai_content"] = self.chk_mark_ai.isChecked()
        self.config["auto_watch_new_files"] = self.chk_auto_watch.isChecked()
        save_config(self.config)

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

        self.worker = WorkerThread(self.config)
        self.worker.log_signal.connect(self.log_message)
        self.worker.status_signal.connect(self.on_worker_status)
        self.worker.progress_signal.connect(self.on_upload_progress)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.start()

    def pause_upload(self):
        if self.worker:
            self.worker.pause()

    def stop_upload(self):
        if self.worker:
            self.worker.stop()
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

    def on_worker_status(self, stats: dict):
        self.refresh_queue_stats()
        self.refresh_queue_table()
        if hasattr(self, 'web_state') and self.web_state:
            self.web_state.update(
                queue_stats=stats,
                status="uploading" if (hasattr(self, 'worker') and self.worker and self.worker.isRunning()) else "idle"
            )

    def on_worker_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.refresh_queue_stats()
        self.refresh_queue_table()
        if hasattr(self, 'upload_progress_bar'):
            self.upload_progress_bar.setValue(100 if self.upload_progress_bar.value() > 0 else 0)
        if hasattr(self, 'upload_progress_lbl'):
            self.upload_progress_lbl.setText("⏳ ສະຖານະ: ສິ້ນສຸດການເຮັດວຽກ (Finished / Idle)")
        if hasattr(self, 'web_state') and self.web_state:
            self.web_state.update(status="idle", progress_pct=100, progress_text="ສິ້ນສຸດການເຮັດວຽກ (Finished / Idle)")
        self.log_message("🏁 สิ้นสุดกระบวนการอัปโหลด.")

    def on_upload_progress(self, percent: int, text: str):
        if hasattr(self, 'upload_progress_bar'):
            self.upload_progress_bar.setValue(max(0, min(100, percent)))
        if hasattr(self, 'upload_progress_lbl'):
            self.upload_progress_lbl.setText(f"🚀 {percent}% - {text}")
        if hasattr(self, 'web_state') and self.web_state:
            self.web_state.update(progress_pct=percent, progress_text=text, status="uploading")

    def verify_active_page_action(self):
        target_name = self.txt_dash_page_name.text().strip() if hasattr(self, 'txt_dash_page_name') else self.config.get("page_name", "")
        target_id = self.txt_dash_page_id.text().strip() if hasattr(self, 'txt_dash_page_id') else str(self.config.get("page_id", ""))

        self.lbl_verify_result.setText("⏳ ກຳລັງກວດສອບ Page ກັບ Meta Business Suite...")
        self.lbl_verify_result.setStyleSheet("color: #fab387; font-size: 11px; font-weight: bold;")
        self.btn_verify_page.setEnabled(False)

        check_cfg = dict(self.config)
        check_cfg["page_name"] = target_name
        check_cfg["page_id"] = target_id

        self.check_thread = CheckPageThread(check_cfg)
        self.check_thread.finished_signal.connect(self.on_verify_page_finished)
        self.check_thread.start()

    def on_verify_page_finished(self, res: dict):
        self.btn_verify_page.setEnabled(True)
        active_name = res.get("active_page_name", "")
        active_id = res.get("active_page_id", "")
        c_user = res.get("c_user", "")
        is_matched = res.get("is_matched", False)
        error = res.get("error", "")

        if error:
            self.lbl_verify_result.setText(f"❌ ຜິດພາດ: {error}")
            self.lbl_verify_result.setStyleSheet("color: #f38ba8; font-size: 11px; font-weight: bold;")
            QMessageBox.warning(self, "ກວດສອບ Page ບໍ່ສຳເລັດ", f"ບໍ່ສາມາດກວດສອບ Page ໄດ້:\n{error}")
            return

        if is_matched:
            display_name = active_name or self.config.get("page_name", "")
            self.lbl_verify_result.setText(f"✅ ຖືກຕ້ອງ 100%! Page: [{display_name}] (ID: {active_id or 'N/A'}) - ປອດໄພ ບໍ່ມີທາງລົງຜິດເພຈ")
            self.lbl_verify_result.setStyleSheet("color: #a6e3a1; font-size: 11px; font-weight: bold;")
            QMessageBox.information(
                self,
                "ກວດສອບ Page ສຳເລັດ (Safe)",
                f"✅ Page ຖືກຕ້ອງກົງກັນ 100%!\n\n"
                f"• ຊື່ Page ທີ່ເປີດຢູ່: {active_name}\n"
                f"• Page ID: {active_id}\n"
                f"• UID Facebook: {c_user}\n\n"
                f"ລະບົບປ້ອງກັນພ້ອມເຮັດວຽກ ຈະບໍ່ມີການລົງວິດີໂອໃສ່ເພຈບໍລິສັດແນ່ນອນ."
            )
        else:
            self.lbl_verify_result.setText(f"⚠️ ແຈ້ງເຕືອນ: Page ທີ່ເປີດຢູ່ແມ່ນ [{active_name}] (ID: {active_id}) ບໍ່ກົງກັບເປົ້າໝາຍ!")
            self.lbl_verify_result.setStyleSheet("color: #f38ba8; font-size: 11px; font-weight: bold;")
            QMessageBox.critical(
                self,
                "ກວດພົບ Page ບໍ່ກົງກັນ! (Warning)",
                f"⚠️ ຄຳເຕືອນຄວາມປອດໄພ:\n\n"
                f"Page ທີ່ເປີດຢູ່ປັດຈຸບັນ: '{active_name}' (ID: {active_id})\n"
                f"ແຕ່ເປົ້າໝາຍທີ່ຕັ້ງໄວ້: '{self.config.get('page_name')}' (ID: {self.config.get('page_id')})\n\n"
                f"ຫາກກົດເລີ່ມອັບໂຫຼດ ລະບົບຈະ Block ທັນທີເພື່ອປ້ອງກັນບໍ່ໃຫ້ລົງຜິດເພຈບໍລິສັດ.\n"
                f"ກະລຸນາເລືອກສະຫຼັບ Page ໃນ Meta Business Suite ໃຫ້ຖືກຕ້ອງກ່ອນ."
            )

    def post_cta_photo_action(self):
        reply = QMessageBox.question(
            self,
            "ຢືນຢັນການໂພສຮູບເຊີນຊວນ",
            "ທ່ານຕ້ອງການໂພສຮູບເຊີນຊວນຄົນກົດຕິດຕາມເພຈ (Follower CTA Photo) ດຽວນີ້ເລີຍຫຼືບໍ່?\n"
            "(ລະບົບຈະເລືອກຮູບ Banner ທີ່ສວຍງາມ ແລະ ສ້າງແຄບຊັ່ນດຶງດູດຄົນຕິດຕາມໃຫ້ອັດຕະໂນມັດ)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        self.log_message("📸 ກຳລັງເລີ່ມໂພສຮູບພາບເຊີນຊວນຕິດຕາມ (Follower CTA Post)...")
        if hasattr(self, 'upload_progress_lbl'):
            self.upload_progress_lbl.setText("📸 ກຳລັງໂພສຮູບເຊີນຊວນຕິດຕາມ...")
        if hasattr(self, 'upload_progress_bar'):
            self.upload_progress_bar.setValue(10)

        self.cta_thread = PostCtaThread(self.config)
        self.cta_thread.log_signal.connect(self.log_message)
        self.cta_thread.progress_signal.connect(self.on_upload_progress)
        self.cta_thread.finished_signal.connect(self.on_post_cta_finished)
        self.cta_thread.start()

    def on_post_cta_finished(self, success: bool):
        if success:
            if hasattr(self, 'upload_progress_bar'):
                self.upload_progress_bar.setValue(100)
            if hasattr(self, 'upload_progress_lbl'):
                self.upload_progress_lbl.setText("✅ ໂພສຮູບເຊີນຊວນຕິດຕາມສຳເລັດ!")
            QMessageBox.information(self, "ສຳເລັດ", "🎉 ໂພສຮູບພາບເຊີນຊວນຕິດຕາມเพจ (Follower CTA) ຮຽບຮ້ອຍແລ້ວ!")
        else:
            if hasattr(self, 'upload_progress_lbl'):
                self.upload_progress_lbl.setText("❌ ໂພສຮູບເຊີນຊວນຕິດຕາມລົ້ມເຫຼວ")
            QMessageBox.warning(self, "ລົ້ມເຫຼວ", "❌ ບໍ່ສາມາດໂພສຮູບພາບເຊີນຊວນໄດ້ ກະລຸນາກວດສອບ Log.")

    def open_cta_images_folder(self):
        folder = os.path.abspath(self.config.get("cta_images_folder", "./cta_images"))
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(f'explorer "{folder}"')
        else:
            subprocess.Popen(["xdg-open", folder])

    def execute_remote_cta(self):
        self.log_message("📸 [Remote CTA] ກຳລັງເລີ່ມຕົ້ນໂພສຮູບພາບ Follower CTA ຕາມຄຳສັ່ງຈາກມືຖື...")
        if hasattr(self, 'upload_progress_lbl'):
            self.upload_progress_lbl.setText("📸 ກຳລັງໂພສຮູບເຊີນຊວນຕິດຕາມ...")
        if hasattr(self, 'upload_progress_bar'):
            self.upload_progress_bar.setValue(10)

        self.cta_thread = PostCtaThread(self.config)
        self.cta_thread.log_signal.connect(self.log_message)
        self.cta_thread.progress_signal.connect(self.on_upload_progress)
        self.cta_thread.finished_signal.connect(self.on_post_cta_finished)
        self.cta_thread.start()

    def handle_remote_action(self, action: str, payload: Optional[dict] = None):
        action_clean = str(action).lower().strip()
        payload = payload or {}

        if action_clean == "start":
            self.log_message("📱 [Remote] ໄດ້ຮັບຄຳສັ່ງ 'ເລີ່ມຕົ້ນ Auto Upload' (Start) ຜ່ານໂທລະສັບມືຖື")
            QTimer.singleShot(0, self.start_upload)
            return "Started"
        elif action_clean == "pause":
            self.log_message("📱 [Remote] ໄດ້ຮັບຄຳສັ່ງ 'ພັກຊົ່ວຄາວ' (Pause) ຜ່ານໂທລະສັບມືຖື")
            QTimer.singleShot(0, self.pause_upload)
            return "Paused"
        elif action_clean == "resume":
            self.log_message("📱 [Remote] ໄດ້ຮັບຄຳສັ່ງ 'ສືບຕໍ່ເຮັດວຽກ' (Resume) ຜ່ານໂທລະສັບມືຖື")
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                QTimer.singleShot(0, self.pause_upload)
            else:
                QTimer.singleShot(0, self.start_upload)
            return "Resumed"
        elif action_clean == "stop":
            self.log_message("📱 [Remote] ໄດ້ຮັບຄຳສັ່ງ 'ຢຸດ' (Stop) ຜ່ານໂທລະສັບມືຖື")
            QTimer.singleShot(0, self.stop_upload)
            return "Stopped"
        elif action_clean == "post_cta":
            self.log_message("📱 [Remote] ໄດ້ຮັບຄຳສັ່ງ 'AI Post Follower CTA' ຜ່ານໂທລະສັບມືຖື")
            QTimer.singleShot(0, self.execute_remote_cta)
            return "Triggered Remote CTA"
        elif action_clean == "switch_page":
            target_name = payload.get("page_name", "")
            target_id = str(payload.get("page_id", "")).strip()
            if target_id:
                self.config["page_name"] = target_name
                self.config["page_id"] = target_id
                save_config(self.config)
                QTimer.singleShot(0, self.update_dashboard_pages_display)
                if hasattr(self, 'web_state') and self.web_state:
                    self.web_state.update(page_name=target_name, page_id=target_id)
                self.log_message(f"📱 [Remote] ປ່ຽນ Target Page ເປັນ: '{target_name}' (ID: {target_id})")
                return f"Switched to {target_name}"
            return "Missing page_id"
        elif action_clean == "update_page_id":
            g_id = payload.get("group_id", "")
            p_idx = int(payload.get("page_index", 0))
            new_id = str(payload.get("page_id", "")).strip()
            if new_id and "page_groups" in self.config:
                for grp in self.config["page_groups"]:
                    if grp.get("group_id") == g_id:
                        if 0 <= p_idx < len(grp.get("pages", [])):
                            grp["pages"][p_idx]["page_id"] = new_id
                            if grp["pages"][p_idx].get("page_name") == self.config.get("page_name"):
                                self.config["page_id"] = new_id
                            save_config(self.config)
                            QTimer.singleShot(0, self.update_dashboard_pages_display)
                            self.log_message(f"📱 [Remote] ບັນທຶກ Page ID ໃໝ່: {new_id} ສຳລັບ '{grp['pages'][p_idx].get('page_name')}'")
                            return f"Updated Page ID: {new_id}"
            return "Group or index not found"
        elif action_clean == "update_settings":
            min_d = payload.get("min_delay")
            max_d = payload.get("max_delay")
            pfx = payload.get("title_prefix")
            if min_d is not None:
                self.config["delay_min_seconds"] = int(min_d)
            if max_d is not None:
                self.config["delay_max_seconds"] = int(max_d)
            if pfx is not None:
                self.config["title_prefix"] = str(pfx)
            save_config(self.config)
            self.log_message("📱 [Remote] ບັນທຶກການຕັ້ງຄ່າ Delays / Prefix ຜ່ານມືຖືສຳເລັດ")
            return "Updated Settings"

        return f"Unknown action: {action_clean}"

    def copy_cloud_link(self):
        cloud_u = self.config.get("web_monitor", {}).get("cloud_relay_url", "").strip()
        if not cloud_u:
            QMessageBox.information(self, "ແຈ້ງເຕືອນ", "ຍັງບໍ່ໄດ້ກຳນົດ Cloud Relay URL. ກະລຸນາໄປທີ່ໜ້າຕັ້ງຄ່າເພື່ອໃສ່ URL ຈາກ Render.com.")
            return
        QApplication.clipboard().setText(cloud_u)
        QMessageBox.information(self, "ຄັດລອກສຳເລັດ", f"ຄັດລອກ Cloud Link ແລ້ວ:\n{cloud_u}\n\nສາມາດສົ່ງ Link ນີ້ໄປເປີດໃນໂທລະສັບ (4G/5G) ໄດ້ທຸກບ່ອນທົ່ວໂລກ.")

    def copy_mobile_link(self):
        url = self.mobile_local_url
        QApplication.clipboard().setText(url)
        QMessageBox.information(self, "ຄັດລອກສຳເລັດ", f"ຄັດລອກ Wi-Fi Link ແລ້ວ:\n{url}\n\nສາມາດເປີດຜ່ານໂທລະສັບທີ່ເຊື່ອມຕໍ່ Wi-Fi ດຽວກັນ.")

    def copy_public_link(self):
        url = self.config.get("web_monitor", {}).get("cloud_relay_url", "").strip()
        if not url:
            url = self.web_state.public_url if (hasattr(self, 'web_state') and self.web_state.public_url) else self.mobile_local_url
        QApplication.clipboard().setText(url)
        QMessageBox.information(self, "ຄັດລອກສຳເລັດ", f"ຄັດລອກ Link ແລ້ວ:\n{url}")

    def show_mobile_qr_dialog(self):
        cloud_u = self.config.get("web_monitor", {}).get("cloud_relay_url", "").strip()
        url = cloud_u if (cloud_u and cloud_u.startswith("http")) else self.mobile_local_url
        dialog = QDialog(self)
        dialog.setWindowTitle("📱 ສະແກນ QR Code ເພື່ອຕິດຕາມຜ່ານໂທລະສັບ")
        dialog.resize(360, 460)
        vbox = QVBoxLayout(dialog)

        lbl_t = QLabel("📲 ສະແກນດ້ວຍກ້ອງຖ່າຍຮູບໂທລະສັບມືຖື")
        lbl_t.setAlignment(Qt.AlignCenter)
        lbl_t.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa; padding: 4px;")
        vbox.addWidget(lbl_t)

        lbl_url = QLabel(f"<a href='{url}' style='color: #4cc9f0; font-weight: bold;'>{url}</a>")
        lbl_url.setAlignment(Qt.AlignCenter)
        lbl_url.setOpenExternalLinks(True)
        vbox.addWidget(lbl_url)

        qr_img_lbl = QLabel()
        qr_img_lbl.setAlignment(Qt.AlignCenter)
        qr_img_lbl.setFixedHeight(260)
        qr_img_lbl.setText("⏳ ກຳລັງໂຫຼດ QR Code...")
        vbox.addWidget(qr_img_lbl)

        try:
            import urllib.parse, requests
            enc = urllib.parse.quote(url)
            qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={enc}"
            r = requests.get(qr_api, timeout=6)
            if r.status_code == 200:
                pix = QPixmap()
                pix.loadFromData(r.content)
                qr_img_lbl.setPixmap(pix)
            else:
                qr_img_lbl.setText("ບໍ່ສາມາດໂຫຼດ QR ໄດ້ (ກະລຸນາເປີດ Link ໂດຍກົງ)")
        except Exception as e:
            qr_img_lbl.setText(f"ບໍ່ສາມາດໂຫຼດ QR: {e}")

        lbl_tip = QLabel("✨ ທ່ານຈະເຫັນ % ອັບໂຫຼດ, ຄິວວິດີໂອ, ຊື່ເລື່ອງ ແລະ Log ສົດໆຜ່ານໂທລະສັບໄດ້ຕະຫຼອດເວລາ.")
        lbl_tip.setWordWrap(True)
        lbl_tip.setAlignment(Qt.AlignCenter)
        lbl_tip.setStyleSheet("color: #a6adc8; font-size: 11px; padding: 4px;")
        vbox.addWidget(lbl_tip)

        btn_ok = QPushButton("ປິດໜ້າຕ່າງ")
        btn_ok.clicked.connect(dialog.accept)
        vbox.addWidget(btn_ok)
        dialog.exec()

    def test_ai_gen_action(self):
        self.log_message("🎨 ກຳລັງທົດລອງສັງເຄາະຮູບພາບ AI ແລະ Caption ບໍ່ຊ້ຳກັນ...")
        try:
            from core.ai_image_generator import AiImageGenerator
            gen = AiImageGenerator(self.config)
            img_path, cap, title = gen.generate_unique_cta_post()
            self.log_message(f"✅ AI ສ້າງຮູບພາບສຳເລັດ: '{title}' -> {os.path.basename(img_path)}")

            # Show preview dialog
            dlg = QDialog(self)
            dlg.setWindowTitle(f"🎨 ຕົວຢ່າງຮູບພາບ AI - {title}")
            dlg.resize(520, 680)
            dvbox = QVBoxLayout(dlg)

            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignCenter)
            pix = QPixmap(img_path).scaled(460, 460, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_lbl.setPixmap(pix)
            dvbox.addWidget(img_lbl)

            txt_cap = QTextEdit()
            txt_cap.setPlainText(cap)
            txt_cap.setMaximumHeight(140)
            txt_cap.setReadOnly(True)
            dvbox.addWidget(txt_cap)

            btn_box = QHBoxLayout()
            btn_open = QPushButton("📂 ເປີດໄຟລ໌ຮູບ")
            btn_open.clicked.connect(lambda: subprocess.Popen(f'explorer /select,"{os.path.abspath(img_path)}"'))
            btn_close = QPushButton("ປິດ")
            btn_close.clicked.connect(dlg.accept)
            btn_box.addWidget(btn_open)
            btn_box.addWidget(btn_close)
            dvbox.addLayout(btn_box)

            dlg.exec()
        except Exception as e:
            self.log_message(f"❌ AI Gen Error: {e}")
            QMessageBox.critical(self, "AI Gen Failed", f"ເກີດຂໍ້ຜິດພາດ: {e}")

    def test_send_notification(self):
        from core.notifier import MobileNotifier
        cfg = dict(self.config)
        cfg["whatsapp_notify"] = {
            "enabled": True,
            "phone": self.txt_wa_phone.text().strip(),
            "apikey": self.txt_wa_key.text().strip()
        }
        notif = MobileNotifier(cfg)
        test_msg = (
            f"🔔 *[Reels Bot] ທົດສອບການແຈ້ງເຕືອນ!* ✅\n\n"
            f"ລະບົບເຊື່ອມຕໍ່ກັບ WhatsApp ສຳເລັດແລ້ວ.\n"
            f"ທ່ານຈະໄດ້ຮັບລາຍງານເມື່ອວິດີໂອອັບໂຫຼດສຳເລັດ ຫຼື ເກີດຂໍ້ຜິດພາດ.\n"
            f"⏱ ເວລາ: {datetime.now().strftime('%H:%M:%S')}"
        )
        notif.send_async(test_msg)
        QMessageBox.information(
            self,
            "ສົ່ງຂໍ້ຄວາມແລ້ວ",
            f"ກຳລັງສົ່ງຂໍ້ຄວາມທົດສອບໄປຍັງ WhatsApp: {cfg['whatsapp_notify']['phone']}\n"
            f"ກະລຸນາກວດເບິ່ງຂໍ້ຄວາມໃນໂທລະສັບຂອງທ່ານ."
        )


def main():
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ThaiMovieDrama.ReelsBot.Instance2")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app_icon = os.path.abspath("./app_icon.ico")
    if os.path.exists(app_icon):
        app.setWindowIcon(QIcon(app_icon))

    # ตั้งค่า Font ไทย (Leelawadee UI) เป็นฟอนต์เริ่มต้นของระบบ
    font = QFont("Leelawadee UI", 10)
    app.setFont(font)

    window = MainWindow()
    if os.path.exists(app_icon):
        window.setWindowIcon(QIcon(app_icon))
    # Offset window so it does not overlap Bot 1
    window.move(260, 100)
    window.show()
    window.raise_()
    window.activateWindow()

    # Auto-start upload if requested via commandline
    if any(arg in sys.argv for arg in ["--autostart", "--start", "-a"]):
        print("🚀 [AutoStart] Triggering automatic upload start in 1 second...")
        QTimer.singleShot(1000, window.start_upload)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()