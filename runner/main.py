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

session = ort.InferenceSession("runner/yolov8n.onnx", providers=['CPUExecutionProvider'])

# OpenCV uses HTTP Range Requests to instantly jump to the correct timestamp on Storj
cap = cv2.VideoCapture(VIDEO_URL)
cap.set(cv2.CAP_PROP_POS_MSEC, START_SEC * 1000)

found_timestamps = []
frames_processed = 0

while frames_processed < CHUNK_DURATION_SEC:
    ret, frame = cap.read()
    if not ret: break
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(cv2.CAP_PROP_POS_FRAMES) + 29)
    
    img = cv2.resize(frame, (640, 640))
    img = img.transpose((2, 0, 1))[np.newaxis, :, :, :].astype(np.float32) / 255.0
    
    outputs = session.run(None, {session.get_inputs()[0].name: img})
    
    if np.max(outputs[0]) > 0.5: 
        found_timestamps.append(START_SEC + frames_processed)
        
    frames_processed += 1

cap.release()

# Securely post results
requests.post(
    f"{WORKER_URL}/update", 
    headers={"Authorization": f"Bearer {API_SECRET}"},
    json={"jobId": JOB_ID, "chunkId": CHUNK_ID, "foundTimestamps": found_timestamps}
)