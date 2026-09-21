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

# Extract true frame counts to avoid broken MP4 timecodes
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
if not fps or fps <= 0 or fps > 120:
    fps = 25.0

video_duration_sec = total_frames / fps
found_timestamps = []

if START_SEC < video_duration_sec:
    start_frame = int(START_SEC * fps)
    end_frame = min(int(END_SEC * fps), total_frames)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current_frame = start_frame
    step = max(1, int(round(fps))) # Step exactly 1 second of frames

    prev_gray = None

    while current_frame < end_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret: 
            break

        current_second = int(current_frame / fps)

        # Standardize resolution and blur heavily to ignore camera static/dust
        frame = cv2.resize(frame, (640, 480))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if prev_gray is not None:
            # Subtract current second from previous second
            diff = cv2.absdiff(prev_gray, gray)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            
            # Count how many pixels physically moved/changed illumination
            motion_pixels = cv2.countNonZero(thresh)

            # 3000 pixels is ~1% of the frame. Ignores bugs, guarantees human/light capture.
            if motion_pixels > 3000:
                found_timestamps.append(current_second)

        prev_gray = gray
        current_frame += step

cap.release()

unique_timestamps = sorted(list(set(found_timestamps)))

try:
    response = requests.post(
        f"{WORKER_URL}/update",
        headers={"Authorization": f"Bearer {API_SECRET}"},
        json={"jobId": JOB_ID, "chunkId": CHUNK_ID, "foundTimestamps": unique_timestamps}
    )
    response.raise_for_status()
    print(f"Chunk {CHUNK_ID} complete. Detections: {unique_timestamps}")
except Exception as e:
    print(f"Failed to post results: {e}")