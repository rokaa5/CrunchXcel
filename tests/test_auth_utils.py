import unittest
from auth_utils import hash_password, verify_password

class PasswordHashTests(unittest.TestCase):
    def test_password_round_trip(self):
        stored = hash_password("admin")
        self.assertNotEqual(stored, "admin")
        self.assertTrue(verify_password("admin", stored))
        self.assertFalse(verify_password("wrong", stored))

    def test_salts_are_unique(self):
        self.assertNotEqual(hash_password("staff"), hash_password("staff"))

    def test_invalid_hash(self):
        self.assertFalse(verify_password("staff", "not-a-valid-hash"))

if __name__ == "__main__":
    unittest.main()
