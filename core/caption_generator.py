import os
import sys
import re
import json
import time
import random
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================================
# CONTENT PRESETS REGISTRY
# ==============================================================================
CONTENT_PRESETS = {
    "china_drama": {
        "id": "china_drama",
        "name": "🎬 ໜັງສັ້ນ / ຊີຣີສ໌ຈີນ AI (ເຕັມເລື່ອງ)",
        "title_prefix": "[เต็มเรื่อง] ",
        "default_template": "🎬 {title}\n\n🔥 ซีรีส์สั้นจีน AI ดราม่าเข้มข้น สุดมันส์!\n📌 ติดตามเรื่องใหม่ๆ ได้ทุกวัน อย่าลืมกด Like & Share เพื่อเป็นกำลังใจให้ด้วยนะครับ! ✨\n\n{tags}",
        "default_tags": [
            "#หนังสั้นจีน", "#ซีรีส์จีน", "#ละครสั้น", "#chinaai", "#chinesedrama",
            "#reelsdrama", "#aiart", "#หนังจีน", "#reels", "#fyp", "#viral", "#reelsfb"
        ]
    },
    "lao_girl_khaohom": {
        "id": "lao_girl_khaohom",
        "name": "🌸 ນ້ອງເຂົ້າຫອມ ສາວຂີ້ດື້ (ສາວນັກຮຽນລາວໜ້າຮັກ)",
        "title_prefix": "",
        "default_template": "✨ {title}\n\n💖 น้องข้าวหอม สาวขี้ดื้อ มาแจกความสดใสแล้วค่าา~ ฝากกด Like & Share และติดตามเป็นกำลังใจให้หนูด้วยน้าา 💕✨\n\n{tags}",
        "default_tags": [
            "#น้องข้าวหอม", "#สาวขี้ดื้อ", "#สาวลาวน่ารัก", "#ความน่ารักสดใส",
            "#สาวนักเรียน", "#แจกความสดใส", "#คลิปน่ารัก", "#reels", "#fyp", "#viral", "#reelsfb"
        ]
    },
    "news_knowledge": {
        "id": "news_knowledge",
        "name": "📰 ຂ່າວສານ / ສາລະໜ້າຮູ້",
        "title_prefix": "[ຂ່າວດ່ວນ] ",
        "default_template": "📰 {title}\n\n📌 ອັບເດດເລື່ອງລາວ ແລະ ສາລະໜ້າຮູ້ ຕິດຕາມໄດ້ທີ່ນີ້! ກົດ Like & Share ເພື່ອບໍ່ພາດເລື່ອງໃໝ່ໆ ✨\n\n{tags}",
        "default_tags": [
            "#ข่าว", "#สรุปข่าว", "#สาระน่ารู้", "#ข่าวtiktok", "#อัปเดต", "#reels", "#viral"
        ]
    },
    "comedy_viral": {
        "id": "comedy_viral",
        "name": "😂 ຕະຫຼົກ / ຄລິບໄວຣັລ",
        "title_prefix": "",
        "default_template": "😂 {title}\n\n🤣 ຄາຍຄຽດໄປນຳກັນ! ຢ່າລືມກົດ Like & Share ແບ່ງປັນຮອຍຍິ້ມໃຫ້ໝູ່ເພື່ອນແດ່ເດີ ✨\n\n{tags}",
        "default_tags": [
            "#คลิปตลก", "#ฮาๆ", "#คลิปไวรัล", "#ขำๆ", "#reelsfb", "#viral"
        ]
    },
    "custom": {
        "id": "custom",
        "name": "⚙️ ກຳນົດເອງ (Custom)",
        "title_prefix": "",
        "default_template": "✨ {title}\n\n📌 ຕິດຕາມເນື້ອຫາພິເສດສະເພາະໄດ້ທີ່ນີ້! ຢ່າລືມກົດ Like & Share ເພື່ອເປັນກຳລັງໃຈໃຫ້ແດ່ເດີ! ✨\n\n{tags}",
        "default_tags": [
            "#reels", "#viral", "#facebookreels", "#fyp"
        ]
    }
}


