import cv2
import mediapipe as mp
import numpy as np
import time
from threading import Thread
from datetime import datetime

class WebcamStream:
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src, cv2.CAP_AVFOUNDATION)
        if not self.stream.isOpened(): self.stopped = True; return
        (self.grabbed, self.frame) = self.stream.read()
        if not self.grabbed: self.stopped = True; return
        self.stopped = False
    def start(self):
        t = Thread(target=self.update, args=()); t.daemon = True; t.start(); return self
    def update(self):
        while not self.stopped: self.grabbed, self.frame = self.stream.read()
    def read(self):
        return self.frame
    def stop(self):
        self.stopped = True; time.sleep(0.5); self.stream.release()

class TwoHandGestureManager:
    def is_fist(self, hand_landmarks):
        """Check if one hand is closed into a fist."""
        if not hand_landmarks: return False
        landmarks = hand_landmarks.landmark
        return (landmarks[8].y > landmarks[6].y and 
                landmarks[12].y > landmarks[10].y and 
                landmarks[16].y > landmarks[14].y and 
                landmarks[20].y > landmarks[18].y)

    def get_gesture(self, multi_hand_landmarks, frame_w, frame_h):
        if not multi_hand_landmarks or len(multi_hand_landmarks) < 2:
            return "IDLE", None
        
        hand1, hand2 = multi_hand_landmarks
        
        if hand1.landmark[0].x > hand2.landmark[0].x:
            right_hand, left_hand = hand1, hand2
        else:
            right_hand, left_hand = hand2, hand1
            
        cursor_pos = (int(right_hand.landmark[8].x * frame_w), int(right_hand.landmark[8].y * frame_h))
        
        if self.is_fist(left_hand):
            return "DRAW", cursor_pos
        else:
            return "POINTER", cursor_pos

class DwellClicker:
    def __init__(self, dwell_time=1.0):
        self.DWELL_TIME = dwell_time; self.hover_target, self.hover_time = None, 0
    def check(self, frame, cursor_pos, target_pos, enabled=True):
        if not enabled or not cursor_pos: self.reset(); return False
        cx, cy = cursor_pos; x1, y1, x2, y2 = target_pos
        is_hovering = x1 < cx < x2 and y1 < cy < y2
        if is_hovering:
            if self.hover_target != str(target_pos):
                self.hover_target = str(target_pos); self.hover_time = time.time()
            progress = (time.time() - self.hover_time) / self.DWELL_TIME
            if progress >= 1.0: self.reset(); return True
            cv2.circle(frame, (cx, cy), 25, (0, 255, 0), 3)
            cv2.ellipse(frame, (cx, cy), (25, 25), -90, 0, 360 * progress, (0, 255, 255), -1)
        else:
            if self.hover_target == str(target_pos): self.reset()
        return False
    def reset(self): self.hover_target = None; self.hover_time = 0

def draw_button(frame, pos, text, hover=False):
    x, y, w, h = pos; color = (80, 80, 80) if not hover else (0, 200, 0)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, -1)
    text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 0.8, 2)[0]
    text_x, text_y = x + (w - text_size[0]) // 2, y + (h + text_size[1]) // 2
    cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 2)

def save_signature(strokes, crop_box):
    if not strokes or not crop_box: return
    x_coords = [c[0] for c in crop_box]; y_coords = [c[1] for c in crop_box]
    x_min, y_min = min(x_coords), min(y_coords); x_max, y_max = max(x_coords), max(y_coords)
    margin = 20; width, height = (x_max - x_min) + 2 * margin, (y_max - y_min) + 2 * margin
    if width <= 1 or height <= 1: return
    
    signature_canvas = np.zeros((height, width, 4), dtype=np.uint8)
    for stroke in strokes:
        shifted_stroke = [(p[0] - x_min + margin, p[1] - y_min + margin) for p in stroke]
        if len(shifted_stroke) > 1: cv2.polylines(signature_canvas, [np.array(shifted_stroke)], False, (0, 0, 0, 255), 3)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S"); filename = f"signature_{timestamp}.png"
    cv2.imwrite(filename, signature_canvas); print(f"Signature saved under: {filename}")

vs = WebcamStream(src=0).start(); time.sleep(1.0)
mp_hands = mp.solutions.hands; hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.7, max_num_hands=2)
gesture_manager, clicker = TwoHandGestureManager(), DwellClicker()
app_state, strokes, message = "IDLE", [], ""
crop_box, active_corner = [], -1
prev_gesture = "IDLE"

