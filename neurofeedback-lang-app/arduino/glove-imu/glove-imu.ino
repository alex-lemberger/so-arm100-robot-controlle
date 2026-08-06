#include <ArduinoBLE.h>
#include <Arduino_LSM9DS1.h>

// Custom IMU service and notify characteristic UUIDs
#define SERVICE_UUID        "12345678-1234-1234-1234-123456789abc"
#define CHARACTERISTIC_UUID "12345678-1234-1234-1234-123456789abd"

// CHANGE THIS before flashing to the right-hand glove:
//   #define GLOVE_NAME "GloveRight"
#define GLOVE_NAME "GloveLeft"

BLEService imuService(SERVICE_UUID);
BLECharacteristic imuCharacteristic(CHARACTERISTIC_UUID, BLENotify, 12);

void setup() {
  Serial.begin(9600);

  if (!IMU.begin()) {
    Serial.println("IMU init failed");
    while (1);
  }

  if (!BLE.begin()) {
    Serial.println("BLE init failed");
    while (1);
  }

  BLE.setLocalName(GLOVE_NAME);
  BLE.setAdvertisedService(imuService);
  imuService.addCharacteristic(imuCharacteristic);
  BLE.addService(imuService);
  BLE.advertise();

  Serial.print("BLE advertising as: ");
  Serial.println(GLOVE_NAME);
}

void loop() {
  BLE.poll();

  if (IMU.accelerationAvailable() && IMU.gyroscopeAvailable()) {
    float ax, ay, az, gx, gy, gz;
    IMU.readAcceleration(ax, ay, az);
    IMU.readGyroscope(gx, gy, gz);

    // Pack as 6 × Int16 little-endian, scaled ×100
    uint8_t packet[12];
    int16_t values[6] = {
      (int16_t)(ax * 100),
      (int16_t)(ay * 100),
      (int16_t)(az * 100),
      (int16_t)(gx * 100),
      (int16_t)(gy * 100),
      (int16_t)(gz * 100),
    };
    memcpy(packet, values, 12);
    imuCharacteristic.writeValue(packet, 12);
  }

  delay(20); // ~50 Hz
}
