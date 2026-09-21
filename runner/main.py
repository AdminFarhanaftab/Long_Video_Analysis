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

model = YOLO("yolov8n.pt")

cap = cv2.VideoCapture(VIDEO_URL)

# Get accurate video properties
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
if not fps or fps <= 5 or fps > 120:
    fps = 25.0

video_duration_sec = total_frames / fps

found_timestamps = []

# If this runner's chunk starts beyond the total video duration, exit cleanly
if START_SEC < video_duration_sec:
    start_frame = int(START_SEC * fps)
    end_frame = min(int(END_SEC * fps), total_frames)

    # Seek to the starting frame via FRAME index (reliable across all codecs)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current_frame_idx = start_frame

    frame_step = max(1, int(round(fps)))  # Step forward by ~1 second of frames

    while current_frame_idx < end_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        current_second = int(current_frame_idx / fps)

        # Evaluate at native orientation and 90-degree rotation (for top-down angles)
        rot_frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        # Predict only humans (class 0)
        res1 = model.predict(source=frame, classes=[0], conf=0.20, verbose=False)
        res2 = model.predict(source=rot_frame, classes=[0], conf=0.20, verbose=False)

        if len(res1[0].boxes) > 0 or len(res2[0].boxes) > 0:
            found_timestamps.append(current_second)

        current_frame_idx += frame_step

cap.release()

unique_timestamps = sorted(list(set(found_timestamps)))

try:
    response = requests.post(
        f"{WORKER_URL}/update",
        headers={"Authorization": f"Bearer {API_SECRET}"},
        json={"jobId": JOB_ID, "chunkId": CHUNK_ID, "foundTimestamps": unique_timestamps}
    )
    response.raise_for_status()
    print(f"Chunk {CHUNK_ID} finished. Detected seconds: {unique_timestamps}")
except Exception as e:
    print(f"Error posting results: {e}")