from google.genai import types
import inspect

print("Attributes of GenerateContentConfig:")
for name, value in inspect.getmembers(types.GenerateContentConfig):
    if not name.startswith('_'):
        print(name)

print("\nAttributes of FunctionCallingConfig:")
try:
    for name, value in inspect.getmembers(types.FunctionCallingConfig):
        if not name.startswith('_'):
            print(name)
except:
    print("FunctionCallingConfig not found or inspection failed")
