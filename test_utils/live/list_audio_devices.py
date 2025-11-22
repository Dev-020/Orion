import pyaudio

p = pyaudio.PyAudio()

print("Available Audio Host APIs:")
for i in range(p.get_host_api_count()):
    api = p.get_host_api_info_by_index(i)
    print(f"  {i}: {api['name']} (type: {api['type']})")

print("\nAvailable Audio Input Devices:")
info = p.get_host_api_info_by_index(0)
numdevices = info.get('deviceCount')

for i in range(p.get_device_count()):
    dev = p.get_device_info_by_index(i)
    if dev['maxInputChannels'] > 0:
        print(f"  {i}: {dev['name']} (HostAPI: {dev['hostApi']})")
        # Check for loopback/WASAPI specific flags if possible, though standard pyaudio might not show them explicitly in the name
        
p.terminate()
