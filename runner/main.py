import os
import sys
import cv2
import requests
import numpy as np
import onnxruntime as ort

WORKER_URL = os.environ['WORKER_URL']
VIDEO_URL = os.environ['VIDEO_URL']
JOB_ID = os.environ['JOB_ID']
CHUNK_ID = int(os.environ['CHUNK_ID'])

CHUNK_DURATION_SEC = 180 # 3 minutes per runner
START_SEC = CHUNK_ID * CHUNK_DURATION_SEC

# Load Model (CPU Optimized ONNX)
session = ort.InferenceSession("runner/yolov8n.onnx", providers=['CPUExecutionProvider'])

# Open Video Stream directly from URL
cap = cv2.VideoCapture(VIDEO_URL)
cap.set(cv2.CAP_PROP_POS_MSEC, START_SEC * 1000)

found_timestamps = []
frames_processed = 0

while frames_processed < CHUNK_DURATION_SEC:
    ret, frame = cap.read()
    if not ret: break
    
    # Sample at 1 FPS (skip 29 frames if video is 30fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(cv2.CAP_PROP_POS_FRAMES) + 29)
    
    # Preprocess frame for YOLO (640x640)
    img = cv2.resize(frame, (640, 640))
    img = img.transpose((2, 0, 1))[np.newaxis, :, :, :].astype(np.float32) / 255.0
    
    # Run Inference
    outputs = session.run(None, {session.get_inputs()[0].name: img})
    
    # Simplified detection check (assuming output tensor contains confidences)
    # In a full script, you apply Non-Max Suppression (NMS) here to specifically filter Class 0 (Person)
    if np.max(outputs[0]) > 0.5: 
        found_timestamps.append(START_SEC + frames_processed)
        
    frames_processed += 1

cap.release()

# Post Results back to Cloudflare
requests.post(f"{WORKER_URL}/update", json={
    "jobId": JOB_ID,
    "chunkId": CHUNK_ID,
    "foundTimestamps": found_timestamps
})