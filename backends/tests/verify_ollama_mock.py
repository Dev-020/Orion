import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Adjust path to import backends
# Add 'Orion' and 'Orion/backends' to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKENDS_DIR = os.path.join(PROJECT_ROOT, 'backends')
sys.path.append(PROJECT_ROOT)
sys.path.append(BACKENDS_DIR)

from backends.orion_core_lite import OrionLiteCore
from backends.main_utils import config

class TestOllamaTools(unittest.TestCase):
    def setUp(self):
        # Force Ollama backend
        config.BACKEND = "ollama"
        config.THINKING_SUPPORT = True
        
        # Mock main functions to avoid real imports/DB
        self.mock_funcs = MagicMock()
        self.mock_funcs.__all__ = ['dummy_tool']
        def dummy_tool(x):
            return f"Processed {x}"
        self.mock_funcs.dummy_tool = dummy_tool
        
        # Patch modules
        self.funcs_patcher = patch('backends.orion_core_lite.functions', self.mock_funcs)
        self.funcs_patcher.start()
        
        # Initialize Core
        self.core = OrionLiteCore()
        
        # Mock Client
        self.core.client = MagicMock()
        
    def tearDown(self):
        self.funcs_patcher.stop()

    def test_streaming_tool_loop(self):
        print("\n--- Testing Streaming Tool Loop ---")
        
        # define iterators for the two turns
        
        # Turn 1: Thoughts + Tool Call
        chunk1_thinking = {'message': {'role': 'assistant', 'thinking': 'I should use a tool.'}}
        chunk2_tool = {'message': {'role': 'assistant', 'tool_calls': [{'function': {'name': 'dummy_tool', 'arguments': {'x': 'data'}}}]}}
        
        # Turn 2: Final Response
        chunk3_content = {'message': {'role': 'assistant', 'content': 'Result found.'}}
        
        # Mock chat to return different streams based on calls
        # We use a side_effect generator
        def chat_side_effect(**kwargs):
            messages = kwargs['messages']
            last_msg = messages[-1]
            
            # If the last message is from the user (or system), it's the first turn
            if last_msg['role'] == 'user':
                print("  -> Simulating Model Turn 1 (Tool Call)")
                yield chunk1_thinking
                yield chunk2_tool
                
            # If the last message is a TOOL result, it's the second turn
            elif last_msg['role'] == 'tool':
                print("  -> Simulating Model Turn 2 (Final Response)")
                yield chunk3_content
                
        self.core.client.chat.side_effect = chat_side_effect
        
        # Run process_prompt
        # We mock prepare specific data to skip complex history logic
        # But process_prompt calls internal helpers.
        # Let's call _generate_stream_response directly to isolate logic
        
        gen = self.core._generate_stream_response(
            contents_to_send=[MagicMock(role='user', parts=[MagicMock(text='Run dummy')])],
            data_envelope={'user_prompt': 'Run dummy'},
            session_id='test_session',
            user_id='test_user',
            user_name='Tester',
            user_prompt='Run dummy',
            attachments_for_db=[],
            context_ids_for_db=[],
            user_content_for_db={}
        )
        
        output_types = []
        for packet in gen:
            print(f"  Received: {packet}")
            output_types.append(packet.get('type'))
            
        # Assertions
        self.assertIn('thought', output_types)
        self.assertIn('token', output_types)
        self.assertIn('done', output_types)
        
        # Verify Tool Execution
        # Check if dummy_tool was executed
        # Since we mocked self.mock_funcs.dummy_tool but OrionLiteCore copies it to self.tool_map...
        # Wait, OrionLiteCore._load_tools imports from the mocked `functions` module.
        # So self.tool_map['dummy_tool'] should be our dummy_tool.
        
        # Check if chat was called twice
        self.assertEqual(self.core.client.chat.call_count, 2)
        print("  -> Tool loop verified successfully.")

if __name__ == '__main__':
    unittest.main()
