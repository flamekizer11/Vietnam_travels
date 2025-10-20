# tests/test_embed.py
# Unit tests for embed.py

import unittest
from unittest.mock import patch, MagicMock
from embed import embed_text, embed_texts, get_text_hash

class TestEmbed(unittest.TestCase):

    @patch('embed.client')
    def test_embed_text(self, mock_client):
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock()]
        mock_resp.data[0].embedding = [0.1, 0.2, 0.3]
        mock_client.embeddings.create.return_value = mock_resp

        result = embed_text("test text", use_cache=False)
        self.assertEqual(result, [0.1, 0.2, 0.3])
        mock_client.embeddings.create.assert_called_once()

    def test_get_text_hash(self):
        hash1 = get_text_hash("hello")
        hash2 = get_text_hash("hello")
        self.assertEqual(hash1, hash2)
        hash3 = get_text_hash("world")
        self.assertNotEqual(hash1, hash3)

if __name__ == '__main__':
    unittest.main()