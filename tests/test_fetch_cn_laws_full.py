"""fetch_cn_laws_full 纯函数测试（无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_cn_laws_full as cn  # noqa: E402

ARTS = ("第一条 为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，"
        "根据宪法，制定本法。\n第二条 自然人的个人信息受法律保护。\n")
# 21 条起(阈值 20),便于完整性校验通过
ARTS += "\n".join(
    f"第{n}条 本条为测试占位条文,内容涉及个人信息处理规则的相应部分。"
    for n in ["三", "四", "五", "六", "七", "八", "九", "十",
              "十一", "十二", "十三", "十四", "十五", "十六", "十七",
              "十八", "十九", "二十", "二十一", "二十二", "二十三",
              "二十四", "二十五"])
ARTS += "\n第二十六条（末条）本法自2021年11月1日起施行。"

META = {"url": "http://x/", "title": "中华人民共和国测试法",
        "first": "为了保护个人信息权益", "last_art": "第二十六条"}


def page(body: str, prefix: str = "站点导航 头条 新闻", suffix: str = "来源：测试\n分享：") -> str:
    return (f"<html><body><div>{prefix}</div><div class='TRS_Editor'>"
            f"<p>{body}</p></div><div>{suffix}</div></body></html>")


class TestConvertLaw(unittest.TestCase):
    def test_full_law_passes(self):
        doc = cn.convert_law(page(ARTS), META)
        self.assertIsNotNone(doc)
        self.assertTrue(doc.startswith("中华人民共和国测试法（全文）"))
        self.assertIn("第一条", doc)
        self.assertIn("第二十六条（末条）", doc)
        self.assertNotIn("来源：", doc)          # 尾部导航剔除
        self.assertNotIn("站点导航", doc)        # 头部导航剔除

    def test_abridged_page_rejected(self):
        # 末条缺失(节选级) → None
        abridged = ARTS.replace("第二十六条（末条）", "") + "\n更多阅读 推荐"
        self.assertIsNone(cn.convert_law(page(abridged), META))

    def test_first_article_missing_rejected(self):
        self.assertIsNone(cn.convert_law(page("欢迎来到官网首页"), META))

    def test_too_few_articles_rejected(self):
        short = "第一条 为了保护个人信息权益，规范个人信息处理活动。\n第二十六条（末条）施行。"
        self.assertIsNone(cn.convert_law(page(short), META))

    def test_anchor_first_kw_in_body(self):
        # 首条关键词不在正文中 → None
        m2 = dict(META, first="完全不存在的关键词")
        self.assertIsNone(cn.convert_law(page(ARTS), m2))


if __name__ == "__main__":
    unittest.main()
