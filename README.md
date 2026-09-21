# 🤖 Facebook Page Reels Auto-Uploader Bot

ລະບົບອັດຕະໂນມັດສຳລັບອັບໂຫຼດ Facebook Reels ລົງ Page ຜ່ານ **Meta Business Suite Browser Automation (Playwright)**.

---

## 💡 ເປັນຫຍັງໃຊ້ API ແລ້ວ Reach ເປັນ 0 / ບໍ່ມີຄົນເຫັນ?
1. **Facebook Graph API Restrictions:** ການອັບໂຫຼດ Reel ຜ່ານ App API ທີ່ບໍ່ໄດ້ຮັບການ verify ຫຼື ບໍ່ແມ່ນ Meta Business Partner ຈະຖືກ algorithm ຂອງ Facebook ຫຼຸດການແຈກຈ່າຍ (Zero Distribution / Reach Shadowban).
2. **ວິທີແກ້ໄຂ:** ໂປຣແກຣມນີ້ໃຊ້ **Playwright Browser Automation** ຈຳລອງການໃຊ້ Google Chrome ແທ້ໆ ເຂົ້າໄປທີ່ Meta Business Suite Reels Composer, ເຮັດໃຫ້ Facebook ເຫັນວ່າເປັນຄົນແທ້ໆກຳລັງອັບໂຫຼດຜ່ານໜ້າເວັບ, ໄດ້ Reach ແລະ ຍອດວິວຕາມ Algorithm ປົກກະຕິ 100%.

---

## 🌟 ຄຸນສົມບັດຫຼັກ (Features)
- 📁 **Batch Upload ວິດີໂອຈຳນວນຫຼາຍ:** ພຽງແຕ່ເອົາໄຟລ໌ວິດີໂອໃສ່ໃນໂຟນເດີ `videos/`, ລະບົບຈະດຶງໄປອັບໂຫຼດເທື່ອລະຄລິບຕາມລຳດັບ.
- 🇨🇳 **China AI Reel Movie Mode (ລະບົບຕັ້ງຊື່ເລື່ອງ & ວິເຄາະໜ້າປົກອັດຕະໂນມັດ):**
  - **ຖ້າໄຟລ໌ມີຊື່:** ລະບົບຈະດຶງຊື່ໄຟລ໌ມາແປງເປັນ Title ທີ່ສວຍງາມ (ຕັດເລກຄວາມລະອຽດ, ຂີດກ້ອງ, ວົງເລັບອອກ).
  - **ຖ້າໄຟລ໌ບໍ່ມີຊື່ (ຊື່ຕົວເລກ/Generic ເຊັ່ນ: `1234.mp4`, `vid_01`):** ລະບົບຈະດຶງຮູບໜ້າປົກ (Cover Frame) ມາວິເຄາະດ້ວຍ Gemini AI Vision ຫຼື ເລືອກຊື່ເລື່ອງ China AI Drama ສຸດດຣາມາ ດຶງດູດຍອດວິວ (ແນວມະຫາເສດຖີປອມຕົວ, ຍ້ອນເວລາແກ້ແຄ້ນ, ເທບສົງຄາມ, ປະທານໃຫຍ່) ພ້ອມເລກຕອນ `ຕອນທີ {index}` ໃຫ້ອັດຕະໂນມັດ!
- ✍️ **Caption & Tags Template Engine:**
  - ຮອງຮັບຕົວປ່ຽນໃນ Template: `{title}`, `{tags}`, `{date}`, `{time}`, `{index}`, `{filename}`.
  - ຄັງ Hashtags Pool ຈີນ AI: `#ໜັງສັ້ນຈີນ #ຊີຣີຈີນ #chinaai #reelsdrama #aiart #ຮູບເງົາຈີນ #fyp`.
  - ປຸ່ມທົດສອບວິເຄາະວິດີໂອ ແລະ Live Preview ສົມມຸດ 2 ກໍລະນີ (ໄຟລ໌ມີຊື່ vs ໄຟລ໌ບໍ່ມີຊື່).
