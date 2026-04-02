import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Defaults — overridden by set_data_dir() when --data is passed
DATA_DIR = os.path.join(BASE_DIR, 'data')
TIFF_DIR = os.path.join(DATA_DIR, 'trainingTiffs')
ANNOTATIONS_DIR = os.path.join(DATA_DIR, 'annotations')
EXPORT_DIR = os.path.join(DATA_DIR, 'trainingPolygons')
CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
DATASET_CONFIG_PATH = os.path.join(DATA_DIR, 'dataset_config.json')
STATE_PATH = os.path.join(DATA_DIR, 'app_state.json')
SAM2_WEIGHTS_DIR = os.path.join(BASE_DIR, 'sam2_weights')
MODELS_DIR = os.path.join(DATA_DIR, 'models')
AUTH_PATH = os.path.join(DATA_DIR, 'auth.json')


def set_data_dir(data_dir):
    """Reconfigure all paths based on a new data directory."""
    global DATA_DIR, TIFF_DIR, ANNOTATIONS_DIR, EXPORT_DIR
    global CONFIG_PATH, DATASET_CONFIG_PATH, STATE_PATH, MODELS_DIR, AUTH_PATH

    DATA_DIR = os.path.abspath(data_dir)

    # Auto-detect TIFF subdirectory name
    for subdir in ('trainingTiffs', 'trainingAreas', 'tiffs', 'images'):
        candidate = os.path.join(DATA_DIR, subdir)
        if os.path.isdir(candidate):
            TIFF_DIR = candidate
            break
    else:
        # Fallback: look for any directory containing .tif files
        TIFF_DIR = os.path.join(DATA_DIR, 'trainingTiffs')
        for entry in os.listdir(DATA_DIR):
            full = os.path.join(DATA_DIR, entry)
            if os.path.isdir(full) and any(f.lower().endswith('.tif') for f in os.listdir(full)):
                TIFF_DIR = full
                break

    ANNOTATIONS_DIR = os.path.join(DATA_DIR, 'annotations')
    EXPORT_DIR = os.path.join(DATA_DIR, 'trainingPolygons')
    CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
    DATASET_CONFIG_PATH = os.path.join(DATA_DIR, 'dataset_config.json')
    STATE_PATH = os.path.join(DATA_DIR, 'app_state.json')
    MODELS_DIR = os.path.join(DATA_DIR, 'models')
    AUTH_PATH = os.path.join(DATA_DIR, 'auth.json')

    # Ensure directories exist
    os.makedirs(ANNOTATIONS_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)


# Ensure default directories exist
os.makedirs(ANNOTATIONS_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(SAM2_WEIGHTS_DIR, exist_ok=True)
