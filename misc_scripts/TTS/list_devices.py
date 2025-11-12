
import sounddevice as sd

print("Searching for audio devices...\n")

# Query all available devices
devices = sd.query_devices()
print("Available audio devices:")
print(devices)

print("\n--- Input Devices ---")
# Filter for devices that have at least 1 input channel
input_devices = sd.query_devices(kind='input')
print(input_devices)

print("\n--- Recommended Device ---")
print("Look for a device that seems to be a 'loopback' or 'monitor'.")
print("On Windows, this might be 'Stereo Mix' or 'What U Hear'.")
print("On Linux, this might be a 'Monitor' device.")
print("On macOS, you will likely need to install a virtual audio driver")
print("like 'BlackHole' and select it here.\n")
print("Once you find it, note its 'index' number (the number at the far left).")
print("If you don't see one, you may need to enable it in your OS sound settings.")