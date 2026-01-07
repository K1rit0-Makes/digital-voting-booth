/* ESP32 - RFID + Buttons + LEDs
   Pin mapping (match your wiring):
     RC522 SDA(SS) -> GPIO5
     RC522 SCK     -> GPIO18
     RC522 MOSI    -> GPIO23
     RC522 MISO    -> GPIO19
     RC522 RST     -> GPIO22
     RC522 VCC     -> 3.3V
     RC522 GND     -> GND

     LED_ALLOW -> GPIO26
     LED_DENY  -> GPIO27
     LED_STORE -> GPIO25

     BUTTON1 -> GPIO14  (to GND)
     BUTTON2 -> GPIO12  (to GND)
*/

#include <SPI.h>
#include <MFRC522.h>

#define SS_PIN 5
#define RST_PIN 22

#define BTN1 14
#define BTN2 12

#define LED_ALLOW 26
#define LED_DENY 27
#define LED_STORE 25

MFRC522 rfid(SS_PIN, RST_PIN);

String lastUID = "";
bool waitingForFace = false;
bool votingEnabled = false;
unsigned long faceWaitStart = 0;
const unsigned long FACE_TIMEOUT = 15000; // 15s safety timeout

void setup() {
  Serial.begin(115200);
  // Explicit SPI pins: SCK, MISO, MOSI
  SPI.begin(18, 19, 23);
  rfid.PCD_Init();
  delay(50);

  pinMode(BTN1, INPUT_PULLUP);
  pinMode(BTN2, INPUT_PULLUP);

  pinMode(LED_ALLOW, OUTPUT);
  pinMode(LED_DENY, OUTPUT);
  pinMode(LED_STORE, OUTPUT);

  digitalWrite(LED_ALLOW, LOW);
  digitalWrite(LED_DENY, LOW);
  digitalWrite(LED_STORE, LOW);

  Serial.println("READY"); // handshake for Python
}

void loop() {
  // Read incoming serial commands from Python
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    if (msg == "ENABLE_VOTING") {
      // optional: allow Python to enable scanning mode (not required, we scan by default)
      waitingForFace = false;
      votingEnabled = false;
      Serial.println("ENABLED");
    }
    else if (msg == "ALLOW") {
      digitalWrite(LED_ALLOW, HIGH);
      digitalWrite(LED_DENY, LOW);
      votingEnabled = true;
      waitingForFace = false;
      Serial.println("ALLOWED");
    }
    else if (msg == "DENY") {
      digitalWrite(LED_DENY, HIGH);
      digitalWrite(LED_ALLOW, LOW);
      // short deny blink
      delay(700);
      digitalWrite(LED_DENY, LOW);
      waitingForFace = false;
      Serial.println("DENIED");
      // tell Python/host we are ready for next card
      Serial.println("READY");
    }
    else if (msg == "RESET_CARD") {
      // Full reset to allow scanning again
      digitalWrite(LED_ALLOW, LOW);
      digitalWrite(LED_DENY, LOW);
      digitalWrite(LED_STORE, LOW);
      votingEnabled = false;
      waitingForFace = false;
      lastUID = "";
      Serial.println("RESET_CARD");
      Serial.println("READY");
    }
    else if (msg == "STORE") {
      // Python tells us vote stored: latch LED_STORE
      digitalWrite(LED_STORE, HIGH);
      Serial.println("STORED");
    }
    else if (msg == "CLEAR") {
      // Python tells us to clear latch and reset
      digitalWrite(LED_STORE, LOW);
      digitalWrite(LED_ALLOW, LOW);
      votingEnabled = false;
      waitingForFace = false;
      lastUID = "";
      Serial.println("RESET_CARD");
      Serial.println("READY");
    }
  }

  // Safety timeout: if we waited too long for face verification, reset
  if (waitingForFace && (millis() - faceWaitStart > FACE_TIMEOUT)) {
    waitingForFace = false;
    votingEnabled = false;
    Serial.println("TIMEOUT");
    Serial.println("READY");
  }

  // RFID scanning: only scan when not waiting for face and not currently voting
  if (!waitingForFace && !votingEnabled) {
    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
      // Build UID string as hex pairs (no colons), e.g. 9E863AAA => '9E863AAA'
      String UID = "";
      for (byte i = 0; i < rfid.uid.size; i++) {
        byte b = rfid.uid.uidByte[i];
        if (b < 0x10) UID += "0";
        UID += String(b, HEX);
      }
      UID.toUpperCase();
      // send check to Python
      Serial.print("CHECK:");
      Serial.println(UID);
      waitingForFace = true;
      faceWaitStart = millis();
      // Halt and stop crypto to be clean
      rfid.PICC_HaltA();
      rfid.PCD_StopCrypto1();
    }
  }

  // Voting buttons: only if ALLOW received (votingEnabled)
  if (votingEnabled) {
    if (digitalRead(BTN1) == LOW) {
      delay(50); // debounce
      if (digitalRead(BTN1) == LOW) {
        Serial.println("VOTE:1");
        votingEnabled = false;
        // do not reset lastUID here; Python will send STORE/CLEAR then RESET_CARD
        delay(300);
      }
    }
    if (digitalRead(BTN2) == LOW) {
      delay(50); // debounce
      if (digitalRead(BTN2) == LOW) {
        Serial.println("VOTE:2");
        votingEnabled = false;
        delay(300);
      }
    }
  }
}