while True:
    frame = vs.read()
    if frame is None: continue
    frame = cv2.flip(frame, 1); h, w, c = frame.shape
    results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    
    gesture, cursor_pos = gesture_manager.get_gesture(results.multi_hand_landmarks, w, h)

    if app_state == "IDLE":
        cv2.putText(frame, "Show both hands to start", (50, h//2 - 20), cv2.FONT_HERSHEY_DUPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, "Left hand open: Pointer | Closed left hand: Drawing", (50, h//2 + 20), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 255, 255), 2)
        if gesture != "IDLE": app_state = "DRAWING"; strokes = []
    
    elif app_state == "DRAWING":
        if gesture == "DRAW":
            if prev_gesture != "DRAW": strokes.append([])
            if strokes: strokes[-1].append(cursor_pos)
        
        btn_validate_pos = [w - 300, 10, 140, 60]; btn_reset_pos = [w - 150, 10, 140, 60]
        draw_button(frame, btn_validate_pos, "Validate", gesture == "POINTER" and cursor_pos and btn_validate_pos[0] < cursor_pos[0] < btn_validate_pos[0]+btn_validate_pos[2])
        draw_button(frame, btn_reset_pos, "Start again", gesture == "POINTER" and cursor_pos and btn_reset_pos[0] < cursor_pos[0] < btn_reset_pos[0]+btn_reset_pos[2])
        if clicker.check(frame, cursor_pos, [btn_validate_pos[0], btn_validate_pos[1], btn_validate_pos[0]+btn_validate_pos[2], btn_validate_pos[1]+btn_validate_pos[3]], enabled=(gesture == "POINTER")):
            all_points = [p for s in strokes for p in s]
            if all_points:
                x_coords, y_coords = [p[0] for p in all_points], [p[1] for p in all_points]
                crop_box = [(min(x_coords)-20, min(y_coords)-20), (max(x_coords)+20, min(y_coords)-20), (max(x_coords)+20, max(y_coords)+20), (min(x_coords)-20, max(y_coords)+20)]
                active_corner, app_state = -1, "CROPPING"
            else: app_state = "IDLE"
        elif clicker.check(frame, cursor_pos, [btn_reset_pos[0], btn_reset_pos[1], btn_reset_pos[0]+btn_reset_pos[2], btn_reset_pos[1]+btn_reset_pos[3]], enabled=(gesture == "POINTER")):
            strokes = []

    elif app_state == "CROPPING":
        pts = np.array(crop_box, np.int32); cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
        
        if gesture == "DRAW":
            if prev_gesture != "DRAW" and cursor_pos:
                for i, corner in enumerate(crop_box):
                    if np.linalg.norm(np.array(corner) - np.array(cursor_pos)) < 40: active_corner = i; break
            if active_corner != -1 and cursor_pos: crop_box[active_corner] = cursor_pos
        else: active_corner = -1
            
        for i, corner in enumerate(crop_box): cv2.circle(frame, corner, 12, (255, 0, 0) if i != active_corner else (0, 255, 255), -1)

        btn_save_pos = [w - 300, 10, 140, 60]; btn_reset_pos = [w - 150, 10, 140, 60]
        draw_button(frame, btn_save_pos, "Enregistrer", gesture == "POINTER" and cursor_pos and btn_save_pos[0] < cursor_pos[0] < btn_save_pos[0]+btn_save_pos[2])
        draw_button(frame, btn_reset_pos, "Recommencer", gesture == "POINTER" and cursor_pos and btn_reset_pos[0] < cursor_pos[0] < btn_reset_pos[0]+btn_reset_pos[2])
        if clicker.check(frame, cursor_pos, [btn_save_pos[0], btn_save_pos[1], btn_save_pos[0]+btn_save_pos[2], btn_save_pos[1]+btn_save_pos[3]], enabled=(gesture == "POINTER")):
            save_signature(strokes, crop_box); message = "Signature saved !"; time.sleep(1)
            app_state, strokes = "IDLE", []
        elif clicker.check(frame, cursor_pos, [btn_reset_pos[0], btn_reset_pos[1], btn_reset_pos[0]+btn_reset_pos[2], btn_reset_pos[1]+btn_reset_pos[3]], enabled=(gesture == "POINTER")):
            app_state, strokes = "DRAWING", []
            
    for stroke in strokes:
        if len(stroke) > 1: cv2.polylines(frame, [np.array(stroke)], False, (255, 255, 255), 3)
    if cursor_pos:
        color = (0, 255, 0) if gesture == "DRAW" else (255, 150, 0)
        cv2.circle(frame, cursor_pos, 12, color, -1)
        cv2.circle(frame, cursor_pos, 12, (255, 255, 255), 2)
    
    if gesture == "IDLE" and app_state != "IDLE": app_state = "IDLE"
    prev_gesture = gesture
    cv2.imshow("Air Signature Pad - Pro", frame)
    if cv2.waitKey(5) & 0xFF == 27: break

vs.stop(); cv2.destroyAllWindows()