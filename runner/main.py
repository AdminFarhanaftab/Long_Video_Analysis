import os
import cv2
import requests
import numpy as np
import onnxruntime as ort

WORKER_URL = os.environ['WORKER_URL']
API_SECRET = os.environ['API_SECRET']
VIDEO_URL = os.environ['VIDEO_URL']
JOB_ID = os.environ['JOB_ID']
CHUNK_ID = int(os.environ['CHUNK_ID'])

CHUNK_DURATION_SEC = 180
START_SEC = CHUNK_ID * CHUNK_DURATION_SEC

# Will automatically use YOLOv8s if you upgrade later, otherwise uses YOLOv8n
model_path = "runner/yolov8s.onnx" if os.path.exists("runner/yolov8s.onnx") else "runner/yolov8n.onnx"
session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

cap = cv2.VideoCapture(VIDEO_URL)
cap.set(cv2.CAP_PROP_POS_MSEC, START_SEC * 1000)

found_timestamps = []
frames_processed = 0

while frames_processed < CHUNK_DURATION_SEC:
    ret, frame = cap.read()
    if not ret: break
    
    # Jump exactly 1 second forward
    cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(cv2.CAP_PROP_POS_FRAMES) + 29)
    
    # --- FILTER 1: CLAHE Contrast Equalization (Fixes Bulb Glare) ---
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl,a,b))
    enhanced_rgb = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
    
    # --- FILTER 2: Aspect-Ratio Padding (Preserves Fisheye Geometry) ---
    row, col = enhanced_rgb.shape[:2]
    _max = max(col, row)
    padded = np.zeros((_max, _max, 3), np.uint8)
    padded[0:row, 0:col] = enhanced_rgb
    
    # --- FILTER 3: Resize and format for YOLO ---
    resized = cv2.resize(padded, (640, 640))
    img = resized.transpose((2, 0, 1))[np.newaxis, :, :, :].astype(np.float32) / 255.0
    
    outputs = session.run(None, {session.get_inputs()[0].name: img})
    
    # YOLOv8 tensor shape is (1, 84, 8400). Row 4 is Class 0 (Person).
    person_scores = outputs[0][0][4] 
    
    # Lowered threshold to 30% for top-down geometry
    if np.max(person_scores) > 0.30: 
        found_timestamps.append(START_SEC + frames_processed)
        
    frames_processed += 1

cap.release()

# Securely post results, removing any duplicate seconds
try:
    response = requests.post(
        f"{WORKER_URL}/update", 
        headers={"Authorization": f"Bearer {API_SECRET}"},
        json={"jobId": JOB_ID, "chunkId": CHUNK_ID, "foundTimestamps": list(set(found_timestamps))}
    )
    response.raise_for_status()
except Exception as e:
    print(f"Failed to post results to Cloudflare: {e}")