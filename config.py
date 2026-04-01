import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
TIFF_DIR = os.path.join(DATA_DIR, 'trainingTiffs')
ANNOTATIONS_DIR = os.path.join(DATA_DIR, 'annotations')
EXPORT_DIR = os.path.join(DATA_DIR, 'trainingPolygons')
CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
DATASET_CONFIG_PATH = os.path.join(DATA_DIR, 'dataset_config.json')
STATE_PATH = os.path.join(DATA_DIR, 'app_state.json')
SAM2_WEIGHTS_DIR = os.path.join(BASE_DIR, 'sam2_weights')

# Ensure directories exist
os.makedirs(ANNOTATIONS_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(SAM2_WEIGHTS_DIR, exist_ok=True)