- 🔐 **Login ຄັ້ງດຽວ (Persistent Profile):** ບັນທຶກ Session/Cookies ໄວ້ໃນ `user_profile/` ບໍ່ຕ້ອງ Login ຊ້ຳ.
- ⏰ **ຕັ້ງເວລາ ຫຼື ໂພສທັນທີ (Publish Now & Schedule):**
  - Publish Now ພ້ອມລະບົບ Delay (ພັກ 15-30 ນາທີ) ເພື່ອປ້ອງກັນ Facebook Spam Block.
  - ຫຼື ເລືອກ Schedule ເພື່ອກະຈາຍເວລາໂພສ.
- 🖥️ **Desktop GUI (PySide6):** ມີໜ້າຕ່າງກົດງ່າຍ, ສະແດງສະຖິຕິ, ຕາຕະລາງຄິວ, ຕົວຢ່າງ Caption Live Preview, ແລະ Realtime Console Log.
- 💻 **CLI Mode:** ຮອງຮັບການສັ່ງການຜ່ານ Command Line.

---

## 🚀 ວິທີຕິດຕັ້ງ ແລະ ເລີ່ມຕົ້ນໃຊ້ງານ

### 1. ເປີດໂປຣແກຣມ (Desktop GUI)
ກົດ Run ໄຟລ໌ `run.py` ຫຼື ພິມຄຳສັ່ງ:
```bash
python run.py
```

### 2. ຂັ້ນຕອນການໃຊ້ງານ (3 ຂັ້ນຕອນງ່າຍໆ)
1. **Login Facebook (ຄັ້ງດຽວ):**
   - ໃນແຖບ **Dashboard**, ກົດປຸ່ມ **"🌐 ເປີດ Browser ເພື່ອ Login Facebook"**.
   - ໜ້າຕ່າງ Browser ຈະເປີດຂຶ້ນມາ -> ໃຫ້ທ່ານ Login Facebook ແລະ ເຂົ້າ Meta Business Suite ໃຫ້ຮຽບຮ້ອຍ -> ແລ້ວປິດໜ້າຕ່າງນັ້ນ.
   - ລະບົບຈະຈື່ Session ນີ້ໄວ້ຕະຫຼອດ.
2. **ຕັ້ງຄ່າ Caption & Tags:**
   - ໄປທີ່ແຖບ **Caption & Tags Studio**.
   - ປັບແຕ່ງ Template ຕາມໃຈມັກ ແລະ ເລືອກຈຳນວນ Tags.
   - ເບິ່ງຕົວຢ່າງ Live Preview ຢູ່ດ້ານລຸ່ມ ແລ້ວກົດ **Save**.
3. **ເລີ່ມຕົ້ນ Auto Upload:**
   - ເອົາໄຟລ໌ວິດີໂອທັງໝົດທີ່ຕ້ອງການລົງ ໄປໃສ່ໃນໂຟນເດີ `videos/`.
   - ກົດປຸ່ມ **"▶️ ເລີ່ມຕົ້ນ Auto Upload (Start)"**.
   - ບັອດຈະເລີ່ມອັບໂຫຼດ, ໃສ່ Title, Caption, Tags ແລະ Publish/Schedule ໃຫ້ແບບອັດຕະໂນມັດ!

---

## 💻 ການສັ່ງງານຜ່ານ CLI (Terminal)

- **Login ເຂົ້າສູ່ລະບົບ:**
  ```bash
  python cli.py --login
  ```
- **ກວດສອບຄິວວິດີໂອ:**
  ```bash
  python cli.py --check
  ```
- **ເລີ່ມຕົ້ນອັບໂຫຼດ:**
  ```bash
  python cli.py --start
  ```
- **ເລີ່ມຕົ້ນອັບໂຫຼດພ້ອມຕັ້ງຄ່າ Delay ແລະ ໂຟນເດີ:**
  ```bash
  python cli.py --start --delay 25 --folder "C:/MyVideos"
  ```
