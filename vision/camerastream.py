import asyncio
import cv2
import numpy as np
from pathlib import Path
from typing import Any
from ultralytics import YOLO
from insightface.app import FaceAnalysis

# -----------------------------
# CONFIG
# -----------------------------
KID_AGE_THRESHOLD = 14
KID_HEIGHT_RATIO = 0.45
FACE_RECOGNITION_THRESHOLD = 0.6  # higher = stricter

try:
    # Preferred: import from the vision package when running as part of the service
    from vision.config import RESIDENTS_DIR  # shared project-root folder (set via VISION_RESIDENTS_DIR in container)
except ImportError:
    # Fallback when running this file directly as a script
    RESIDENTS_DIR = "residents"

# -----------------------------
# LOAD MODELS (once)
# -----------------------------
print("Loading YOLO...")
yolo = YOLO("yolov8n.pt")

print("Loading Face Analysis...")
face_app = FaceAnalysis(providers=["CPUExecutionProvider"])
face_app.prepare(ctx_id=0, det_size=(640, 640))

##loading the residents databse
resident_embeddings = {}  # {name: embedding}


def load_residents(residents_dir: str) -> dict:
    """Load resident photos and extract face embeddings.
    
    Expected structure:
    residents/
        john.jpg
        jane.jpg
        mike.jpg
    
    Returns dict mapping resident names to their embeddings.
    """
    embeddings = {}
    residents_path = Path(residents_dir)
    
    if not residents_path.exists():
        print(f"Warning: Residents directory '{residents_dir}' not found. Creating it...")
        residents_path.mkdir(exist_ok=True)
        return embeddings
    
    # Use repr() so we can spot accidental whitespace in env vars.
    print(f"Loading residents from {residents_dir!r}...")
    try:
        print(f"Residents dir resolved to: {residents_path.resolve()!s}")
    except Exception:
        pass
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}

    # count what we see on disk (regardless of whether faces are detected).
    total_files = 0
    supported_files = 0
    unreadable_files = 0
    no_face_files = 0
    loaded_files = 0

    # scan recursively so residents can be organized into subfolders.
    # (e.g., residents/john/1.jpg, residents/person/profile.png)
    try:
        all_paths = list(residents_path.rglob("*"))
        total_files = sum(1 for p in all_paths if p.is_file())
        print(f"Found {total_files} files under residents dir.")
        # Print a small sample for debugging
        sample = [str(p) for p in all_paths if p.is_file()][:20]
        if sample:
            print("Sample resident files:")
            for p in sample:
                print(f"  - {p}")
    except Exception as e:
        print(f"Warning: Failed to scan residents dir: {e}")
        all_paths = []
    
    for img_file in all_paths:
        if not getattr(img_file, "is_file", lambda: False)():
            continue

        if img_file.suffix.lower() in image_extensions:
            supported_files += 1
            # extract the  name from filename (without extension)
            resident_name = img_file.stem
            
            # load and process image
            img = cv2.imread(str(img_file))
            if img is None:
                print(f"Warning: Could not load {img_file}")
                unreadable_files += 1
                continue
            
            # extract face embedding
            faces = face_app.get(img)
            if not faces:
                print(f"Warning: No face detected in {img_file}")
                no_face_files += 1
                continue
            
            embedding = faces[0].normed_embedding
            embeddings[resident_name] = embedding
            loaded_files += 1
            print(f"  Loaded: {resident_name}")
    
    if supported_files == 0:
        print(
            "Warning: No supported resident images found. "
            "Supported extensions: .jpg, .jpeg, .png, .bmp"
        )
    print(
        f"Loaded {len(embeddings)} residents. "
        f"(supported_images={supported_files}, loaded={loaded_files}, "
        f"unreadable={unreadable_files}, no_face={no_face_files})"
    )
    return embeddings


def recognize_face(face_embedding: np.ndarray, resident_db: dict, threshold: float = 0.6) -> tuple:
    """Recognize a face by comparing embedding with resident database.
    
    Args:
        face_embedding: Face embedding from InsightFace
        resident_db: Dictionary mapping names to embeddings
        threshold: Cosine similarity threshold (0-1)
    
    Returns:
        (name, similarity_score) or (None, 0.0) if no match found
    """
    if not resident_db:
        return None, 0.0
    
    best_match = None
    best_score = 0.0
    
    for name, ref_embedding in resident_db.items():
        # Cosine similarity
        similarity = np.dot(face_embedding, ref_embedding)
        
        if similarity > best_score:
            best_score = similarity
            best_match = name
    
    if best_score >= threshold:
        return best_match, best_score
    
    return None, best_score


