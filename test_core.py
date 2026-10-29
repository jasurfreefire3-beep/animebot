import os
import unittest
from database import Database
from utils.parser import extract_episode_number

class TestAnimeBotCore(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_anime.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = Database(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_caption_parser(self):
        cases = [
            ("1-qism", 1),
            ("1 - qism", 1),
            ("Qora Klever 12-qism", 12),
            ("Naruto 50 qism", 50),
            ("Episode 12", 12),
            ("Ep 12", 12),
            ("ep. 03", 3),
            ("14 ep", 14),
            ("5-epizod", 5),
            ("12-seriya", 12),
            ("серия 170", 170),
            ("15 / 170", 15),
            ("Qora Klever 05", 5),
        ]
        for caption, expected in cases:
            res = extract_episode_number(caption)
            self.assertEqual(res, expected, f"Failed for '{caption}': expected {expected}, got {res}")

    def test_database_and_episodes(self):
        # Anime qo'shish
        anime_id = self.db.add_anime(
            title="Qora Klever / Black Clover",
            genres="Jangari • Sarguzasht • Fantaziya",
            media_type="video",
            media_file_id="BAACAgIAAxkBAAE..."
        )
        self.assertGreater(anime_id, 0)

        # Epizod qo'shilmagan holatda
        self.assertEqual(self.db.get_episode_count(anime_id), 0)

        # 3 ta epizod qo'shish
        self.db.add_or_update_episode(anime_id, 1, "video_id_1", "1-qism")
        self.db.add_or_update_episode(anime_id, 2, "video_id_2", "2-qism")
        self.db.add_or_update_episode(anime_id, 3, "video_id_3", "3-qism")

        # Epizodlar soni 3 ta bo'lishi kerak
        self.assertEqual(self.db.get_episode_count(anime_id), 3)
        self.assertEqual(self.db.get_max_episode_number(anime_id), 3)

        # 2-qismni olish
        ep2 = self.db.get_episode(anime_id, 2)
        self.assertIsNotNone(ep2)
        self.assertEqual(ep2["video_file_id"], "video_id_2")

        # Ko'rishlarni oshirish
        self.db.increment_views(anime_id)
        anime = self.db.get_anime(anime_id)
        self.assertEqual(anime["views"], 1)

if __name__ == "__main__":
    unittest.main()

