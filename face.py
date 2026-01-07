import serial
import serial.tools.list_ports
import time
import json
import os
import cv2
import face_recognition

FACES_DIR = "registered_faces"

# ===================== AUTO PORT DETECTION =====================
def find_esp32_port():
    print("🔌 Searching for ESP32...")
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "USB" in port.description or "Silicon" in port.description or "CH340" in port.description:
            print(f"✅ Found ESP32 on {port.device}")
            return port.device
    print("❌ No ESP32 detected. Please check your connection.")
    return None


# ===================== SERIAL CONNECTION =====================
def connect_esp32():
    port = find_esp32_port()
    if not port:
        exit(1)
    try:
        esp = serial.Serial(port, 115200, timeout=1)
        time.sleep(2)
        print("✅ ESP32 connected successfully.")
        print("📡 Waiting for READY signal from ESP32...")
        start_time = time.time()
        while time.time() - start_time < 8:
            if esp.in_waiting:
                line = esp.readline().decode(errors='ignore').strip()
                if "READY" in line:
                    print("🟢 ESP32 Ready! You can scan your card now.\n")
                    return esp
        print("⚠️ No READY signal — continuing anyway...")
        return esp
    except Exception as e:
        print(f"❌ Could not connect to ESP32: {e}")
        exit(1)


# ===================== FACE RECOGNITION SETUP =====================
known_encodings = {}
for file in os.listdir(FACES_DIR):
    if file.lower().endswith((".jpg", ".jpeg", ".png")):
        face_id = os.path.splitext(file)[0]  # e.g. "9E"
        image_path = os.path.join(FACES_DIR, file)
        image = face_recognition.load_image_file(image_path)

        # Ensure correct format
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)

        encs = face_recognition.face_encodings(image)
        if encs:
            known_encodings[face_id] = encs[0]
            print(f"✅ Loaded face data for {face_id}")
        else:
            print(f"⚠️ Warning: No face detected in {file}")


def verify_face(prefix):
    print(f"🔍 Verifying face for card prefix {prefix}")
    cap = cv2.VideoCapture(0)
    start = time.time()
    verified = False

    while time.time() - start < 10:  # 10 seconds max
        ret, frame = cap.read()
        if not ret:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        encs = face_recognition.face_encodings(rgb)

        if encs and prefix in known_encodings:
            dist = face_recognition.face_distance([known_encodings[prefix]], encs[0])[0]
            if dist < 0.5:
                verified = True
                break

        cv2.imshow("Face Verification", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    return verified


# ===================== VOTE DATABASE =====================
VOTE_FILE = "votes.json"

def load_votes():
    if os.path.exists(VOTE_FILE):
        with open(VOTE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_votes(votes):
    with open(VOTE_FILE, "w") as f:
        json.dump(votes, f, indent=4)


# ===================== MAIN LOGIC =====================
def main():
    esp = connect_esp32()
    votes = load_votes()
    print("🗳️ System ready — waiting for voter...")

    last_prompt = time.time()
    uid = None

    while True:
        try:
            # Prompt every few seconds
            if time.time() - last_prompt > 5:
                print("🕹️ Please scan your card now...")
                last_prompt = time.time()

            if esp.in_waiting > 0:
                line = esp.readline().decode(errors='ignore').strip()
                if not line:
                    continue

                # --- CARD DETECTED ---
                if line.startswith("CHECK:"):
                    uid = line.split(":")[1].strip()
                    prefix = uid[:2]  # first two letters
                    print(f"\n💳 Card detected: {uid} (prefix: {prefix})")

                    allowed_prefixes = ["9E", "22"]

                    # Check prefix validity
                    if prefix not in allowed_prefixes:
                        print(f"🚫 Unauthorized card prefix ({prefix}) — access denied.")
                        esp.write(b"DENY\n")
                        
                        continue

                    # Check if already voted
                    if uid in votes:
                        print(f"🚫 Card {uid} has already voted — access denied.")
                        esp.write(b"DENY\n")
                        continue

                    # Face verification
                    print(f"✅ Authorized prefix '{prefix}' — verifying face...")
                    if verify_face(prefix):
                        esp.write(b"ALLOW\n")
                        print("🟢 Face verified. Waiting for vote...")
                    else:
                        esp.write(b"DENY\n")
                        print("❌ Face verification failed.")

                # --- BUTTON VOTE ---
                elif line.startswith("VOTE:"):
                    candidate = line.split(":")[1]
                    if not uid:
                        print("⚠️ Error: UID missing before vote.")
                        continue

                    print(f"✅ Vote stored: Candidate {candidate}")
                    esp.write(b"STORE\n")
                    time.sleep(0.5)
                    esp.write(b"CLEAR\n")

                    votes[uid] = candidate
                    save_votes(votes)
                    print("🔒 Waiting for next voter...\n")

                elif "READY" in line:
                    print("📡 ESP32 Ready signal received — you can scan a card now!\n")

        except KeyboardInterrupt:
            print("\n🛑 Exiting system safely...")
            esp.close()
            break
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(1)


# ===================== RUN =====================
if __name__ == "__main__":
    main()
