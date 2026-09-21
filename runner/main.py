import os
import cv2
import requests
from ultralytics import YOLO

WORKER_URL = os.environ['WORKER_URL']
API_SECRET = os.environ['API_SECRET']
VIDEO_URL = os.environ['VIDEO_URL']
JOB_ID = os.environ['JOB_ID']
CHUNK_ID = int(os.environ['CHUNK_ID'])

CHUNK_DURATION_SEC = 180
START_SEC = CHUNK_ID * CHUNK_DURATION_SEC
END_SEC = START_SEC + CHUNK_DURATION_SEC

# Prefer yolov8s.onnx if committed, otherwise fallback to yolov8n.pt
if os.path.exists("runner/yolov8s.onnx"):
    model = YOLO("runner/yolov8s.onnx", task="detect")
elif os.path.exists("runner/yolov8s.pt"):
    model = YOLO("runner/yolov8s.pt")
else:
    model = YOLO("yolov8n.pt")

cap = cv2.VideoCapture(VIDEO_URL)
fps = cap.get(cv2.CAP_PROP_FPS)
if not fps or fps <= 0 or fps > 120:
    fps = 25.0  # Safe fallback for corrupted CCTV headers

# Seek by exact millisecond timestamp, NOT raw frame count
cap.set(cv2.CAP_PROP_POS_MSEC, START_SEC * 1000.0)

found_timestamps = []
current_sec = START_SEC

while current_sec < END_SEC:
    # Set position by exact timestamp in milliseconds
    cap.set(cv2.CAP_PROP_POS_MSEC, current_sec * 1000.0)
    ret, frame = cap.read()
    if not ret:
        break

    # Ultralytics handles CLAHE-like normalization, letterboxing, and RGB conversion automatically
    # classes=[0] filters ONLY humans (COCO class 0 = person)
    # conf=0.35 balances CCTV overhead perspective with strict false-positive elimination
    results = model.predict(source=frame, classes=[0], conf=0.35, verbose=False)

    # Check if a genuine person bounding box was verified
    if len(results[0].boxes) > 0:
        found_timestamps.append(int(current_sec))

    current_sec += 1

cap.release()

# Deduplicate and sort
unique_timestamps = sorted(list(set(found_timestamps)))

try:
    response = requests.post(
        f"{WORKER_URL}/update",
        headers={"Authorization": f"Bearer {API_SECRET}"},
        json={"jobId": JOB_ID, "chunkId": CHUNK_ID, "foundTimestamps": unique_timestamps}
    )
    response.raise_for_status()
    print(f"Chunk {CHUNK_ID} completed successfully. Found: {unique_timestamps}")
except Exception as e:
    print(f"Failed to post results to Cloudflare: {e}")