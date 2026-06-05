#include <Servo.h>
#include <SoftwareSerial.h>

// ---------------- Pins ----------------
#define LEFT_ARM_PIN   9
#define RIGHT_ARM_PIN  10

#define BT_RX_PIN      2
#define BT_TX_PIN      3

SoftwareSerial btSerial(BT_RX_PIN, BT_TX_PIN);

Servo leftArm;
Servo rightArm;

// ---------------- Teddy Calibration ----------------
const int L_HOME   = 20;
const int L_OPEN   = 5;
const int L_CLOSE  = 50;

const int R_HOME   = 160;
const int R_OPEN   = 175;
const int R_CLOSE  = 130;

// Natural wave
const int L_WAVE_A = 15;
const int L_WAVE_B = 35;

const int R_WAVE_A = 165;
const int R_WAVE_B = 145;

String usbBuffer = "";
String btBuffer  = "";

// --------------------------------------------------
void sendBoth(const String &msg) {
  Serial.println(msg);
  btSerial.println(msg);
}

// --------------------------------------------------
void setup() {

  Serial.begin(9600);
  btSerial.begin(9600);

  leftArm.attach(LEFT_ARM_PIN);
  rightArm.attach(RIGHT_ARM_PIN);

  goIdle();

  sendBoth("TEDDY_READY");
}

// --------------------------------------------------
void loop() {

  // USB Serial
  while (Serial.available()) {

    char c = Serial.read();

    if (c == '\n') {

      usbBuffer.trim();

      if (usbBuffer.length() > 0)
        executeCommand(usbBuffer);

      usbBuffer = "";
    }
    else {
      usbBuffer += c;
    }
  }

  // Bluetooth
  while (btSerial.available()) {

    char c = btSerial.read();

    if (c == '\n') {

      btBuffer.trim();

      if (btBuffer.length() > 0)
        executeCommand(btBuffer);

      btBuffer = "";
    }
    else {
      btBuffer += c;
    }
  }
}

// --------------------------------------------------
void executeCommand(String cmd) {

  cmd.toUpperCase();

  if (cmd == "WAVE") {

    sendBoth("ACK:WAVE");
    waveAnimation();
  }

  else if (cmd == "IDLE") {

    sendBoth("ACK:IDLE");
    goIdle();
  }

  else if (cmd == "DANCE") {

    sendBoth("ACK:DANCE");
    danceAnimation();
  }

  else if (cmd == "EXCITED") {

    sendBoth("ACK:EXCITED");
    excitedAnimation();
  }

  else if (cmd == "SPEAK") {

    sendBoth("ACK:SPEAK");
    speakAnimation();
  }

  else {

    sendBoth("ERR:UNKNOWN:" + cmd);
  }
}

// --------------------------------------------------
void moveServo(Servo &servo, int from, int to, int speedDelay) {

  if (from < to) {

    for (int pos = from; pos <= to; pos++) {

      servo.write(pos);
      delay(speedDelay);
    }
  }
  else {

    for (int pos = from; pos >= to; pos--) {

      servo.write(pos);
      delay(speedDelay);
    }
  }
}

// --------------------------------------------------
void goIdle() {

  leftArm.write(L_HOME);
  rightArm.write(R_HOME);
}

// --------------------------------------------------
void waveAnimation() {

  leftArm.write(L_HOME);
  rightArm.write(R_HOME);

  delay(300);

  for (int i = 0; i < 3; i++) {

    leftArm.write(L_WAVE_A);
    rightArm.write(R_WAVE_A);
    delay(400);

    leftArm.write(L_WAVE_B);
    rightArm.write(R_WAVE_B);
    delay(400);
  }

  goIdle();
}

// --------------------------------------------------
void excitedAnimation() {

  for (int i = 0; i < 8; i++) {

    leftArm.write(L_OPEN);
    rightArm.write(R_OPEN);
    delay(120);

    leftArm.write(45);
    rightArm.write(135);
    delay(120);
  }

  goIdle();
}

// --------------------------------------------------
void danceAnimation() {

  for (int i = 0; i < 6; i++) {

    leftArm.write(L_OPEN);
    rightArm.write(R_CLOSE);
    delay(250);

    leftArm.write(L_CLOSE);
    rightArm.write(R_OPEN);
    delay(250);
  }

  goIdle();
}

// --------------------------------------------------
void speakAnimation() {

  leftArm.write(25);
  rightArm.write(155);
  delay(250);

  leftArm.write(35);
  rightArm.write(145);
  delay(250);

  leftArm.write(20);
  rightArm.write(160);
  delay(200);

  leftArm.write(30);
  rightArm.write(150);
  delay(250);

  goIdle();
}