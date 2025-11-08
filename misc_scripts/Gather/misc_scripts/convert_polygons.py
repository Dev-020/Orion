import os
import json
from PIL import Image  # Install with: pip install pillow
import shutil  # <-- NEW: Import the library for moving files

# --- 1. CONFIGURE YOUR PATHS ---
# This path is relative from where you RUN the script (.../gather)
# to the project folder (.../baru_ore)
PROJECT_PATH_FROM_RUN_DIR = "dataset\\pending_review\\baru_ore"

# --- NEW: Define the base "processed" directory ---
# This will be relative to where you run the script (e.g., .../gather/dataset/processed)
PROCESSED_DIR_BASE = "dataset/processed" 

# This is the "project name" that Label Studio's Local Files URL will use.
# It's the name of the folder you added as the "Absolute local path"
# in the Label Studio UI's storage settings.
PROJECT_NAME_FOR_URL = "baru_ore"

# These are the subdirectories inside your project folder
LABELS_SUBDIR = "labels"
IMAGES_SUBDIR = "images"
CLASSES_FILE = "classes.txt"

# This will be created in the directory where you RUN the script
OUTPUT_JSON = "tasks-for-import.json"

# --- 2. CONFIGURE YOUR LABEL STUDIO SETUP ---
# These MUST match the names in your Label Studio UI's <View>
# <Image name="image" ... />
# <PolygonLabels name="label" ... />
LABEL_STUDIO_IMAGE_NAME = "image"
LABEL_STUDIO_LABEL_NAME = "poly_label"

# --- End of Configuration ---


def convert_yolo_polygons_to_ls():
    # Get the directory where the command is being run
    run_dir = os.getcwd()
    
    # Build all paths
    project_base = os.path.join(run_dir, PROJECT_PATH_FROM_RUN_DIR)
    labels_dir = os.path.join(project_base, LABELS_SUBDIR)
    images_dir = os.path.join(project_base, IMAGES_SUBDIR)
    classes_file = os.path.join(project_base, CLASSES_FILE)

    # --- NEW: Define and create the destination "processed" directories ---
    # This builds the full path: .../dataset/processed/baru_ore/
    resource_dest_dir = os.path.join(run_dir, PROCESSED_DIR_BASE, PROJECT_NAME_FOR_URL)
    
    # .../dataset/processed/baru_ore/labels
    processed_labels_dir = os.path.join(resource_dest_dir, LABELS_SUBDIR)
    
    # .../dataset/processed/baru_ore/images
    processed_images_dir = os.path.join(resource_dest_dir, IMAGES_SUBDIR)
    
    # Create these folders if they don't exist
    os.makedirs(processed_labels_dir, exist_ok=True)
    os.makedirs(processed_images_dir, exist_ok=True)
    # --- END NEW SECTION ---

    if not os.path.exists(labels_dir):
        print(f"ERROR: Labels directory not found at: {labels_dir}")
        return
    if not os.path.exists(images_dir):
        print(f"ERROR: Images directory not found at: {images_dir}")
        return
    if not os.path.exists(classes_file):
        print(f"ERROR: Classes file not found at: {classes_file}")
        return

    # 1. Read class names
    with open(classes_file, 'r') as f:
        class_names = [line.strip() for line in f.readlines()]
    print(f"Found {len(class_names)} classes: {class_names}")

    tasks = []  # This will hold all our converted tasks

    # 2. Loop through all label files
    for label_file in os.listdir(labels_dir):
        if not label_file.endswith('.txt'):
            continue

        base_filename = os.path.splitext(label_file)[0]
        # <-- NEW: Get the full path to the current label file
        current_label_path = os.path.join(labels_dir, label_file) 
        
        # Find the matching image
        image_path = None
        for ext in ['.png', '.jpg', '.jpeg']:
            potential_path = os.path.join(images_dir, base_filename + ext)
            if os.path.exists(potential_path):
                image_path = potential_path
                break
        
        if not image_path:
            print(f"  WARNING: No matching image found for {label_file}. Skipping.")
            continue
            
        print(f"Processing: {label_file}") # <-- NEW: Moved this down to confirm processing

        # 3. Get image dimensions
        with Image.open(image_path) as img:
            img_width, img_height = img.size

        # 4. Build the "data" part of the JSON task
        # This path MUST match what Label Studio expects
        ls_image_path = f"/data/local-files/?d={PROJECT_NAME_FOR_URL}/{IMAGES_SUBDIR}/{os.path.basename(image_path)}"
        
        task = {
            "data": {
                "image": ls_image_path
            },
            "predictions": []
        }

        # 5. Read the polygon labels from the .txt file
        prediction_results = []
        # <-- NEW: Use the full 'current_label_path'
        with open(current_label_path, 'r') as f: 
            for line in f.readlines():
                parts = line.strip().split()
                if len(parts) < 7: # Must have class + at least 3 points
                    continue
                
                class_id = int(parts[0])
                class_name = class_names[class_id]
                
                # Get the normalized polygon points
                normalized_points = [float(p) for p in parts[1:]]
                
                # 6. Convert normalized (0.0-1.0) to Label Studio PERCENTAGE (0.0-100.0)
                ls_points = []
                # Loop in pairs (x, y)
                for i in range(0, len(normalized_points), 2):
                    norm_x = normalized_points[i]
                    norm_y = normalized_points[i+1]
                    
                    ls_x = norm_x * 100.0
                    ls_y = norm_y * 100.0
                    ls_points.append([ls_x, ls_y])

                # 7. Build the final "result" object for this one polygon
                prediction_results.append({
                    "from_name": LABEL_STUDIO_LABEL_NAME,
                    "to_name": LABEL_STUDIO_IMAGE_NAME,
                    "type": "polygonlabels",
                    "value": {
                        "points": ls_points,
                        "polygonlabels": [class_name]
                    }
                })

        # 8. Add all found polygons to the task
        task["predictions"].append({
            "model_version": "custom_polygon_import",
            "result": prediction_results
        })
        
        tasks.append(task)
        
        # --- NEW: Move the processed files to the archive ---
        try:
            shutil.move(current_label_path, os.path.join(processed_labels_dir, label_file))
            shutil.move(image_path, os.path.join(processed_images_dir, os.path.basename(image_path)))
            print(f"  > Successfully processed and moved {base_filename}")
        except Exception as e:
            print(f"  ! ERROR moving files for {base_filename}: {e}")
            # If moving fails, we should remove the task we just added to prevent
            # processing it again next time.
            tasks.pop()
        # --- END NEW SECTION ---

    # 9. Write the final JSON file
    if not tasks: # <-- NEW: Check if we processed any files
        print("\nNo new files to process. Exiting.")
        return

    output_file_path = os.path.join(run_dir, OUTPUT_JSON)
    with open(output_file_path, 'w') as f:
        json.dump(tasks, f, indent=2)

    print(f"\n--- SUCCESS ---")
    print(f"Wrote {len(tasks)} new tasks to {output_file_path}")


if __name__ == "__main__":
    convert_yolo_polygons_to_ls()