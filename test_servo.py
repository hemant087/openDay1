import serial
import time
import sys

# Change this to match your Arduino's COM port
ARDUINO_PORT = "COM4"
BAUD_RATE = 9600

def test_servo():
    print(f"Connecting to Arduino on {ARDUINO_PORT} at {BAUD_RATE} baud...")
    try:
        # Establish serial connection
        ser = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
        
        # Give Arduino time to auto-reset after serial connection is opened
        print("Waiting 2 seconds for Arduino to initialize...")
        time.sleep(2)
        print("Connected successfully!\n")
        
        # Read any startup messages (like "ROBOGREET_READY")
        while ser.in_waiting > 0:
            msg = ser.readline().decode('utf-8').strip()
            if msg:
                print(f"[Arduino Startup]: {msg}")
                
    except serial.SerialException as e:
        print(f"\n[ERROR] Failed to connect to {ARDUINO_PORT}")
        print(f"Details: {e}")
        print("Please check your COM port in Windows Device Manager and update the ARDUINO_PORT variable at the top of this script.")
        sys.exit(1)

    print("\n" + "="*30)
    print("      SERVO TEST MENU")
    print("="*30)
    print("Type a command and press Enter to send it to the Arduino.")
    print("Available commands:")
    print("  WAVE     - Robot raises arm and waves 3 times")
    print("  IDLE     - Returns arm to the home position")
    print("  DANCE    - Arm goes up and down rhythmically")
    print("  EXCITED  - Fast flapping motion")
    print("  EYES_ON  - Turns on the LED eyes")
    print("  EYES_OFF - Turns off the LED eyes")
    print("  quit     - Exit this test program")
    print("="*30 + "\n")

    try:
        while True:
            cmd = input("Enter command: ").strip().upper()
            
            if cmd in ['EXIT', 'QUIT']:
                print("Closing connection...")
                break
            
            if cmd:
                print(f"--> Sending: {cmd}")
                
                # Send the command with a newline character as expected by Arduino's readStringUntil('\n')
                ser.write((cmd + '\n').encode('utf-8'))
                
                # Wait a moment for Arduino to process and send acknowledgment
                time.sleep(0.5)
                
                # Read any response/acknowledgment from Arduino
                while ser.in_waiting > 0:
                    response = ser.readline().decode('utf-8').strip()
                    if response:
                        print(f"<-- Arduino replied: {response}")
                        
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial connection closed.")

if __name__ == "__main__":
    test_servo()
