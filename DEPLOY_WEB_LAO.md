# 🚀 ຄູ່ມືການເອົາ Web Dashboard ຂຶ້ນ Cloud (Render.com) & ຈັດການຜ່ານໂທລະສັບມືຖື 24/7

ລະບົບ Web Dashboard ໃໝ່ຖືກອອກແບບມາໃຫ້ຮອງຮັບການຈັດການ ແລະ ຄວບຄຸມ Bot ຜ່ານໂທລະສັບມືຖື (iPhone, Android) ໄດ້ 100%.

---

## 🌟 ວິທີທີ 1: ເອົາຂຶ້ນ Render.com (ຟຣີ 100%, ໄດ້ເວັບຖາວອນ 24/7)
ທ່ານຈະໄດ້ Link HTTPS ຖາວອນ ເຊັ່ນ: `https://reels-bot-dashboard.onrender.com` ທີ່ສາມາດບັນທຶກໃສ່ Home Screen ຂອງໂທລະສັບ ຄືກັບ Application ມືຖືແທ້ໆ, ເຂົ້າໄດ້ຕະຫຼອດເວລາ ບໍ່ມີຫຼຸດ ແລະ ບໍ່ຕິດ Error 530.

### ຂັ້ນຕອນ:
1. ສ້າງ Repository ໃໝ່ໃນ **GitHub** (ຕັ້ງເປັນ Public ຫຼື Private ກໍໄດ້)
2. Push ໂຄດຂຶ້ນ GitHub:
   ```bash
   git init
   git add .
   git commit -m "feat: mobile web dashboard"
   git branch -M main
   git remote add origin https://github.com/USERNAME/reels-bot-dashboard.git
   git push -u origin main
   ```
