import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Adjust path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKENDS_DIR = os.path.join(PROJECT_ROOT, 'backends')
sys.path.append(PROJECT_ROOT)
sys.path.append(BACKENDS_DIR)

from backends.orion_core_lite import OrionLiteCore
from backends.main_utils import config

class TestOllamaRateLimit(unittest.TestCase):
    def setUp(self):
        config.BACKEND = "ollama"
        config.THINKING_SUPPORT = False
        
        self.mock_funcs = MagicMock()
        self.mock_funcs.__all__ = ['dummy_tool']
        def dummy_tool(x): return f"Processed {x}"
        self.mock_funcs.dummy_tool = dummy_tool
        
        self.funcs_patcher = patch('backends.orion_core_lite.functions', self.mock_funcs)
        self.funcs_patcher.start()
        
        self.core = OrionLiteCore()
        self.core.client = MagicMock()
        
    def tearDown(self):
        self.funcs_patcher.stop()

    def test_rate_limit(self):
        print("\n--- Testing Tool Rate Limit (Max 5) ---")
        
        # Tool Call Chunk
        chunk_tool = {'message': {'role': 'assistant', 'tool_calls': [{'function': {'name': 'dummy_tool', 'arguments': {'x': 'val'}}}]}}
        # Final Response Chunk
        chunk_final = {'message': {'role': 'assistant', 'content': 'Limit Reached, stopping.'}}
        
        # Side effect to return tool calls 6 times, then final
        # 0, 1, 2, 3, 4 -> Tool Executed
        # 5 -> Tool Requested -> BLOCKED (Error fed back)
        # 6 -> Model sees error -> Final Response
        
        def chat_side_effect(**kwargs):
            messages = kwargs['messages']
            last_msg = messages[-1]
            
            # Count how many tool results are in history to determine "Turn"
            tool_results = [m for m in messages if m['role'] == 'tool']
            turn_count = len(tool_results)
            
            print(f"  [MockChat] History has {turn_count} tool results.")
            
            if turn_count < 6:
                print(f"  [MockChat] Generating Tool Request (Turn {turn_count})")
                yield chunk_tool
            else:
                print(f"  [MockChat] Generating Final Response (Turn {turn_count})")
                yield chunk_final

        self.core.client.chat.side_effect = chat_side_effect
        
        # Run
        gen = self.core._generate_stream_response(
            contents_to_send=[MagicMock(role='user', parts=[MagicMock(text='Spam tools')])],
            data_envelope={'user_prompt': 'Spam tools', 'system_notifications': []},
            session_id='test', user_id='test', user_name='test', user_prompt='test',
            attachments_for_db=[], context_ids_for_db=[], user_content_for_db={}
        )
        
        # Drain generator
        for _ in gen: pass
        
        # Verification
        # 1. The loop should have run 7 times (6 tool reqs + 1 final)
        print(f"  [Test] Chat Call Count: {self.core.client.chat.call_count}")
        # Note: logic calls chat, then processes.
        # It should call chat 7 times.
        
        # 2. Check if the LAST tool result in history is the System Error
        # We can't easily access the internal 'ollama_messages' list of the method since it's local.
        # But we can check the 'new_tool_turns' if we could return it, but _generate yields.
        # However, we can check if `_execute_safe` was called only 5 times, not 6.
        
        # We need to spy on `_execute_safe`?
        # self.tool_map['dummy_tool'] is the mock.
        # OrionLiteCore copies it to self.tool_map.
        # Check call count of the tool.
        
        real_tool = self.core.tool_map['dummy_tool']
        # Depending on how MagicMock copied it.
        # 'dummy_tool' function defined in setUp is NOT a mock, it's a real function.
        # Let's wrap it.
        
        pass

    def test_run_verify_logic(self):
        # Re-implementing verification logic cleanly
        self.core.tool_map['dummy_tool'] = MagicMock(return_value="OK")
        
        chunk_tool = {'message': {'role': 'assistant', 'tool_calls': [{'function': {'name': 'dummy_tool', 'arguments': {'x': 'val'}}}]}}
        chunk_final = {'message': {'role': 'assistant', 'content': 'Done.'}}
        
        # We need to simulate the chat responses exactly
        # 1. User -> Chat -> ToolReq1
        # 2. ToolRes1 -> Chat -> ToolReq2
        # ...
        # 6. ToolRes5 -> Chat -> ToolReq6 (THIS IS THE BLOCKED ONE)
        # 7. ToolResError -> Chat -> Final
        
        outputs = [
            chunk_tool, # 1
            chunk_tool, # 2
            chunk_tool, # 3
            chunk_tool, # 4
            chunk_tool, # 5
            chunk_tool, # 6 (Should be blocked)
            chunk_final # 7
        ]
        
        def side_effect(*args, **kwargs):
            if outputs:
                yield outputs.pop(0)
            else:
                yield chunk_final
        
        self.core.client.chat.side_effect = side_effect
        
        gen = self.core._generate_stream_response(
            contents_to_send=[MagicMock(role='user', parts=[MagicMock(text='test')])], # valid object
            data_envelope={'user_prompt': 'test', 'system_notifications': []},
            session_id='t', user_id='u', user_name='n', user_prompt='p',
            attachments_for_db=[], context_ids_for_db=[], user_content_for_db={}
        )
        
        for _ in gen: pass
        
        # CHECK: Tool should be called exactly 5 times.
        print(f"Tool execution count: {self.core.tool_map['dummy_tool'].call_count}")
        self.assertEqual(self.core.tool_map['dummy_tool'].call_count, 5, "Tool should be executed exactly 5 times")

if __name__ == '__main__':
    unittest.main()
