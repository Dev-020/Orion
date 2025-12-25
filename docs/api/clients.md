# Client SDKs

Orion doesn't just offer raw endpoints; it provides "SDKs" (Software Development Kits) to make connecting easier.

## 1. Python SDK (`orion_client.py`)
**Location**: `backends/orion_client.py`
**Used By**: Discord Bot, Desktop GUI.

This class mimics the `OrionCore` methods. It handles the request serialization and response parsing for you.

### Example Usage
```python
from backends.orion_client import OrionClient

client = OrionClient(base_url="http://localhost:8000")

# Sync Generator
for chunk in client.process_prompt(
    session_id="test", 
    user_prompt="Hello", 
    user_id="dev",
    user_name="Dev"
):
    print(chunk)
```

## 2. JavaScript Client (`api.js`)
**Location**: `frontends/web/src/utils/api.js`
**Used By**: Web Frontend.

A lightweight wrapper around the browser's `fetch` API. It automatically handles:
-   Injecting the `Authorization` header.
-   Bypassing Ngrok warning pages.
-   Resolving relative URLs.

### Example Usage
```javascript
import { orionApi } from '../utils/api';

// GET request
const profile = await orionApi.get('/api/profile');

// POST request
const result = await orionApi.post('/process_prompt', {
    prompt: "Hello",
    session_id: "test"
});
```
