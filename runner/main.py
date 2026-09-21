import os
import cv2
import requests
import numpy as np

WORKER_URL = os.environ['WORKER_URL']
API_SECRET = os.environ['API_SECRET']
VIDEO_URL = os.environ['VIDEO_URL']
JOB_ID = os.environ['JOB_ID']
CHUNK_ID = int(os.environ['CHUNK_ID'])

CHUNK_DURATION_SEC = 180
START_SEC = CHUNK_ID * CHUNK_DURATION_SEC
END_SEC = START_SEC + CHUNK_DURATION_SEC

cap = cv2.VideoCapture(VIDEO_URL)

total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
if not fps or fps <= 5 or fps > 120:
    fps = 25.0

video_duration_sec = total_frames / fps
found_timestamps = []

if START_SEC < video_duration_sec:
    start_frame = int(START_SEC * fps)
    end_frame = min(int(END_SEC * fps), total_frames)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current_frame_idx = start_frame
    frame_step = max(1, int(round(fps)))

    while current_frame_idx < end_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        current_second = int(current_frame_idx / fps)

        # Convert to HSV to separate color intensity (Saturation) and Brightness (Value)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        sat_mean = np.mean(hsv[:, :, 1])
        val_mean = np.mean(hsv[:, :, 2])

        # Baseline IR mode in this footage has Saturation < 10.0.
        # Floodlight mode switches to color with Saturation > 18.0 and higher brightness.
        is_floodlight_on = (sat_mean > 16.0) or (val_mean > 95.0 and sat_mean > 12.0)

        if is_floodlight_on:
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
    print(f"Chunk {CHUNK_ID} complete. Detected seconds: {unique_timestamps}")
except Exception as e:
    print(f"Failed to post results: {e}")