# Load resident database at startup
resident_embeddings = load_residents(RESIDENTS_DIR)


def analyze_frame(image: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Run kid/delivery/stranger logic on a frame. Returns (annotated_image, list of detections)."""
    if image is None:
        return image, []

    img = image.copy()
    img_h = img.shape[0]

    # YOLO detection
    results = yolo(img, conf=0.4)[0]

    persons = []
    has_box = False

    for box in results.boxes:
        cls = int(box.cls[0])
        label = yolo.names[cls]
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        if label == "person":
            persons.append((x1, y1, x2, y2))

        if label in ["backpack", "handbag", "suitcase"]:
            has_box = True

    detections: list[dict[str, Any]] = []

    # Classify each person
    for (x1, y1, x2, y2) in persons:
        crop = img[y1:y2, x1:x2]

        is_kid = False
        reason = ""
        recognized_name = None
        recognition_score = 0.0

        # FACE-BASED AGE CHECK AND RECOGNITION
        faces = face_app.get(crop)
        if faces:
            face = faces[0]
            age = int(face.age)

            if hasattr(face, "normed_embedding"):
                recognized_name, recognition_score = recognize_face(
                    face.normed_embedding,
                    resident_embeddings,
                    FACE_RECOGNITION_THRESHOLD,
                )

            if age < KID_AGE_THRESHOLD:
                is_kid = True
                reason = f"face age {age}"
            else:
                reason = f"face age {age}"
        else:
            height_ratio = (y2 - y1) / img_h
            if height_ratio < KID_HEIGHT_RATIO:
                is_kid = True
                reason = f"height ratio {height_ratio:.2f}"
            else:
                reason = f"height ratio {height_ratio:.2f}"

        # FINAL CLASSIFICATION
        if recognized_name:
            label = f"RESIDENT: {recognized_name.upper()}"
            color = (0, 255, 0)
            text = f"{label} ({reason}, match: {recognition_score:.2f})"
        elif is_kid:
            label = "KID"
            color = (255, 0, 255)
            text = f"{label} ({reason})"
        elif has_box:
            label = "DELIVERY"
            color = (255, 255, 0)
            text = f"{label} ({reason})"
        else:
            label = "STRANGER"
            color = (0, 0, 255)
            text = f"{label} ({reason})"

        detections.append({
            "label": label,
            "box": (x1, y1, x2, y2),
            "reason": reason,
            "recognized_name": recognized_name,
            "recognition_score": recognition_score,
            "is_kid": is_kid,
        })

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    return img, detections


def classify_and_draw(image: np.ndarray) -> np.ndarray:
    """Convenience: run analysis and return only the annotated image."""
    annotated, _ = analyze_frame(image)
    return annotated




async def run_analyzer(
    input_queue: asyncio.Queue,
    results_queue: asyncio.Queue,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """
    Consume images from input_queue, run analysis in a thread pool, push results to results_queue.

    Input queue items: (request_id, image) where request_id is any hashable (or None).
    To stop the worker, put None on the input queue (single item).

    Result items: (request_id, annotated_image, detections).
    """
    loop = loop or asyncio.get_running_loop()

    while True:
        try:
            item = await input_queue.get()
        except asyncio.CancelledError:
            break

        if item is None:
            input_queue.task_done()
            break

        request_id, image = item
        input_queue.task_done()

        try:
            annotated, detections = await loop.run_in_executor(None, analyze_frame, image)
            await results_queue.put((request_id, annotated, detections))
        except Exception as e:
            # Push error result so consumer can handle it
            await results_queue.put((request_id, None, [], e))


async def put_image(
    input_queue: asyncio.Queue,
    image: np.ndarray,
    request_id: str | int | None = None,
) -> None:
    """Helper: submit one image for analysis."""
    await input_queue.put((request_id, image))


async def get_result(results_queue: asyncio.Queue) -> tuple[Any, np.ndarray | None, list, Exception | None]:
    """
    Helper: get one result. Returns (request_id, annotated_image, detections, error).
    error is non-None only if analysis raised.
    """
    item = await results_queue.get()
    results_queue.task_done()
    if len(item) == 4:
        return item  # (request_id, None, [], e)
    request_id, annotated, detections = item
    return request_id, annotated, detections, None





if __name__ == "__main__":

    # -----------------------------
    # WEBCAM STREAM (sync, original)
    # -----------------------------
    cap = cv2.VideoCapture(0)  # or an RTSP/HTTP URL instead of 0

    if not cap.isOpened():
        raise RuntimeError("Could not open webcam")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        annotated_frame = classify_and_draw(frame.copy())
        cv2.imshow("Webcam Stream", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()