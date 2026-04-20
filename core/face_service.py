"""
ArcFace face-embedding extraction  +  MediaPipe liveness detection.
"""

import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"

import base64
import cv2
import numpy as np
import mediapipe as mp
from deepface import DeepFace

# ──── MediaPipe landmarks for Eye Aspect Ratio ───────────────────
# Right eye (6 ordered points around the eye)
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
# Left eye
LEFT_EYE = [362, 385, 387, 263, 373, 380]

EAR_THRESHOLD = 0.20

mp_face_mesh = mp.solutions.face_mesh


# ──── Helpers ─────────────────────────────────────────────────────
def decode_base64_image(b64_string: str) -> np.ndarray:
    """Decode a base64 (optionally data-URI prefixed) string → BGR ndarray."""
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]
    raw = base64.b64decode(b64_string)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode base64 image")
    return img


def _ear(landmarks, indices, w, h) -> float:
    """Eye Aspect Ratio for one eye."""
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
    v1 = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    v2 = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    horiz = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
    if horiz == 0:
        return 0.0
    return (v1 + v2) / (2.0 * horiz)


# ──── Public API ──────────────────────────────────────────────────
def check_liveness(image: np.ndarray) -> bool:
    """
    Return True when MediaPipe detects 468+ landmarks AND both eyes
    have an Eye Aspect Ratio above the threshold (eyes open → live).
    """
    h, w = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as mesh:
        result = mesh.process(rgb)
        if not result.multi_face_landmarks:
            return False

        lm = result.multi_face_landmarks[0].landmark
        if len(lm) < 468:
            return False

        left_ear = _ear(lm, LEFT_EYE, w, h)
        right_ear = _ear(lm, RIGHT_EYE, w, h)
        avg = (left_ear + right_ear) / 2.0
        return avg > EAR_THRESHOLD


def get_embedding(image: np.ndarray) -> list[float]:
    """Extract a 512-dim ArcFace embedding from a BGR image."""
    results = DeepFace.represent(
        img_path=image,
        model_name="ArcFace",
        enforce_detection=False,
        detector_backend="opencv",
    )
    if not results:
        raise ValueError("No face detected in image")
    return results[0]["embedding"]


def compute_registration_vectors(
    photos: list[str],
) -> dict[str, list[float]]:
    """
    Accept 15 base64 photos (5 front · 5 left · 5 right).
    Average each group → return 3 × 512-dim vectors.
    Memory-optimized: processes one photo at a time.
    """
    import gc

    if len(photos) != 15:
        raise ValueError(f"Expected 15 photos, got {len(photos)}")

    groups = {
        "front": photos[0:5],
        "left": photos[5:10],
        "right": photos[10:15],
    }
    vectors: dict[str, list[float]] = {}
    for angle, batch in groups.items():
        print(f"DEBUG: Processing group: {angle}")
        running_sum = None
        count = 0
        for i, b64 in enumerate(batch):
            print(f"DEBUG:   Extracting embedding for {angle} photo {i+1}/5...")
            img = decode_base64_image(b64)
            emb = np.array(get_embedding(img))
            del img  # free image memory immediately
            if running_sum is None:
                running_sum = emb
            else:
                running_sum = running_sum + emb
            count += 1
            del emb
            gc.collect()  # force garbage collection
        print(f"DEBUG:   Group {angle} completed.")
        vectors[angle] = (running_sum / count).tolist()
        del running_sum
        gc.collect()
    return vectors