3. ເຂົ້າເວັບ **[Render.com](https://render.com)** -> ເລືອກ **New +** -> **Web Service**
4. ເລືອກ Repository ທີ່ຫາກໍ່ Push ຂຶ້ນໄປ
5. Render ຈະອ່ານໄຟລ໌ `render.yaml` ໃຫ້ອັດຕະໂນມັດ -> ກົດ **Deploy Web Service**
6. ເມື່ອ Deploy ສຳເລັດ ທ່ານຈະໄດ້ URL ເຊັ່ນ: `https://xxxxxx.onrender.com`
7. ເອົາ URL ນີ້ມາໃສ່ໃນໂປຣແກຣມ Bot (ໜ້າ Settings -> **Cloud Relay URL**) ແລ້ວກົດບັນທຶກ.
   *Bot ໃນຄອມພິວເຕີຈະ Sync ຂໍ້ມູນຂຶ້ນເວັບນີ້ອັດຕະໂນມັດທຸກໆ 2 ວິນາທີ!*

---

## ⚡ ວິທີທີ 2: ເປີດໃຊ້ຜ່ານ Wi-Fi ພາຍໃນເຮືອນ/ຫ້ອງການ (Instant Local Access)
ຖ້າໂທລະສັບ ແລະ ຄອມພິວເຕີເຊື່ອມຕໍ່ Wi-Fi ດຽວກັນ:
1. ເປີດ Safari ຫຼື Chrome ໃນໂທລະສັບ
2. ພິມ IP ຂອງຄອມພິວເຕີ: `http://192.168.1.3:5555` (ຫຼື ສະແກນ QR Code ຈາກໜ້າจอ Bot)
3. ຈະເຫັນໜ້າ Dashboard ແລະ ປຸ່ມຄວບຄຸມທັງໝົດທັນທີ.

---

## 🛡️ ຄວາມປອດໄພລະດັບສູງ (Security Hardened):
1. **PIN Code Lock & Anti-Brute-Force**: ເມື່ອເຂົ້າເວັບຄັ້ງທຳອິດ ຫຼື ຫຼັງຈາກກົດລັອກ, ລະບົບຈະຖາມຫາລະຫັດ PIN (ລະຫັດປັດຈຸບັນແມ່ນ `5564`).
   - ຖ້າກົດລະຫັດຜິດເກີນ 5 ຄັ້ງ, ລະບົບຈະ Block IP ນັ້ນ 15 ນາທີ (Anti-Brute Force & Attack Protection).
   - ມີລະບົບ Tarpit Delay (ໜ່ວງເວລາ 1 ວິນາທີຕໍ່ຄັ້ງທີ່ກົດຜິດ) ເພື່ອປ້ອງກັນບໍ່ໃຫ້ Bot/Script ສຸ່ມລະຫັດໄດ້ໂດຍສິ້ນເຊີງ.
   - ປ່ຽນລະຫັດ PIN ໄດ້ທີ່ `config.json` ຫົວຂໍ້ `"access_pin"` ຫຼື ຕັ້ງຄ່າ Environment Variable ໃນ Render ຊື່ `ACCESS_PIN`.
2. **Cloud Relay Secret Token (`X-Bot-Token`)**: 
   - ລະບົບມີ Token ຄວາມລັບ `b0015017e92db8567376789a3d0c12b0` ເພື່ອປ້ອງກັນບໍ່ໃຫ້ຄົນອື່ນສົ່ງຂໍ້ມູນປອມມາແຊກແຊງ Bot ຂອງທ່ານ.
   - ຖ້າ Deploy ເທິງ Render, Token ຈະຖືກຕັ້ງຄ່າຜ່ານ `SYNC_SECRET_TOKEN`.
3. **ປ້ອງກັນຂໍ້ມູນຮົ່ວໄຫຼ (Zero Credential Leak)**:
   - ໄຟລ໌ `.gitignore` ຖືກຕັ້ງຄ່າໄວ້ຢ່າງຮັດກຸມ 100% ບໍ່ໃຫ້ Upload `config.json`, Facebook Cookies, ຫຼື API Key ຂຶ້ນ GitHub ເດັດຂາດ.
   - ເວັບ Dashboard ບໍ່ເຄີຍສົ່ງ Cookies ຫຼື Gemini Key ອອກມາສະແດງຜົນໃນ Browser, ຮັບປະກັນຄວາມປອດໄພສູງສຸດ.

---

## 📱 ສິ່ງທີ່ສາມາດຈັດການຜ່ານໂທລະສັບມືຖືໄດ້:
1. **🚀 ຄວບຄຸມ Bot**: ກົດ ເລີ່ມອັບໂຫຼດ (Start), ພັກ (Pause), ສືບຕໍ່ (Resume), ຫຼື ຢຸດ (Stop).
2. **📸 ສັ່ງ AI**: ສັ່ງໃຫ້ AI Gen ຮູບພາບ ແລະ ໂພສ Follower CTA ລົງ Facebook ທັນທີ.
3. **🌐 ຈັດການ 4 Pages**: ເລືອກ Page ທີ່ຕ້ອງການໃຫ້ອັບໂຫຼດ, ແລະ ພິມແກ້ໄຂ Facebook Page ID ໄດ້ໂດຍກົງ.
4. **📦 ເບິ່ງຄິວວິດີໂອ**: ກວດເບິ່ງລາຍຊື່ໄຟລ໌ວິດີໂອທີ່ກຳລັງລໍຖ້າອັບໂຫຼດ.
5. **⚙️ ຕັ້ງຄ່າລະບົບ**: ປັບ Delay ວິນາທີ, ເປີດ/ປິດຄຳນຳໜ້າ `[เต็มเรื่อง]` ຜ່ານມືຖື.
6. **📜 ອ່ານ Log ສົດ**: ຕິດຕາມຂັ້ນຕອນການອັບໂຫຼດແບບ Real-time.
7. **🔒 ລັອກໜ້າຈໍ**: ກົດປຸ່ມແມ່ກະແຈ 🔒 ມຸມຂວາເທິງ ເພື່ອລັອກໜ້າຈໍທັນທີເມື່ອເຊົາໃຊ້ງານ.
