import re
import json

text_stream = """
Thinking process...
< | tool_calls_begin | > < | tool_call_begin | >search_web< | tool_sep | >{"query": "latest league of legends champion", "smart_filter": true}< | tool_call_end | > < | tool_calls_end | >
"""

def parse_tool_calls(text):
    tool_calls = []
    # Pattern to capture multiple tool calls
    # Looks for content between tool_call_begin and tool_call_end
    # Inside that: name, separator, args
    
    # Regex is tricky with streams, but let's test a static parser first
    pattern = r"< \| tool_call_begin \| >(.*?)< \| tool_sep \| >(.*?)< \| tool_call_end \| >"
    matches = re.findall(pattern, text, re.DOTALL)
    
    for name, args_json in matches:
        try:
            name = name.strip()
            args = json.loads(args_json.strip())
            tool_calls.append({
                "function": {
                    "name": name,
                    "arguments": args
                },
                "id": "call_mock_id",
                "type": "function"
            })
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON for {name}: {e}")
            
    return tool_calls

print("--- Testing Parse ---")
results = parse_tool_calls(text_stream)
print(json.dumps(results, indent=2))
