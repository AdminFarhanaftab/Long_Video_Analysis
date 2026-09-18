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
cap = cv2.VideoCapture(VIDEO_URL)
cap.set(cv2.CAP_PROP_POS_MSEC, START_SEC * 1000)

found_timestamps = []
frames_processed = 0

while frames_processed < CHUNK_DURATION_SEC:
    ret, frame = cap.read()
    if not ret: break
    
    # 1. Skip forward 1 second (assuming ~30fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(cv2.CAP_PROP_POS_FRAMES) + 29)
    
    # 2. Fix the color channel order for the AI (BGR to RGB)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # 3. Format for YOLOv8
    img = cv2.resize(frame_rgb, (640, 640))
    img = img.transpose((2, 0, 1))[np.newaxis, :, :, :].astype(np.float32) / 255.0
    
    outputs = session.run(None, {session.get_inputs()[0].name: img})
    person_scores = outputs[0][0][4] 
    
    # 4. Use a 45% confidence threshold for the 'nano' model
    if np.max(person_scores) > 0.45: 
        found_timestamps.append(START_SEC + frames_processed)
        
    frames_processed += 1

cap.release()

requests.post(
    f"{WORKER_URL}/update", 
    headers={"Authorization": f"Bearer {API_SECRET}"},
    json={"jobId": JOB_ID, "chunkId": CHUNK_ID, "foundTimestamps": found_timestamps}
)