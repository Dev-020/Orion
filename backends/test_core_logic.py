import logging
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock dependencies before import
sys.modules['main_utils'] = MagicMock()
sys.modules['main_utils.config'] = MagicMock()
sys.modules['main_utils.main_functions'] = MagicMock()
sys.modules['main_utils.chat_object'] = MagicMock()
sys.modules['main_utils.file_manager'] = MagicMock()
sys.modules['system_utils'] = MagicMock()
sys.modules['system_utils.orion_replay'] = MagicMock()
sys.modules['system_utils.orion_tts'] = MagicMock()
sys.modules['agents'] = MagicMock()
sys.modules['agents.file_processing_agent'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.genai'] = MagicMock()
sys.modules['ollama'] = MagicMock()
sys.modules['sklearn'] = MagicMock() # Often imported by embedding_utils

# Import the target file
# We need to use sys path hack if running from backends/
import os
sys.path.append(os.getcwd())
try:
    from orion_core_lite import OrionLiteCore
except ImportError:
    # Try importing directly if we are in the folder
    import orion_core_lite

# Test Class
class TestStreamLogic(unittest.TestCase):
    def setUp(self):
        # Mock config
        self.config_patch = patch('orion_core_lite.config')
        self.mock_config = self.config_patch.start()
        self.mock_config.BACKEND = "ollama"
        self.mock_config.THINKING_SUPPORT = True
        self.mock_config.VOICE = False
        
        # Instantiate Core with mocks
        self.core = OrionLiteCore()
        self.core.client = MagicMock()
        self.core.chat = MagicMock()
        self.core.local_model = "gemma2"
        self.core.backend = "ollama"
        self.core.tools = []

    def tearDown(self):
        self.config_patch.stop()

    def test_thought_promotion(self):
        print("--- Testing Thought Promotion ---")
        
        # Mock the client.chat stream to yield thoughts but NO content
        mock_chunks = [
            {'message': {'thinking': 'This is a thought.'}},
            {'message': {'thinking': ' Ideally this is the answer.'}},
            {'message': {'content': None}} # Empty content
        ]
        self.core.client.chat.return_value = mock_chunks

        # Call _generate_stream_response
        generator = self.core._generate_stream_response(
            contents_to_send=[], data_envelope={}, session_id="test", 
            user_id="u1", user_name="User", user_prompt="hi", 
            attachments_for_db=[], context_ids_for_db=[], user_content_for_db={}
        )

        results = list(generator)
        
        # Verify tokens
        # Expect: 
        # 1. Thought token 1
        # 2. Thought token 2
        # 3. Promoted Content Token (The fix!)
        # 4. Done token
        
        found_promotion = False
        for packet in results:
            print(f"Packet: {packet}")
            if packet.get('type') == 'token' and "This is a thought." in packet.get('content', ''):
                found_promotion = True
        
        self.assertTrue(found_promotion, "Failed to find promoted content from thoughts!")

if __name__ == '__main__':
    unittest.main()
