import os
import cv2
import requests
import numpy as np
from ultralytics import YOLO

WORKER_URL = os.environ['WORKER_URL']
API_SECRET = os.environ['API_SECRET']
VIDEO_URL = os.environ['VIDEO_URL']
JOB_ID = os.environ['JOB_ID']
CHUNK_ID = int(os.environ['CHUNK_ID'])

CHUNK_DURATION_SEC = 180
START_SEC = CHUNK_ID * CHUNK_DURATION_SEC
END_SEC = START_SEC + CHUNK_DURATION_SEC

# Use lightweight YOLOv8n (automatically fetched by ultralytics)
model = YOLO("yolov8n.pt")

cap = cv2.VideoCapture(VIDEO_URL)
cap.set(cv2.CAP_PROP_POS_MSEC, START_SEC * 1000.0)

found_timestamps = []
current_sec = START_SEC
prev_gray = None

while current_sec < END_SEC:
    cap.set(cv2.CAP_PROP_POS_MSEC, current_sec * 1000.0)
    ret, frame = cap.read()
    if not ret:
        break

    # Normalize resolution
    h, w = frame.shape[:2]
    dim = max(h, w)
    square = np.zeros((dim, dim, 3), dtype=np.uint8)
    square[0:h, 0:w] = frame
    frame_resized = cv2.resize(square, (640, 640))
    gray = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2GRAY)

    motion_detected = True
    if prev_gray is not None:
        diff = cv2.absdiff(prev_gray, gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        non_zero = cv2.countNonZero(thresh)
        # Filter out static scenes (require minimum moving pixel area)
        if non_zero < 800:
            motion_detected = False

    prev_gray = gray

    if motion_detected:
        # Multi-Angle TTA: Check 0 deg and 90 deg rotations to handle overhead orientation
        rotations = [frame_resized, cv2.rotate(frame_resized, cv2.ROTATE_90_CLOCKWISE)]
        person_detected = False

        for rot_img in rotations:
            # Predict only Person (class 0)
            results = model.predict(source=rot_img, classes=[0], conf=0.28, verbose=False)
            if len(results[0].boxes) > 0:
                person_detected = True
                break

        if person_detected:
            found_timestamps.append(int(current_sec))

    current_sec += 1

cap.release()

unique_timestamps = sorted(list(set(found_timestamps)))

try:
    response = requests.post(
        f"{WORKER_URL}/update",
        headers={"Authorization": f"Bearer {API_SECRET}"},
        json={"jobId": JOB_ID, "chunkId": CHUNK_ID, "foundTimestamps": unique_timestamps}
    )
    response.raise_for_status()
    print(f"Chunk {CHUNK_ID} done: {unique_timestamps}")
except Exception as e:
    print(f"Error updating worker: {e}")