class CaptionGenerator:
    """
    Intelligent Title & Caption Generator designed for China AI Reel Movies and Persona Reels.
    - Automatically extracts video cover thumbnail and analyzes scene with Gemini AI Vision
      to generate a viral, captivating title and caption in Thai matching the specific Content Category.
    - Supports multi-category personas:
        * china_drama: China AI Mini-Dramas (Full Movie, revenge, rebirth, CEO).
        * lao_girl_khaohom: 'น้องข้าวหอม สาวขี้ดื้อ' (Fictional cute Lao student girl, 14-16 yrs, playful, cute, Thai content).
        * news_knowledge: News & updates.
        * comedy_viral: Funny & viral clips.
    - Seamlessly falls back to curated pools if AI is offline or rate-limited.
    - Detects and filters out scraped junk filenames (view counts, links, "กดติดตาม", "เต็มเรื่อง", etc.).
    """

    # Curated pool of 50+ viral Thai China AI Drama titles (แนวประธานใหญ่, มหาเศรษฐีปลอมตัว, ย้อนเวลา, เทพสงคราม, วังหลวง, แก้แค้น)
    CHINA_DRAMA_TITLES = [
        "ประธานใหญ่ปลอมตัวเป็นคนธรรมดา ถูกดูถูกว่าจน",
        "มหาเศรษฐีอันดับ 1 ปลอมตัวเป็นคนขับรถเพื่อลองใจสาว",
        "ย้อนเวลากลับมา 5 ปีก่อน เพื่อแก้แค้นตระกูลใหญ่",
        "ถูกไล่ออกจากบ้าน โดยไม่รู้ว่าความจริงคือทายาทหมื่นล้าน",
        "เทพสงครามไร้พ่าย หวนคืนเมืองหลวงเพื่อปกป้องคนรัก",
        "เมียน้อยท้าทาย แต่หารู้ไม่ว่าเมียหลวงคือประธานใหญ่",
        "3 ปีแห่งการดูถูก วันนี้ถึงเวลาเปิดเผยฐานะที่แท้จริง",
        "ลูกสาวมหาเศรษฐีตกยาก ถูกคู่หมั้นและครอบครัวทรยศ",
        "ประธานหนุ่มปลอมเป็นคนทำความสะอาด ใครจะกล้ารังแก",
        "ราชาโลกใต้ดิน ปลอมตัวมาดูแลแม่ค้าข้างทาง",
        "หญิงสาวธรรมดา ถูกประธานสายโหดบังคับแต่งงาน",
        "เปิดเผยฐานะมหาเศรษฐีกลางงานเลี้ยง ทำเอาทุกคนหน้าซีด",
        "แฟนเก่าดูถูกว่าจน พอรู้ความจริงถึงกับคุกเข่าขอร้อง",
        "จอมราชันย์หวนคืน เมืองหลวงต้องสั่นสะเทือน",
        "ประธานสาวสายโหด กับบอดี้การ์ดหนุ่มสุดลึกลับ",
        "ราชันย์มังกรซ่อนกาย ใครกล้าแตะต้องภรรยาข้าต้องตาย",
        "หมอเทวดาผู้ไร้ชื่อเสียง กอบกู้ตระกูลใหญ่ในพริบตา",
        "ถูกทิ้งให้ยากลำบาก 10 ปีผ่านไปกลับมาพร้อมกองทัพ",
        "เล่ห์รักค่ำคืนในวังหลวง ชายาผู้ซ่อนพิษแค้น",
        "สนมเอกผู้ถูกลืม พลิกชะตากลับมาครองบัลลังก์วังหลัง",
        "แม่ทัพหญิงยอดดวงใจ สยบหัวใจจักรพรรดิผู้เย็นชา",
        "เกิดใหม่ในร่างสาวชาวบ้าน พร้อมระบบเทพสร้างความร่ำรวย",
        "คุณหนูตัวจริงกลับบ้าน แต่กลับถูกครอบครัวรังแกจนต้องเปิดหน้าสู้",
        "รักสามเส้าในตระกูลทรงอิทธิพล ใครคือผู้บงการที่แท้จริง",
        "ภรรยาสายลับปลอมตัวมาสืบความลับสามีมหาเศรษฐี",
        "สามีใบ้ที่ทุกคนดูถูก แท้จริงคือผู้นำองค์กรลับอันดับหนึ่ง",
        "ลูกเขยสวะที่ทุกคนเหยียบย่ำ แท้จริงคือมหาเศรษฐีเบื้องหลัง",
        "ทายาทตระกูลกู้ หวนคืนทวงทุกสิ่งที่เป็นของตัวเอง",
        "พลิกชะตาฟ้ากำหนด จากเด็กกำพร้าสู่ราชาธุรกิจหมื่นล้าน",
        "นางพญาคืนถิ่น วันนี้จะไม่มีใครรังแกฉันได้อีกต่อไป",
        "ความลับในคืนวิวาห์ สามีของฉันไม่ใช่คนธรรมดา",
        "ซ่อนรักประธานหน้าดุ ยิ่งหนีเขายิ่งตามตื๊อ",
        "ย้อนเวลากลับมาเอาคืนเพื่อนรักหักเหลี่ยมโหด",
        "เล่ห์กลลวงใจ มหาเศรษฐีคลั่งรักภรรยาที่หย่าร้าง",
        "ชะตารักบัลลังก์เลือด สนมกำมะลอกับฮ่องเต้ทรราช",
        "แม่ทัพไร้พ่ายกับหมอยาสาวผู้กุมหัวใจมังกร",
        "ลูกหนี้สาวกับเจ้าหนี้มหาเศรษฐีสายคลั่งรัก",
        "ปราบพยศประธานร้าย กลอุบายพิชิตหัวใจเย็นชา",
        "บอดี้การ์ดหน้าหวาน ที่แท้คือนักฆ่าอันดับหนึ่งของโลก",
        "ข้ามภพมาเป็นพระชายาตัวร้าย ที่ฮ่องเต้ต้องยอมสยบ",
        "วันเปิดพินัยกรรม ทุกคนถึงรู้ว่าใครคือเจ้าของมรดกตัวจริง",
        "การล้างแค้นของลูกสาวคนโต ที่ทุกคนคิดว่าตายไปแล้ว",
        "แกล้งจนเพื่อลองใจ แต่สิ่งที่ได้คือความเจ็บปวด",
        "สตรีผู้ถูกตราหน้าว่าไร้ค่า วันนี้คือผู้กำหนดชะตาทุกคน",
        "รักต้องห้ามในวังหลวง ระหว่างองครักษ์กับองค์หญิงใหญ่",
        "สามีผู้แสนดี แท้จริงคือเจ้าพ่อนักล่าในเงามืด",
        "สะใภ้บ้านนอกที่ทุกคนรังเกียจ แท้จริงคืออัจฉริยะกู้วิกฤต",
        "เมื่อความจริงเปิดเผย คนที่พวกเจ้าคุกเข่าให้คือข้า!",
        "สายเลือดมังกรที่ตื่นขึ้น พลิกฟ้าคว่ำแผ่นดิน",
        "คืนเดียวเปลี่ยนชีวิต จากคนธรรมดาสู่ผู้นำตระกูลสูงสุด"
    ]

    DRAMA_HOOKS = [
        "อย่าตัดสินคนจากภายนอก เพราะคนที่คุณดูถูก อาจเป็นคนที่คุณต้องก้มหัวให้...",
        "3 ปีที่ยอมอดทน วันนี้ถึงเวลาที่พวกเขาต้องชดใช้อย่างสาสม!",
        "คิดว่าฉันจนแล้วจะรังแกได้ง่ายๆ เหรอ? ถ้ารู้ฐานะที่แท้จริงแล้วอย่าร้องไห้นะ!",
        "ความรักที่แลกด้วยน้ำตา และการกลับมาทวงคืนทุกสิ่งที่เคยสูญเสีย...",
        "เมื่อความจริงถูกเปิดเผย ทำเอาทุกคนในงานเลี้ยงถึงกับหน้าซีดเผือด!",
        "คนที่เจ้าคิดว่าเป็นสวะ แท้จริงคือคนที่สามารถทำลายตระกูลเจ้าได้ในพริบตา...",
        "ยิ่งหนีเท่าไหร่ หัวใจยิ่งโหยหา ความลับในอดีตกำลังจะถูกเปิดโปง!",
        "ต่อหน้าทำเป็นคนธรรมดา แต่เบื้องหลังคือกุมชะตาคนทั้งเมือง..."
    ]

    # Curated pool for "น้องข้าวหอม สาวขี้ดื้อ" (Cute, playful Lao student girl, 14-16 yrs, Thai content)
    KHAOHOM_TITLES = [
        "วันนี้ดื้อได้มั้ยคะ ถ้าใจดีเดี๋ยวพาไปกินติม 🍦✨",
        "หนูไม่ได้ดื้อนะ แค่ซนไปหน่อยเอง 😝💕",
        "ส่งยิ้มหวานๆ ให้พี่ๆ วันนี้อย่าลืมยิ้มตอบหนูนะ 💖",
        "สาวลาวขี้ดื้อแอบมาแจกความสดใสค่าา ✨",
        "อย่าดุหนูเลยน้าา เดี๋ยวหนูทำตัวน่ารักให้ดู 🥺🎀",
        "มองหน้าหนูบ่อยๆ ระวังตกหลุมรักไม่รู้ตัวนะคะ 🙈💓",
        "แกล้งทำเป็นดื้อไปงั้น ที่จริงอยากให้พี่สนใจงับ 😚✨",
        "วันนี้หนูแต่งตัวเรียบร้อยแล้วน้าา น่ารักมั้ยคะ 💕",
        "ความสดใสของวัน อยู่ที่รอยยิ้มของน้องข้าวหอมนี่แหละค่ะ ✨",
        "ดื้อกับคนอื่น แต่หนูยอมใจดีกับพี่คนเดียวนะคะ 😜💗",
        "ถ้าพี่เหงา ทักมาหาน้องข้าวหอมสาวขี้ดื้อได้นะ 💬💖",
        "เลิกเรียนแล้ว รีบกลับบ้านมาแจกความน่ารักให้ทุกคนเลยค่า 🎒✨",
        "ใครบอกว่าหนูซน หนูแค่มีพลังความสดใสเยอะไปหน่อยเอง 😆🎀",
        "ยิ้มวันละนิด จิตแจ่มใส ยิ้มให้หนูหน่อยได้มั้ยคะ 🥰",
        "สาวน้อยแก้มป่อง วันนี้มีเรื่องมาฟ้องพี่ๆ ด้วยแหละ 😝💖",
        "หนูขี้อ้อนขนาดนี้ พี่จะไม่ใจอ่อนให้หนูจริงๆ เหรอคะ 🥺✨",
        "ความน่ารักไม่เข้าใครออกใคร แต่เข้าตาพี่บ้างรึยังคะ 🙈💓",
        "เด็กดื้อคนนี้ สัญญาว่าวันนี้จะไม่ซนเกิน 3 เวลาค่าา 😜💕",
        "วันนี้ทำการบ้านเสร็จแล้ว มาอ้อนพี่ๆ ได้รึยังน้าา 📚✨",
        "ส่งกำลังใจให้คนทำงานสู้ๆ ยิ้มหวานๆ จากน้องข้าวหอมค่า 🌸💕"
    ]

    KHAOHOM_HOOKS = [
        "น้องข้าวหอม สาวขี้ดื้อ มาแจกความสดใสแล้วค่าา~ ฝากกด Like & Share และติดตามเป็นกำลังใจให้หนูด้วยน้าา 💕✨",
        "เด็กดื้อวันนี้ มาส่งรอยยิ้มหวานๆ ให้พี่ๆ ทุกคนค่าา! อย่าลืมกดแชร์ให้หนูด้วยนะคะ 💖✨",
        "ใครเห็นคลิปนี้ขอให้มีแต่รอยยิ้มและความสุขทั้งวันเลยนะคะ รักทุกคนน้าา 🌸🎀",
        "หนูไม่ได้ดื้อจริงๆ นะคะพี่ๆ! ถ้าชอบความน่ารักสดใส อย่าลืมกดติดตามหนูไว้ด้วยน้าา 🥰✨",
        "แวะมาแจกความสดใสหลังเลิกเรียนค่าา ฝากเป็นกำลังใจให้น้องข้าวหอมด้วยนะคะ 🎒💕"
    ]

    GENERIC_NAME_PATTERNS = [
        r'^\d+$',                                              # purely numbers: 123456
        r'^(vid|video|clip|reels|mov|media|file|export|output|download|temp|untitled)[_\-\s\d]*$', # vid_01, video1, vid 01
        r'^[a-f0-9]{16,64}$',                                  # hex hash / md5 / uuid
        r'^\d{4}[\-_]?\d{2}[\-_]?\d{2}[_\-\s\d]*$',            # date timestamp: 20260918_120000
        r'^(tiktok|snapinst|fb|facebook|instagram)[_\-\s\w\d]*$', # downloader tags
        r'^[\W_]+$'                                            # only symbols
    ]

    GENERIC_BOILERPLATE = [
        r'^(?:ดู|มินิ)?ซีรี่?ย์จีน(?:แนวตั้ง)?$',
        r'^(?:สมาคมคนรักหนังจีน|แมวติดซีรีส์|คนบ้าหนัง|มาดูหนัง|สปอยหนัง)$',
        r'^(?:รวมพลคนดูหนัง\d*)$',
        r'^(?:หนังสั้น|ซีรีย์ส|ซีรี่|ซีรีส์|ละครสั้น)$',
        r'^(?:คลิป|ตอน|ตอนเต็ม|ตอนเดียวจบ|เต็มเรื่อง|มินิซีรี่ย์|ซีรี่ย์|ซีรีส์)$',
        r'^(?:ตอนที่\s*\d+|ep\s*\d+|part\s*\d+)$'
    ]

    TRUNCATED_COMPLETIONS = [
        (r'ตระกู$', 'ตระกูลใหญ่'),
        (r'สุดแข็งแ$', 'สุดแข็งแกร่ง'),
        (r'แข็งแ$', 'แข็งแกร่ง'),
        (r'ก่อนเปิดตัวเป$', 'ก่อนเปิดตัวเป็นประธานใหญ่'),
        (r'เปิดตัวเป$', 'เปิดตัวเป็นประธานใหญ่'),
        (r'ล่าหมู$', 'ล่าหมูป่า'),
        (r'ทวงแค้$', 'ทวงแค้น'),
        (r'ล้างแค้$', 'ล้างแค้น'),
        (r'แก้แค้$', 'แก้แค้น'),
        (r'มหาเศรษฐ$', 'มหาเศรษฐี'),
        (r'ประธา$', 'ประธานใหญ่'),
        (r'ทายา$', 'ทายาท'),
        (r'เทพสงครา$', 'เทพสงคราม'),
        (r'ราชั$', 'ราชันย์'),
        (r'ความทรงจ$', 'ความทรงจำ'),
        (r'ช่วยชีวิ$', 'ช่วยชีวิต'),
        (r'ซีรีย์ໃ$', 'ซีรีย์ใหม่ยอดฮิต'),
        (r'ซีรีย์ใหม$', 'ซีรีย์ใหม่ยอดฮิต'),
        (r'ซีรีส์ใหม$', 'ซีรีส์ใหม่ยอดฮิต'),
        (r'ล่าสือท$', 'ล่าเสือ'),
        (r'เจิดจร$', 'เจิดจรัส'),
        (r'ปลอมเป็นสา$', 'ปลอมเป็นสามี'),
        (r'บอกข่าวด$', 'บอกข่าวดี'),
        (r'สุดท้ายก็ยั$', 'สุดท้ายก็ยังหนีไม่พ้น'),
        (r'แต่ท่านกลับตามใ$', 'แต่ท่านกลับตามใจข้า'),
        (r'จุดเชื่อมต$', 'จุดเชื่อมต่อ'),
        (r'บ้านเดีย$', 'บ้านเดียวกัน'),
        (r'เริ่มโต้ก$', 'เริ่มโต้กลับ'),
        (r'ถึงได้รู้ว่าตัว$', 'ถึงได้รู้ว่าตัวเอง'),
        (r'ปล่อยเก$', 'ปล่อยเกาะ'),
        (r'โดนปล่อยเก$', 'โดนปล่อยเกาะ'),
        (r'พามาปล่อยเก$', 'พามาปล่อยเกาะ'),
        (r'ถูกทิ้$', 'ถูกทิ้ง'),
        (r'ทรยศหักหลั$', 'ทรยศหักหลัง'),
        (r'หักหลั$', 'หักหลัง')
    ]

    # Scraped junk patterns commonly found in downloaded Facebook/TikTok videos
    SCRAPED_JUNK_PATTERNS = [
        r'\b\d+(\.\d+)?[kKmM]\s*(views|reactions)\b',  # 1.5M views, 40K reactions
        r'https?:\S+',                                  # URLs (heylink, etc.)
        r'heylink\S*',
        r'\[\d{10,}\]',                                # Facebook IDs like [1045610895020596]
        r'กดติดตาม',
        r'เพื่อจะได้ไม่พลาด',
        r'อย่าลืมกดติดตาม',
        r'จะได้ไม่พลาด',
        r'เต็มเรื่อง',
        r'เต็​มเรื่อง',
        r'เต็มเรือง',
        r'ภาคแรก',
        r'ภาคสอง',
        r'ภาคต่อ',
        r'หัวจะปวด',
        r'#กดติดตาม',
        r'#จะได้ไม่พลาด'
    ]

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.template = config.get(
            "caption_template",
            "🎬 {title}\n\n🔥 ซีรีส์สั้นจีน AI ดราม่าเข้มข้น สุดมันส์!\n📌 ติดตามตอนใหม่ๆ ได้ทุกวัน อย่าลืมกด Like & Share เพื่อไม่พลาดตอนต่อไป! ✨\n\n{tags}"
        )
        self.hashtag_pool = config.get("hashtag_pool", [
            "#หนังสั้นจีน", "#ซีรีส์จีน", "#ละครสั้น", "#chinaai", "#chinesedrama",
            "#reelsdrama", "#aiart", "#หนังจีน", "#reels", "#fyp", "#viral", "#reelsfb"
        ])
        self.tags_count = config.get("tags_count", 6)
        self.ai_config = config.get("ai_caption", {})
        self.china_ai_config = config.get("china_ai_movie", {
            "enabled": True,
            "generate_catchy_title_if_no_name": True,
            "analyze_cover_frame": True
        })
        self.cache_file = os.path.abspath("./logs/ai_caption_cache.json")

    def _load_ai_cache(self) -> Dict[str, Any]:
        """Loads cached AI captions to prevent wasting API credits on repeated requests."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_ai_cache(self, cache: Dict[str, Any]):
        """Persists AI captions cache to disk safely."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_cached_ai_result(self, filename: str) -> Optional[Dict[str, str]]:
        """Retrieves previously generated AI title & caption if exists."""
        base = os.path.splitext(os.path.basename(filename))[0].strip()
        cache = self._load_ai_cache()
        if base in cache:
            return cache[base]
        return None

    def store_cached_ai_result(self, filename: str, title: str, caption: str, source: str = "ai_cached"):
        """Saves generated AI title & caption to avoid re-querying Gemini API in future runs."""
        base = os.path.splitext(os.path.basename(filename))[0].strip()
        cache = self._load_ai_cache()
        cache[base] = {
            "title": title,
            "caption": caption,
            "source": source,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_ai_cache(cache)

    @classmethod
    def is_meaningful_filename(cls, filename: str) -> bool:
        """
        Determines if a filename is truly a clean, meaningful custom name.
        Returns False if it is generic, purely numbers, or contains scraped junk (views, links, 'กดติดตาม').
        """
        base = os.path.splitext(os.path.basename(filename))[0].strip()
        if len(base) <= 3:
            return False

        lower_base = base.lower()
        for pattern in cls.GENERIC_NAME_PATTERNS:
            if re.match(pattern, lower_base):
                return False

        # Check for scraped Facebook / TikTok junk patterns
        for junk in cls.SCRAPED_JUNK_PATTERNS:
            if re.search(junk, base, re.IGNORECASE):
                return False

        # If base has at least some alphabetic characters
        alpha_count = len(re.findall(r'[a-zA-Z\u0E80-\u0EFF\u0E00-\u0E7F]', base))
        if alpha_count < 4:
            return False

        return True

    @classmethod
    def clean_filename(cls, filename: str) -> str:
        """
        Converts filename into a readable, clean movie or video title.
        Intelligently strips scraped Facebook/TikTok junk metrics (views, reactions, shares),
        brackets, IDs, channel spam, URLs, and video tech tags.
        Extracts the genuine drama title and completes truncated Thai endings if applicable.
        """
        base = os.path.splitext(os.path.basename(filename))[0].strip()
        if not base:
            return ""

        # 1. Remove URLs
        base = re.sub(r'https?://\S+|heylink\S*', '', base)

        # 2. Remove FB / Reel view/reaction/share metrics header: e.g. '1.1M views · 25K reactions ｜'
        metric_pat = r'^\s*(?:[\d\.,\s]+[kKmMbB]?\s*(?:views|reactions|shares|likes|การดู|ความรู้สึก|ยอดดู)[\s·,•|｜/\\–—-]*)+[🎬·:|\s–—\u2013\u2014-]*'
        base = re.sub(metric_pat, '', base, flags=re.IGNORECASE)
        base = re.sub(r'(?i)\b\d+(\.\d+)?[kmb]?\s*(?:views|reactions|shares|likes|การดู|ความรู้สึก|ยอดดู)\b', '', base)

        # 3. Remove trailing IDs like [1091750576836625] or (1091750576836625)
        base = re.sub(r'\[\s*\d{6,}\s*\]|\(\s*\d{6,}\s*\)|\{\s*\d{6,}\s*\}', '', base)

        # 4. Remove hashtags
        base = re.sub(r'#\S+', '', base)

        # 5. Iteratively remove common prefixes and suffixes
        prefixes = [
            r'^\s*【[^】]*】',
            r'^\s*\[[^\]]*\]',
            r'^\s*\([^\)]*\)',
            r'^\s*(?:รีวิวภาพยนตร์สนุกเต็มเรื่อง|รีวิวหนังสนุกเต็มเรื่อง|รีวิวหนัง|รีวิวภาพยนตร์|สปอยหนัง|สปอยล์หนัง|สปอยซีรีย์)[\s｜|–—\u2013\u2014-]*',
            r'^\s*(?:เต็มเรื่องในตอนเดียว|เต็มเ?เรื่อง|เต็​มเรื่อง|เต็มเรือง|ตอนเต็ม|ตอนเดียวจบ|คลิปเต็ม|พากย์ไทยเต็มเรื่อง)',
            r'^\s*FULL[\s–—\u2013\u2014-]*',
            r'^\s*(?:มินิซีรี่ย์จีน|มินิซีรี่ย์|ซีรี่ย์จีน|ซีรีส์จีน|หนังสั้นจีน|หนังสั้น|ละครสั้น)',
            r'^\s*#\d+\s*',
        ]
        suffixes = [
            r'[｜|]\s*(?:มินิซีรี่ย์จีน|มินิซีรี่ย์|ซีรี่ย์จีน|ซีรีส์จีน|ดูหนัง\s*ดูซีรีย์|เสื้อยืดปลีก-ส่ง|Cheng Rat|สปอยหนัง.*|คนบ้าหนัง.*|แมวติดซีรีส์.*).*$',
            r'on Reels.*$',
            r'ฝากกด\s*(?:ไลก|ติดตาม).*$',
            r'กดติดตาม.*$',
            r'จะได้ไม่พลาด.*$',
            r'เพื่อจะได้ไม่พลาด.*$',
            r'\(?ตอนเดียวจบ\)?$',
            r'\(?เต็มเรื่อง\)?$',
            r'【?เต็มเรื่อง】?$',
            r'\[?เต็มเรื่อง\]?$',
            r'#\S*$',
        ]
        for _ in range(5):
            changed = False
            for p in prefixes:
                new_base = re.sub(p, '', base, flags=re.IGNORECASE).strip()
                if new_base != base:
                    base = new_base
                    changed = True
            for s in suffixes:
                new_base = re.sub(s, '', base, flags=re.IGNORECASE).strip()
                if new_base != base:
                    base = new_base
                    changed = True

            base = re.sub(r'^[｜|🎬·:–—\u2013\u2014\-\s🦈🎞️💯🔥🍎🍊👉🔊👇💥✨❤️👑_]+', '', base).strip()
            base = re.sub(r'[｜|🎬·:–—\u2013\u2014\-\s🦈🎞️💯🔥🍎🍊👉🔊👇💥✨❤️👑_.]+$', '', base).strip()
            if not changed:
                break

        # 6. Convert underscores and separators to spaces if latin or tokenized
        if '_' in base or '.' in base or '-' in base:
            base = re.sub(r'[_\.-]+', ' ', base)

        # 7. Remove bracketed technical specs: [1080p], (720p), [fhd], etc.
        base = re.sub(r'\[\s*(?i:1080p|720p|480p|4k|2k|hd|fhd|uhd|hevc|x264|x265|bluray|web-dl|aac|mp4)\s*\]', ' ', base)
        base = re.sub(r'\(\s*(?i:1080p|720p|480p|4k|2k|hd|fhd|uhd|hevc|x264|x265|bluray|web-dl|aac|mp4)\s*\)', ' ', base)
        base = re.sub(r'\[\s*\]|\(\s*\)|\{\s*\}', ' ', base)

        # 8. Strip standalone resolution/tech tags
        base = re.sub(r'(?i)\b(1080p|720p|480p|4k|2k|hd|fhd|uhd|hevc|x264|x265|bluray|web-dl|aac|mp4)\b', ' ', base)

        # 9. Clean dangling unmatched brackets at ends
        base = re.sub(r'^[()\[\]{}]+|[()\[\]{}]+$', '', base).strip()

        # 10. Clean up extra punctuation/spaces
        base = re.sub(r'^[^\w\u0E00-\u0E7F\u0E80-\u0EFF]+|[^\w\u0E00-\u0E7F\u0E80-\u0EFF]+$', '', base).strip()
        base = re.sub(r'\s+', ' ', base).strip()

        # 11. Check if what remains is purely generic boilerplate
        for b_pat in cls.GENERIC_BOILERPLATE:
            if re.search(b_pat, base, re.IGNORECASE):
                return ""

        for g_pat in cls.GENERIC_NAME_PATTERNS:
            if re.match(g_pat, base.lower()):
                return ""

        # Check if there are meaningful chars
        char_count = len(re.findall(r'[\u0E00-\u0E7F\u0E80-\u0EFFa-zA-Z0-9]', base))
        if char_count < 3:
            return ""

        # 12. Complete truncated endings if matched
        for pat, repl in cls.TRUNCATED_COMPLETIONS:
            if re.search(pat, base):
                base = re.sub(pat, repl, base)
                break

        # 13. If ASCII, format as Title Case
        if base.isascii():
            base = base.title()

        return base

    def extract_cover_frame(self, video_path: str, timestamp_sec: float = 1.0) -> Optional[str]:
        """
        Extracts a video cover frame (thumbnail) using OpenCV at 1.0s (or 10% in) to analyze the scene.
        Uses safe MD5 hash filenames and cv2.imencode to guarantee Windows Unicode compatibility.
        """
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100
            target_frame = int(fps * timestamp_sec)
            if target_frame >= frame_count or target_frame <= 0:
                target_frame = int(frame_count * 0.1)

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return None

            thumb_dir = os.path.abspath("./logs/thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            safe_id = hashlib.md5(video_path.encode('utf-8')).hexdigest()
            thumb_path = os.path.join(thumb_dir, f"thumb_{safe_id}.jpg")

            # Safely encode and write image on Windows without non-ASCII path errors
            is_ok, buf = cv2.imencode(".jpg", frame)
            if is_ok:
                with open(thumb_path, "wb") as f:
                    f.write(buf)
                return thumb_path
            return None
        except Exception as e:
            print(f"[CaptionGenerator] Error extracting cover frame: {e}")
            return None

    def get_hashtags(self, count: Optional[int] = None) -> List[str]:
        """Returns a list of unique hashtags formatted with #"""
        k = count if count is not None else self.tags_count
        pool = list(set(self.hashtag_pool))
        
        formatted_pool = [t if t.startswith('#') else f"#{t}" for t in pool if t.strip()]
        if not formatted_pool:
            return ["#หนังสั้นจีน", "#ซีรีส์จีน", "#ละครสั้น", "#chinaai", "#reelsdrama"]

        if k >= len(formatted_pool):
            selected = formatted_pool
        else:
            selected = random.sample(formatted_pool, k)

        return selected

    @classmethod
    def extract_story_hints(cls, filename: str) -> str:
        """
        Strips views, reactions, boilerplate download spam, URLs, and IDs,
        leaving only meaningful story keywords if any exist.
        """
        return cls.clean_filename(filename)

    @classmethod
    def is_meaningful_drama_hint(cls, hint: str) -> bool:
        """Checks if hint contains actual story words rather than generic spam"""
        h = hint.strip().lower()
        if len(h) < 4:
            return False
        if re.match(r'^(ซีรีย์|ซีรีส์|หนังสั้น|ละคร|คลิป|video|reel|reels)[\sໃใหม\d]*$', h):
            return False
        thai_chars = len(re.findall(r'[\u0E00-\u0E7F]', h))
        return thai_chars >= 4

    def complete_truncated_story_title(self, hint: str, index: int = 1) -> str:
        """
        Completes cut-off words/sentences from truncated Facebook filenames.
        e.g.:
        'ตื่นจากหลับมา 100 ปี ทวงสัญญา 4 ตระกู' -> 'ตื่นจากหลับมา 100 ปี ทวงสัญญา 4 ตระกูลใหญ่'
        'สุดแข็งแ' -> 'สุดแข็งแกร่ง'
        'ก่อนเปิดตัวเป' -> 'ก่อนเปิดตัวเป็นประธานใหญ่'
        """
        t = hint.strip().rstrip('. ')
        completions = [
            (r'ตระกู$', 'ตระกูลใหญ่'),
            (r'ตระกูล$', 'ตระกูลใหญ่'),
            (r'สุดแข็งแ$', 'สุดแข็งแกร่ง'),
            (r'แข็งแ$', 'แข็งแกร่ง'),
            (r'ก่อนเปิดตัวเป$', 'ก่อนเปิดตัวเป็นประธานใหญ่'),
            (r'เปิดตัวเป$', 'เปิดตัวเป็นประธานใหญ่'),
            (r'ล่าหมู$', 'ล่าหมูป่า'),
            (r'ทวงแค้$', 'ทวงแค้น'),
            (r'ล้างแค้$', 'ล้างแค้น'),
            (r'แก้แค้$', 'แก้แค้น'),
            (r'มหาเศรษฐ$', 'มหาเศรษฐี'),
            (r'ประธา$', 'ประธานใหญ่'),
            (r'ประธาน$', 'ประธานใหญ่'),
            (r'ทายา$', 'ทายาทหมื่นล้าน'),
            (r'ทายาท$', 'ทายาทหมื่นล้าน'),
            (r'เทพสงครา$', 'เทพสงคราม'),
            (r'ราชั$', 'ราชันย์'),
            (r'ความทรงจ$', 'ความทรงจำ'),
            (r'ช่วยชีวิ$', 'ช่วยชีวิต'),
            (r'ซีรีย์ໃ$', 'ซีรีย์ยอดฮิต'),
            (r'ซีรีย์ใหม$', 'ซีรีย์ใหม่ยอดฮิต'),
            (r'ซีรีส์ใหม$', 'ซีรีส์ใหม่ยอดฮิต')
        ]
        for pattern, repl in completions:
            if re.search(pattern, t):
                t = re.sub(pattern, repl, t)
                break
        else:
            # Fallback: If not matched in static dictionary, ask Gemini AI to complete the truncated word
            ai_completed = self.complete_truncated_with_ai(t)
            if ai_completed:
                t = ai_completed

        # Remove existing episode tags if any
        t = re.sub(r'(?:\s*ตอนที่\s*\d+|\s*ตอน\s*\d+|\s*ep\s*\d+|\s*part\s*\d+)+$', '', t, flags=re.IGNORECASE).strip()
        t = re.sub(r'^(?:ตอนที่\s*\d+\s*|ตอน\s*\d+\s*|ep\s*\d+\s*)[:\-–—\s]*', '', t, flags=re.IGNORECASE).strip()
        if self.config.get("add_episode_number", False):
            return f"{t} ตอนที่ {index}"
        return t

    def complete_truncated_with_ai(self, text: str) -> Optional[str]:
        """
        Uses Gemini AI to complete the last truncated/cut-off Thai word or phrase in a title.
        Example: 'สาวน้อยชาวประมงโดนอาแท้ๆพามาปล่อยเก' -> 'สาวน้อยชาวประมงโดนอาแท้ๆพามาปล่อยเกาะ'
        """
        if not text or len(text.strip()) < 4:
            return None

        # Check if text looks cut off (e.g. ends with Thai vowel, single consonant, or incomplete phrase)
        keys, models = self.get_api_keys()
        if not keys:
            return None

        try:
            from google import genai
            from google.genai import types
        except Exception:
            return None

        prompt = (
            f"ข้อความชื่อเรื่องละครสั้น/ซีรีส์ต่อไปนี้ถูกตัดคำขาดที่ท้ายประโยคเนื่องจากความยาวชื่อไฟล์ถูกตัด:\n"
            f"\"{text.strip()}\"\n\n"
            f"คำสั่ง:\n"
            f"1. ให้เติมคำที่ขาดหายไปต่อท้ายให้ประโยคสมบูรณ์และถูกต้องตามหลักภาษาไทยและบริบทของเรื่อง\n"
            f"2. ห้ามเปลี่ยนคำเดิมในประโยค ให้คงข้อความเดิมไว้ทั้งหมดและเติมเฉพาะคำ/พยางค์สุดท้ายที่ถูกตัดให้ครบถ้วน\n"
            f"3. ตอบกลับเฉพาะข้อความชื่อเรื่องที่สมบูรณ์แล้วเพียงบรรทัดเดียวเท่านั้น ห้ามมีคำอธิบาย เครื่องหมายคำพูด หรือข้อความอื่นใดทั้งสิ้น"
        )

        http_opts = types.HttpOptions(
            timeout=10000,
            retry_options=types.HttpRetryOptions(attempts=1)
        )

        for key in keys:
            try:
                client = genai.Client(api_key=key, http_options=http_opts)
            except Exception:
                continue

            for m in models:
                try:
                    resp = client.models.generate_content(
                        model=m,
                        contents=prompt
                    )
                    if resp and resp.text:
                        completed = resp.text.strip().strip('"\'')
                        # Sanity check: completed text must start with the original text (or original without last char)
                        if completed and len(completed) >= len(text) and completed != text:
                            # Verify it starts with at least 80% prefix of text
                            prefix = text[:max(4, len(text) - 4)]
                            if prefix in completed:
                                print(f"[CaptionGenerator] 🤖 AI Title Completion: '{text}' -> '{completed}'")
                                return completed
                except Exception as e:
                    err_s = str(e)
                    if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                        break
                    continue

        return None

    def get_api_keys(self) -> Tuple[List[str], List[str]]:
        """Returns list of API keys and ordered list of models for fallback"""
        raw_key = self.ai_config.get("api_key", "").strip()
        configured_model = self.ai_config.get("model", "gemini-3.5-flash-lite")

        # If empty, attempt to load from G:/PG/Auto flow ຂຽນຂ່າວ
        if not raw_key:
            from core.utils import load_external_gemini_key
            ext_key, ext_model = load_external_gemini_key()
            if ext_key:
                raw_key = ext_key
            if ext_model:
                configured_model = ext_model

        if configured_model:
            configured_model = configured_model.lower().strip().replace(" ", "-").replace("models/", "")

        keys = [k.strip() for k in raw_key.split(",") if k.strip()]

        # High-performance fallback model chain (gemini-3.5-flash-lite has high quota)
        model_chain = [
            "gemini-3.5-flash-lite",
            configured_model,
            "gemini-3.1-flash-lite",
            "gemini-3.6-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-3.8-flash",
            "gemini-3.7-flash"
        ]
        unique_models = []
        for m in model_chain:
            if m and m not in unique_models:
                unique_models.append(m)

        return keys, unique_models

    def generate_with_ai(self, cover_path: Optional[str] = None, story_hints: str = "", index: int = 1, content_type: str = "china_drama") -> Optional[Dict[str, str]]:
        """
        Uses Gemini AI (Vision if thumbnail available, or Text if image unavailable)
        to generate a viral, captivating title & caption in Thai language matching the Content Category.
        """
        keys, models = self.get_api_keys()
        if not keys:
            return None

        try:
            from google import genai
            from google.genai import types
            from PIL import Image
        except (ImportError, Exception) as e:
            print(f"[CaptionGenerator] ⚠️ Gemini SDK / PIL unavailable ({e}) -> Falling back to curated title pool.")
            return None

        image_obj = None
        if cover_path and os.path.exists(cover_path):
            try:
                image_obj = Image.open(cover_path)
            except Exception as e:
                print(f"[CaptionGenerator] Could not open cover thumbnail: {e}")

        hints_clean = story_hints.strip()
        has_story = self.is_meaningful_drama_hint(hints_clean)

        add_ep = self.config.get("add_episode_number", False)

        # -------------------------------------------------------------
        # Branch prompts based on content_type
        # -------------------------------------------------------------
        if content_type == "lao_girl_khaohom":
            prompt_core = (
                "CHARACTER & PERSONA: 'น้องข้าวหอม สาวขี้ดื้อ' (Nong Khao Hom - The Mischievous & Cute Lao Student Girl).\n"
                "- Persona: Fictional cute Lao high school / student girl (age 14-16), cheerful, playful, cheeky, sweet, charming, lovable.\n"
                "- Language: All titles and captions MUST BE IN THAI LANGUAGE (ภาษาไทย)!\n"
                "- Tone: น่ารัก สดใส ขี้เล่น ขี้อ้อน ปนกวนๆ สไตล์เด็กดื้อน่าเอ็นดู มีอีโมจิสดใส (✨ 💕 🌸 🍦 😝 💖 🎀)\n\n"
                "MANDATORY INSTRUCTIONS:\n"
                "1. Generate a viral, captivating, super cute Title in Thai language from the perspective of Nong Khao Hom or describing her cute moment.\n"
                "   Examples: 'วันนี้ดื้อได้มั้ยคะ ถ้าใจดีเดี๋ยวพาไปกินติม 🍦✨', 'หนูไม่ได้ดื้อนะ แค่ซนไปหน่อยเอง 😝💕', 'ส่งยิ้มหวานๆ ให้พี่ๆ วันนี้อย่าลืมยิ้มตอบหนูนะ 💖', 'สาวน้อยขี้ดื้อ แอบมาแจกความสดใสค่าา ✨'\n"
                "   DO NOT include episode numbers (ห้ามมีคำว่า ตอนที่, ep, part).\n"
                "2. Write an adorable, playful Caption in Thai language inviting viewers to Like, Share, follow, and comment.\n"
                "3. Include relevant hashtags (#น้องข้าวหอม #สาวขี้ดื้อ #สาวลาวน่ารัก #ความน่ารักสดใส #สาวนักเรียน #แจกความสดใส #reels #fyp).\n\n"
                "Respond ONLY with valid JSON in this exact structure, nothing else:\n"
                "{\n"
                '  "title": "[ชื่อเรื่องน่ารักสดใส สไตล์น้องข้าวหอม สาวขี้ดื้อ]",\n'
                '  "caption": "✨ [ชื่อเรื่อง]\\n\\n💖 [ข้อความแคปชั่นน่ารักๆ อ้อนๆ กวนๆ ชวนคุย]\\n📌 ฝากกด Like & Share และติดตามเป็นกำลังใจให้น้องข้าวหอมด้วยน้าา 💕\\n\\n[hashtags]"\n'
                "}"
            )
            vision_prompt = (
                "You are managing the Facebook Reels persona 'น้องข้าวหอม สาวขี้ดื้อ' (cute Lao student girl age 14-16).\n"
                "Analyze this video thumbnail frame depicting her cute moments or charms.\n\n"
                f"{prompt_core}"
            )
            text_prompt = (
                "You are managing the Facebook Reels persona 'น้องข้าวหอม สาวขี้ดื้อ' (cute Lao student girl age 14-16).\n\n"
                f"{prompt_core}"
            )
        elif has_story:
            if add_ep:
                prompt_core = (
                    f"ORIGINAL DRAMA TITLE / KEYWORDS FROM VIDEO: \"{hints_clean}\"\n\n"
                    "CRITICAL INSTRUCTIONS:\n"
                    f"1. Notice that the Original Title \"{hints_clean}\" is often cut off / incomplete at the end due to file truncation (e.g. 'ตื่นจากหลับมา 100 ปี ทวงสัญญา 4 ตระกู' was cut off from 'ตระกูลใหญ่', 'ก่อนเปิดตัวเป' was cut off from 'ก่อนเปิดตัวเป็นทายาทเศรษฐี', 'สุดแข็งแ' was cut off from 'สุดแข็งแกร่ง').\n"
                    f"2. You MUST prioritize and use this original story idea as the title! Complete any cut-off words or incomplete sentences so it forms a natural, grammatically correct, dramatic, and captivating title in Thai language (ภาษาไทย).\n"
                    f"3. Append 'ตอนที่ {index}' at the end of the title.\n"
                    "4. Write a dramatic, suspenseful Caption in Thai language with a story hook directly matching this exact storyline, call-to-action to Like & Share, and 6 hashtags (#หนังสั้นจีน #ซีรีส์จีน #ละครสั้น #chinaai #chinesedrama #reelsdrama).\n\n"
                    "Respond ONLY with valid JSON in this exact structure, nothing else:\n"
                    "{\n"
                    f'  "title": "[ชื่อเรื่องเดิมที่เติมเต็มประโยคให้สมบูรณ์และน่าติดตาม] ตอนที่ {index}",\n'
                    '  "caption": "🎬 [ชื่อเรื่องเดิมที่เติมเต็มสมบูรณ์แล้ว]\\n\\n🔥 [Story Hook ดราม่าเข้มข้นตรงกับเรื่องราว]\\n📌 ติดตามเรื่องใหม่ๆ ได้ทุกวัน อย่าลืมกด Like & Share เพื่อเป็นกำลังใจให้ด้วยนะครับ! ✨\\n\\n[hashtags]"\n'
                    "}"
                )
            else:
                prompt_core = (
                    f"ORIGINAL DRAMA TITLE / KEYWORDS FROM VIDEO: \"{hints_clean}\"\n\n"
                    "CRITICAL INSTRUCTIONS:\n"
                    f"1. Notice that the Original Title \"{hints_clean}\" is often cut off / incomplete at the end due to file truncation (e.g. 'ตื่นจากหลับมา 100 ปี ทวงสัญญา 4 ตระกู' was cut off from 'ตระกูลใหญ่', 'ก่อนเปิดตัวเป' was cut off from 'ก่อนเปิดตัวเป็นทายาทเศรษฐี', 'สุดแข็งแ' was cut off from 'สุดแข็งแกร่ง').\n"
                    f"2. You MUST prioritize and use this original story idea as the title! Complete any cut-off words or incomplete sentences so it forms a natural, grammatically correct, dramatic, and captivating title in Thai language (ภาษาไทย).\n"
                    "3. DO NOT include episode numbers (e.g. DO NOT write 'ตอนที่ 1', 'ตอน 1', 'EP 1', 'Part 1') because this video is a complete full movie / full episode (เต็มเรื่องจบ)!\n"
                    "4. Write a dramatic, suspenseful Caption in Thai language with a story hook directly matching this exact storyline, call-to-action to Like & Share, and 6 hashtags (#หนังสั้นจีน #ซีรีส์จีน #ละครสั้น #chinaai #chinesedrama #reelsdrama).\n\n"
                    "Respond ONLY with valid JSON in this exact structure, nothing else:\n"
                    "{\n"
                    '  "title": "[ชื่อเรื่องเดิมที่เติมเต็มประโยคให้สมบูรณ์และน่าติดตาม (ห้ามมีคำว่าตอนที่)]",\n'
                    '  "caption": "🎬 [ชื่อเรื่องเดิมที่เติมเต็มสมบูรณ์แล้ว]\\n\\n🔥 [Story Hook ดราม่าเข้มข้นตรงกับเรื่องราว]\\n📌 ติดตามเรื่องใหม่ๆ ได้ทุกวัน อย่าลืมกด Like & Share เพื่อเป็นกำลังใจให้ด้วยนะครับ! ✨\\n\\n[hashtags]"\n'
                    "}"
                )
        else:
            if add_ep:
                prompt_core = (
                    "Requirements:\n"
                    f"1. Generate a viral, click-worthy drama Title in Thai language (ภาษาไทย) for a Chinese AI mini-drama "
                    f"(topics: Billionaire/CEO in disguise, Revenge, Rebirth, War God, Royal Palace, or Secret Identity). Must end with 'ตอนที่ {index}'.\n"
                    "2. Write a dramatic, suspenseful Caption in Thai language with a story hook, call-to-action to Like & Share, and 6 hashtags (#หนังสั้นจีน #ซีรีส์จีน #ละครสั้น #chinaai #chinesedrama #reelsdrama).\n\n"
                    "Respond ONLY with valid JSON in this exact structure, nothing else:\n"
                    "{\n"
                    f'  "title": "ชื่อเรื่องสุดดราม่า ตอนที่ {index}",\n'
                    '  "caption": "🎬 [ชื่อเรื่อง]\\n\\n🔥 [Story Hook ดราม่าเข้มข้น]\\n📌 ติดตามเรื่องใหม่ๆ ได้ทุกวัน อย่าลืมกด Like & Share เพื่อเป็นกำลังใจให้ด้วยนะครับ! ✨\\n\\n[hashtags]"\n'
                    "}"
                )
            else:
                prompt_core = (
                    "Requirements:\n"
                    "1. Generate a viral, click-worthy drama Title in Thai language (ภาษาไทย) for a Chinese AI mini-drama "
                    "(topics: Billionaire/CEO in disguise, Revenge, Rebirth, War God, Royal Palace, or Secret Identity). "
                    "DO NOT include episode numbers (e.g. DO NOT write 'ตอนที่ 1', 'ตอน 1', 'EP 1', 'Part 1') because this is a complete full movie / full episode (เต็มเรื่องจบ).\n"
                    "2. Write a dramatic, suspenseful Caption in Thai language with a story hook, call-to-action to Like & Share, and 6 hashtags (#หนังสั้นจีน #ซีรีส์จีน #ละครสั้น #chinaai #chinesedrama #reelsdrama).\n\n"
                    "Respond ONLY with valid JSON in this exact structure, nothing else:\n"
                    "{\n"
                    '  "title": "ชื่อเรื่องสุดดราม่า (ห้ามมีคำว่าตอนที่)",\n'
                    '  "caption": "🎬 [ชื่อเรื่อง]\\n\\n🔥 [Story Hook ดราม่าเข้มข้น]\\n📌 ติดตามเรื่องใหม่ๆ ได้ทุกวัน อย่าลืมกด Like & Share เพื่อเป็นกำลังใจให้ด้วยนะครับ! ✨\\n\\n[hashtags]"\n'
                    "}"
                )

        if content_type != "lao_girl_khaohom":
            if has_story:
                vision_prompt = (
                    "You are an expert viral content creator specializing in Facebook Reels for Chinese AI Mini-Dramas.\n"
                    "MANDATORY TASK: You are given an original drama title that was truncated/cut off at the end.\n"
                    "You MUST base the Title on this original story and complete the cut-off words/sentence into a grammatically complete, exciting Thai title.\n"
                    "Use the video thumbnail frame to match the mood and scene, but the Title MUST be the completed version of the original drama title!\n\n"
                    f"{prompt_core}"
                )
            else:
                vision_prompt = (
                    "You are an expert viral content creator specializing in Facebook Reels for Chinese AI Mini-Dramas "
                    "(หนังสั้นจีน AI / ละครสั้นจีน / China AI Drama).\n"
                    "Analyze this video thumbnail frame from a China AI movie/series.\n\n"
                    f"{prompt_core}"
                )

            text_prompt = (
                "You are an expert viral content creator specializing in Facebook Reels for Chinese AI Mini-Dramas "
                "(หนังสั้นจีน AI / ละครสั้นจีน / China AI Drama).\n\n"
                f"{prompt_core}"
            )

        http_opts = types.HttpOptions(
            timeout=15000,
            retry_options=types.HttpRetryOptions(attempts=1)
        )

        # Determine optimal execution steps:
        # If original filename has a cut-off story title: prioritize Text to complete it with 100% fidelity.
        # If original filename has no story keywords: prioritize Vision to analyze scene and invent a title.
        steps = []
        if has_story and content_type != "lao_girl_khaohom":
            steps.append(("text", text_prompt, None))
            if image_obj:
                steps.append(("vision", vision_prompt, image_obj))
        else:
            if image_obj:
                steps.append(("vision", vision_prompt, image_obj))
            steps.append(("text", text_prompt, None))

        for step_name, prompt_txt, img in steps:
            for key in keys:
                try:
                    client = genai.Client(api_key=key, http_options=http_opts)
                except Exception:
                    continue

                for m in models:
                    try:
                        contents = [img, prompt_txt] if img else prompt_txt
                        response = client.models.generate_content(
                            model=m,
                            contents=contents
                        )
                        if response and response.text:
                            txt = response.text.strip()
                            match = re.search(r'\{.*\}', txt, re.DOTALL)
                            if match:
                                data = json.loads(match.group(0))
                                title = data.get("title", "").strip()
                                caption = data.get("caption", "").strip()
                                if title:
                                    if content_type == "lao_girl_khaohom":
                                        title = re.sub(r'(?:\s*ตอนที่\s*\d+|\s*ตอน\s*\d+|\s*ep\s*\d+|\s*part\s*\d+)+$', '', title, flags=re.IGNORECASE).strip()
                                        print(f"[CaptionGenerator] 🌸 AI {step_name.title()} Title ({m}) for Nong Khao Hom: {title}")
                                        return {"title": title, "caption": caption, "source": f"ai_{step_name}_{m}"}
                                    else:
                                        title = re.sub(r'(?:\s*ตอนที่\s*\d+|\s*ตอน\s*\d+|\s*ep\s*\d+|\s*part\s*\d+)+$', '', title, flags=re.IGNORECASE).strip()
                                        title = re.sub(r'^(?:ตอนที่\s*\d+\s*|ตอน\s*\d+\s*|ep\s*\d+\s*)[:\-–—\s]*', '', title, flags=re.IGNORECASE).strip()
                                        if self.config.get("add_episode_number", False):
                                            title = f"{title} ตอนที่ {index}"
                                        else:
                                            if caption:
                                                caption = re.sub(r'(🎬[^\n]+?)(?:\s*ตอนที่\s*\d+|\s*ตอน\s*\d+|\s*ep\s*\d+|\s*part\s*\d+)', r'\1', caption, flags=re.IGNORECASE)
                                                caption = caption.replace("ติดตามตอนใหม่ๆ", "ติดตามเรื่องใหม่ๆ").replace("เพื่อไม่พลาดตอนต่อไป", "เพื่อไม่พลาดเรื่องต่อไป")
                                        print(f"[CaptionGenerator] 🤖 AI {step_name.title()} Title ({m}): {title}")
                                        return {"title": title, "caption": caption, "source": f"ai_{step_name}_{m}"}
                    except Exception as e:
                        err_s = str(e)
                        if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                            # Quota is exhausted for this key, break immediately to try next key
                            break
                        continue

        return None

    def get_catchy_china_drama_title(self, index: int = 1) -> str:
        """Returns a captivating China AI movie title from curated pool (with episode number only if configured)"""
        idx = (index - 1) % len(self.CHINA_DRAMA_TITLES)
        base_title = self.CHINA_DRAMA_TITLES[idx]
        if self.config.get("add_episode_number", False):
            return f"{base_title} ตอนที่ {index}"
        return base_title

    def build_catchy_china_drama_caption(self, title: str, index: int = 1, custom_template: Optional[str] = None, custom_hashtag_pool: Optional[List[str]] = None) -> str:
        """Constructs a dramatic China AI movie caption with hooks and hashtags"""
        hook = random.choice(self.DRAMA_HOOKS)
        tags_list = self.get_hashtags(count=self.tags_count) if not custom_hashtag_pool else custom_hashtag_pool[:self.tags_count]
        tags = " ".join(tags_list)

        replacements = {
            "{title}": title,
            "{hook}": hook,
            "{tags}": tags,
            "{index}": str(index),
            "{date}": datetime.now().strftime("%Y-%m-%d"),
            "{time}": datetime.now().strftime("%H:%M")
        }

        tpl = custom_template or self.template
        caption = tpl
        for k, v in replacements.items():
            caption = caption.replace(k, v)

        if not self.config.get("add_episode_number", False):
            caption = caption.replace("ติดตามตอนใหม่ๆ", "ติดตามเรื่องใหม่ๆ").replace("เพื่อไม่พลาดตอนต่อไป", "เพื่อไม่พลาดเรื่องต่อไป")

        # Clean duplicate prefixes if template already had one
        caption = re.sub(r'(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)\s*(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)', r'\1', caption)
        return caption.strip()

    def get_catchy_khaohom_title(self, index: int = 1) -> str:
        """Returns a charming title from Nong Khao Hom curated pool"""
        idx = (index - 1) % len(self.KHAOHOM_TITLES)
        return self.KHAOHOM_TITLES[idx]

    def build_catchy_khaohom_caption(self, title: str, index: int = 1, custom_template: Optional[str] = None, custom_hashtag_pool: Optional[List[str]] = None) -> str:
        """Constructs an adorable caption for Nong Khao Hom"""
        hook = random.choice(self.KHAOHOM_HOOKS)
        preset = CONTENT_PRESETS.get("lao_girl_khaohom", {})
        tags_list = custom_hashtag_pool if custom_hashtag_pool else preset.get("default_tags", [])
        tags = " ".join(tags_list[:self.tags_count])

        replacements = {
            "{title}": title,
            "{hook}": hook,
            "{tags}": tags,
            "{index}": str(index),
            "{date}": datetime.now().strftime("%Y-%m-%d"),
            "{time}": datetime.now().strftime("%H:%M")
        }

        tpl = custom_template or preset.get("default_template")
        caption = tpl
        for k, v in replacements.items():
            caption = caption.replace(k, v)

        return caption.strip()

    @staticmethod
    def apply_title_prefix(title: str, prefix: Optional[str] = None) -> str:
        """
        Safely applies a prefix like '[เต็มเรื่อง]' in front of a title without duplicate nesting.
        """
        if not title:
            return ""
        clean_title = title.strip()
        if not prefix or not prefix.strip():
            return clean_title

        p = prefix.strip()
        # If title already starts with [เต็มเรื่อง], (เต็มเรื่อง), 【เต็มเรื่อง】, or เต็มเรื่อง
        if re.search(r'^(?:\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】|เต็มเรื่อง)', clean_title, re.IGNORECASE) or clean_title.startswith(p):
            return clean_title

        return f"{p} {clean_title}".strip()

    @staticmethod
    def read_companion_text_file(txt_path: str) -> Optional[str]:
        """
        Reads companion .txt file with multi-encoding fallback (UTF-8, UTF-8-BOM, CP874, TIS-620, Latin-1).
        """
        for enc in ["utf-8", "utf-8-sig", "cp874", "tis-620", "latin-1"]:
            try:
                with open(txt_path, "r", encoding=enc) as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception:
                pass
        return None

    def build_caption(self, video_path: str, index: int = 1, custom_template: Optional[str] = None, custom_hashtag_pool: Optional[List[str]] = None, title_prefix: Optional[str] = None, content_type: str = "china_drama", title_mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Builds title and full caption for a given video or photo file.
        Priority:
        1. Companion .txt file (e.g. clip1.txt or photo1.txt with user-specified caption details).
        2. Clean filename (if configured via title_mode == 'filename_clean').
        3. Gemini AI Vision + Text analysis matching Content Preset.
        4. Curated Pool fallback.
        """
        raw_name = os.path.splitext(os.path.basename(video_path))[0]
        actual_title_mode = title_mode or self.config.get("title_mode", "filename_clean")
        cover_path = None
        tpl = custom_template or self.template

        # 0. Companion .txt file check (e.g., photo1.txt for photo1.jpg or clip1.txt for clip1.mp4)
        txt_path = None
        try:
            from core.queue_manager import QueueManager
            txt_path = QueueManager.find_companion_text_file(video_path)
        except Exception:
            pass

        if txt_path and os.path.exists(txt_path):
            txt_content = self.read_companion_text_file(txt_path)
            if txt_content:
                lines = [line.strip() for line in txt_content.splitlines() if line.strip()]
                raw_title = lines[0] if lines else raw_name
                if raw_title.startswith("#"):
                    raw_title = raw_name
                if len(raw_title) > 100:
                    raw_title = raw_title[:97] + "..."

                final_title = self.apply_title_prefix(raw_title, title_prefix)

                tags_list = custom_hashtag_pool if custom_hashtag_pool else (
                    self.get_hashtags() if content_type != "lao_girl_khaohom" else CONTENT_PRESETS.get("lao_girl_khaohom", {}).get("default_tags", [])
                )
                tags_str = " ".join(tags_list[:self.tags_count])

                if "{title}" in txt_content or "{tags}" in txt_content:
                    final_caption = txt_content.replace("{title}", final_title).replace("{tags}", tags_str)
                elif "#" in txt_content:
                    final_caption = txt_content
                else:
                    final_caption = f"{txt_content}\n\n{tags_str}"

                final_caption = re.sub(r'(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)\s*(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)', r'\1', final_caption)

                print(f"[CaptionGenerator] 📄 Loaded Title & Caption from companion file '{os.path.basename(txt_path)}'")
                return {
                    "title": final_title,
                    "caption": final_caption.strip(),
                    "source": "companion_txt_file",
                    "cover_path": None
                }

        # If user explicitly configured 'filename_clean' (use clean title extracted from filename)
        if actual_title_mode == "filename_clean":
            clean_title = self.clean_filename(video_path)
            if clean_title and len(clean_title) >= 3:
                # Also run through truncation completion (regex + Gemini AI)
                clean_title = self.complete_truncated_story_title(clean_title, index=index)

                if self.config.get("add_episode_number", False):
                    if not re.search(r'(?i)\b(ep|episode|part|ตอน|ຕອນ)\b', clean_title):
                        clean_title = f"{clean_title} ตอนที่ {index}"
                else:
                    clean_title = re.sub(r'(?:\s*ตอนที่\s*\d+|\s*ตอน\s*\d+|\s*ep\s*\d+|\s*part\s*\d+)+$', '', clean_title, flags=re.IGNORECASE).strip()

                clean_title = self.apply_title_prefix(clean_title, title_prefix)

                tags_list = self.get_hashtags() if not custom_hashtag_pool else custom_hashtag_pool[:self.tags_count]
                tags_str = " ".join(tags_list)
                caption = tpl.replace("{title}", clean_title)\
                             .replace("{filename}", raw_name)\
                             .replace("{tags}", tags_str)\
                             .replace("{index}", str(index))\
                             .replace("{date}", datetime.now().strftime("%Y-%m-%d"))\
                             .replace("{time}", datetime.now().strftime("%H:%M"))
                if not self.config.get("add_episode_number", False):
                    caption = caption.replace("ติดตามตอนใหม่ๆ", "ติดตามเรื่องใหม่ๆ").replace("เพื่อไม่พลาดตอนต่อไป", "เพื่อไม่พลาดเรื่องต่อไป")
                caption = re.sub(r'(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)\s*(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)', r'\1', caption)
                print(f"[CaptionGenerator] 📁 [Filename Mode] Extracted Clean Title from filename: '{clean_title}'")
                return {
                    "title": clean_title,
                    "caption": caption.strip(),
                    "source": "filename",
                    "cover_path": None
                }
            else:
                print(f"[CaptionGenerator] ⚠️ [Filename Mode] Filename '{raw_name[:50]}' had no extractable story title -> falling back to AI / curated pool.")

        # Extract story hints from video filename
        story_hints = self.extract_story_hints(raw_name)

        # Extract cover frame & generate via Gemini AI
        if os.path.exists(video_path):
            cover_path = self.extract_cover_frame(video_path)

        # 1. Check Local AI Persistent Cache (Credit Saver - 0 API cost)
        cached = self.get_cached_ai_result(video_path)
        if cached and cached.get("title"):
            cached_title = self.apply_title_prefix(cached["title"], title_prefix)
            cached_caption = cached.get("caption", "")
            print(f"[CaptionGenerator] ⚡ [Credit Saver] Loaded Title & Caption from local AI Cache: '{cached_title}' (Zero API calls)")
            return {
                "title": cached_title,
                "caption": cached_caption,
                "source": "ai_persistent_cache",
                "cover_path": cover_path
            }

        # 2. Try Gemini AI (Vision + Text Fallback)
        if self.ai_config.get("enabled", True):
            ep_label = f" (Episode {index})" if self.config.get("add_episode_number", False) else ""
            print(f"[CaptionGenerator] 🤖 Requesting Gemini AI Title for '{raw_name[:40]}...'{ep_label} (Category: {content_type})...")
            ai_result = self.generate_with_ai(cover_path=cover_path, story_hints=story_hints, index=index, content_type=content_type)
            if ai_result and ai_result.get("title"):
                ai_title = self.apply_title_prefix(ai_result["title"], title_prefix)
                final_caption = ai_result["caption"]
                if custom_template:
                    tags_list = self.get_hashtags() if not custom_hashtag_pool else custom_hashtag_pool[:self.tags_count]
                    tags_str = " ".join(tags_list)
                    final_caption = custom_template.replace("{title}", ai_title)\
                                                   .replace("{filename}", raw_name)\
                                                   .replace("{tags}", tags_str)\
                                                   .replace("{index}", str(index))\
                                                   .replace("{date}", datetime.now().strftime("%Y-%m-%d"))\
                                                   .replace("{time}", datetime.now().strftime("%H:%M"))
                else:
                    if title_prefix and not re.search(r'^(?:\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|เต็มเรื่อง)', final_caption):
                        final_caption = re.sub(r'(🎬\s*|✨\s*)(.+)', rf'\1{title_prefix.strip()} \2', final_caption, count=1)
                
                final_caption = re.sub(r'(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)\s*(\[เต็มเรื่อง\]|\(เต็มเรื่อง\)|【เต็มเรื่อง】)', r'\1', final_caption)

                # Persist to local AI cache to avoid future credit usage
                self.store_cached_ai_result(video_path, ai_title, final_caption, source=ai_result.get("source", "gemini_ai"))

                # Write companion text file beside media if directory is writable
                try:
                    txt_companion = os.path.splitext(video_path)[0] + ".txt"
                    if not os.path.exists(txt_companion):
                        with open(txt_companion, "w", encoding="utf-8") as tf:
                            tf.write(f"{ai_title}\n\n{final_caption}")
                        print(f"[CaptionGenerator] 💾 [Credit Saver] Created companion text file: '{os.path.basename(txt_companion)}'")
                except Exception:
                    pass

                return {
                    "title": ai_title,
                    "caption": final_caption.strip(),
                    "source": ai_result.get("source", "gemini_ai"),
                    "cover_path": cover_path
                }

        # 2. Final Fallback if AI unavailable:
        if content_type == "lao_girl_khaohom":
            k_title = self.get_catchy_khaohom_title(index=index)
            k_title = self.apply_title_prefix(k_title, title_prefix)
            print(f"[CaptionGenerator] 🌸 Applied Curated Nong Khao Hom Title: {k_title}")
            return {
                "title": k_title,
                "caption": self.build_catchy_khaohom_caption(k_title, index=index, custom_template=custom_template, custom_hashtag_pool=custom_hashtag_pool),
                "source": "curated_khaohom_pool",
                "cover_path": cover_path
            }

        if story_hints and self.is_meaningful_drama_hint(story_hints):
            drama_title = self.complete_truncated_story_title(story_hints, index=index)
            print(f"[CaptionGenerator] 🎬 Completed Truncated Drama Title: {drama_title}")
        else:
            drama_title = self.get_catchy_china_drama_title(index=index)
            print(f"[CaptionGenerator] 🎬 Applied Curated China AI Drama Title: {drama_title}")

        drama_title = self.apply_title_prefix(drama_title, title_prefix)

        return {
            "title": drama_title,
            "caption": self.build_catchy_china_drama_caption(drama_title, index=index, custom_template=custom_template, custom_hashtag_pool=custom_hashtag_pool),
            "source": "curated_drama_pool",
            "cover_path": cover_path
        }
