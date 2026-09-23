import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from core.queue_manager import QueueManager
from core.caption_generator import CaptionGenerator
from core.engine import ReelUploadEngine

with open('config.json', 'r', encoding='utf-8') as f:
    cfg = json.load(f)

print('=== 1. Checking Config Groups ===')
groups = cfg.get('page_groups', [])
print(f'Total groups configured: {len(groups)}')
for g in groups:
    print(f"Group: {g.get('group_name')} | Folder: {g.get('video_folder')} | Pages: {len(g.get('pages', []))}")

print('\n=== 2. Testing QueueManager multi-folder support ===')
qm = QueueManager(cfg)
stats1 = qm.get_stats()
print(f'Queue stats (default): {stats1}')

print('\n=== 3. Testing CaptionGenerator custom template & hashtags ===')
cg = CaptionGenerator(cfg)
custom_tpl = "TEST TITLE: {title}\nTEST TAGS: {tags}"
custom_tags = ["#CustomTag1", "#CustomTag2"]
res = cg.build_catchy_china_drama_caption("ทดสอบเรื่องใหม่", index=1, custom_template=custom_tpl, custom_hashtag_pool=custom_tags)
print('Generated Caption Preview:')
print(res)
assert "#CustomTag1" in res, "Custom tag missing"

print('\n=== 4. Testing Engine _get_execution_groups ===')
engine = ReelUploadEngine(cfg)
exec_groups = engine._get_execution_groups()
print(f'Engine execution groups: {len(exec_groups)}')
assert len(exec_groups) == 2, "Should have 2 execution groups"
print('\n=== 5. Testing Title Prefix [เต็มเรื่อง] for Group 1 vs Group 2 ===')
# Unit test apply_title_prefix
t1 = cg.apply_title_prefix("มหาเศรษฐีอันดับ 1", "[เต็มเรื่อง] ")
assert t1 == "[เต็มเรื่อง] มหาเศรษฐีอันดับ 1", f"Expected '[เต็มเรื่อง] มหาเศรษฐีอันดับ 1', got '{t1}'"

t2 = cg.apply_title_prefix("[เต็มเรื่อง] มหาเศรษฐีอันดับ 1", "[เต็มเรื่อง] ")
assert t2 == "[เต็มเรื่อง] มหาเศรษฐีอันดับ 1", f"Expected no duplicate, got '{t2}'"

t3 = cg.apply_title_prefix("(เต็มเรื่อง) มหาเศรษฐีอันดับ 1", "[เต็มเรื่อง] ")
assert t3 == "(เต็มเรื่อง) มหาเศรษฐีอันดับ 1", f"Expected no duplicate, got '{t3}'"

t4 = cg.apply_title_prefix("คอนเทนต์ทั่วไป", "")
assert t4 == "คอนเทนต์ทั่วไป", f"Expected unchanged, got '{t4}'"

# Group 1 build_caption verification
g1 = groups[0]
g1_prefix = g1.get("title_prefix", "[เต็มเรื่อง] ")
g1_tpl = g1.get("caption_template")
g1_tags = g1.get("hashtag_pool")

dummy_video = "tests/dummy_sample_movie.mp4"
cap_g1 = cg.build_caption(dummy_video, index=1, custom_template=g1_tpl, custom_hashtag_pool=g1_tags, title_prefix=g1_prefix)
print(f"Group 1 Title: {cap_g1['title']}")
print(f"Group 1 Caption preview:\n{cap_g1['caption'][:120]}...")
assert "[เต็มเรื่อง]" in cap_g1['title'], f"Group 1 title must have [เต็มเรื่อง]: {cap_g1['title']}"
assert "[เต็มเรื่อง]" in cap_g1['caption'], f"Group 1 caption must have [เต็มเรื่อง]: {cap_g1['caption']}"

# Group 2 build_caption verification (dedicated page, no full movie prefix, Nong Khao Hom category)
g2 = groups[1]
g2_prefix = g2.get("title_prefix", "")
g2_tpl = g2.get("caption_template")
g2_tags = g2.get("hashtag_pool")
g2_cat = g2.get("content_type", "lao_girl_khaohom")
cap_g2 = cg.build_caption(dummy_video, index=1, custom_template=g2_tpl, custom_hashtag_pool=g2_tags, title_prefix=g2_prefix, content_type=g2_cat)
print(f"\nGroup 2 Title: {cap_g2['title']}")
print(f"Group 2 Caption preview:\n{cap_g2['caption'][:150]}...")
assert not cap_g2['title'].startswith("[เต็มเรื่อง]"), f"Group 2 title should not start with [เต็มเรื่อง]: {cap_g2['title']}"
assert "น้องข้าวหอม" in cap_g2['caption'], f"Group 2 caption should mention น้องข้าวหอม: {cap_g2['caption']}"

print('\n=== 6. Testing CONTENT_PRESETS Registry & Fallback Pool ===')
from core.caption_generator import CONTENT_PRESETS
assert "china_drama" in CONTENT_PRESETS, "Missing china_drama preset"
assert "lao_girl_khaohom" in CONTENT_PRESETS, "Missing lao_girl_khaohom preset"

k_title = cg.get_catchy_khaohom_title(index=1)
print(f"Nong Khao Hom Curated Title 1: {k_title}")
assert len(k_title) > 5, "Curated title is too short"
assert "ตอนที่" not in k_title, "Nong Khao Hom should not have episode number"

print('\n=== 7. Testing Priority Immediate for Nong Khao Hom ===')
ded_group = [g for g in exec_groups if g.get("group_id") == "group_dedicated_1page"][0]
assert ded_group.get("priority") == "immediate", f"Expected priority 'immediate', got {ded_group.get('priority')}"
print(f"Dedicated group priority verified: {ded_group.get('priority')}")

print('\nALL COMPONENT LOGIC CHECKS PASSED!')
