import { ImuService } from './imu.service';

/** Build a 12-byte DataView simulating an Arduino IMU packet. */
function makePacket(ax: number, ay: number, az: number,
                    gx: number, gy: number, gz: number): DataView {
  const buf = new ArrayBuffer(12);
  const view = new DataView(buf);
  view.setInt16(0,  Math.round(ax * 100), true);
  view.setInt16(2,  Math.round(ay * 100), true);
  view.setInt16(4,  Math.round(az * 100), true);
  view.setInt16(6,  Math.round(gx * 100), true);
  view.setInt16(8,  Math.round(gy * 100), true);
  view.setInt16(10, Math.round(gz * 100), true);
  return view;
}

/** Fake BluetoothRemoteGATTCharacteristic with a settable value. */
function fakeCharacteristicEvent(view: DataView): Event {
  const target = { value: view } as unknown as EventTarget;
  return { target } as unknown as Event;
}

describe('ImuService — parseFrame', () => {
  let service: ImuService;

  beforeEach(() => {
    service = new ImuService();
    // Expose parseFrame for direct testing
    (service as any).sessionStart = 0;
  });

  it('parses positive accel and gyro values correctly', () => {
    const frame = (service as any).parseFrame(
      fakeCharacteristicEvent(makePacket(1.23, 4.56, 7.89, 10.11, 12.13, 14.15)),
      'left'
    );
    expect(frame.ax).toBeCloseTo(1.23, 1);
    expect(frame.ay).toBeCloseTo(4.56, 1);
    expect(frame.az).toBeCloseTo(7.89, 1);
    expect(frame.gx).toBeCloseTo(10.11, 1);
    expect(frame.gy).toBeCloseTo(12.13, 1);
    expect(frame.gz).toBeCloseTo(14.15, 1);
  });

  it('parses negative values correctly', () => {
    const frame = (service as any).parseFrame(
      fakeCharacteristicEvent(makePacket(-1.0, -2.0, -3.0, -4.0, -5.0, -6.0)),
      'left'
    );
    expect(frame.ax).toBeCloseTo(-1.0, 1);
    expect(frame.gz).toBeCloseTo(-6.0, 1);
  });

  it('assigns t as offset from sessionStart', () => {
    (service as any).sessionStart = Date.now() - 500;
    const frame = (service as any).parseFrame(
      fakeCharacteristicEvent(makePacket(0, 0, 0, 0, 0, 0)),
      'left'
    );
    expect(frame.t).toBeGreaterThanOrEqual(490);
    expect(frame.t).toBeLessThan(600);
  });
});

describe('ImuService — recording', () => {
  let service: ImuService;

  beforeEach(() => {
    service = new ImuService();
  });

  it('ignores frames before startRecording()', () => {
    const evt = fakeCharacteristicEvent(makePacket(1, 2, 3, 4, 5, 6));
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    expect(result.left.length).toBe(0);
  });

  it('accumulates left frames only while recording', () => {
    service.startRecording(Date.now());
    const evt = fakeCharacteristicEvent(makePacket(1, 2, 3, 4, 5, 6));
    (service as any).onCharacteristicChanged(evt, 'left');
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    // 2 frames × 7 floats = 14
    expect(result.left.length).toBe(14);
    expect(result.right.length).toBe(0);
  });

  it('stopRecording() produces correct Float32Array layout per frame', () => {
    service.startRecording(0);
    const evt = fakeCharacteristicEvent(makePacket(1.0, 2.0, 3.0, 4.0, 5.0, 6.0));
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    // t=0 index, ax=1 index, ay=2, az=3, gx=4, gy=5, gz=6
    expect(result.left[1]).toBeCloseTo(1.0, 1); // ax
    expect(result.left[2]).toBeCloseTo(2.0, 1); // ay
    expect(result.left[6]).toBeCloseTo(6.0, 1); // gz
  });

  it('does not accumulate frames after stopRecording()', () => {
    service.startRecording(Date.now());
    service.stopRecording();
    const evt = fakeCharacteristicEvent(makePacket(1, 2, 3, 4, 5, 6));
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    expect(result.left.length).toBe(0);
  });
});

describe('ImuService — error$ and reconnect', () => {
  let service: ImuService;
  let mockBluetooth: jasmine.SpyObj<Bluetooth>;
  let mockDevice: any;
  let mockServer: any;
  let mockCharacteristic: any;

  beforeEach(() => {
    mockCharacteristic = {
      startNotifications: jasmine.createSpy().and.returnValue(Promise.resolve()),
      addEventListener:   jasmine.createSpy(),
    };
    mockServer = {
      connected:         true,
      getPrimaryService: jasmine.createSpy().and.returnValue(Promise.resolve({
        getCharacteristic: jasmine.createSpy().and.returnValue(Promise.resolve(mockCharacteristic)),
      })),
      disconnect:        jasmine.createSpy(),
    };
    mockDevice = {
      gatt:             mockServer,
      addEventListener: jasmine.createSpy(),
    };
    mockServer.connect = jasmine.createSpy().and.returnValue(Promise.resolve(mockServer));
    mockDevice.gatt.connect = jasmine.createSpy().and.returnValue(Promise.resolve(mockServer));

    mockBluetooth = jasmine.createSpyObj('Bluetooth', ['requestDevice']);
    mockBluetooth.requestDevice.and.returnValue(Promise.resolve(mockDevice));
    Object.defineProperty(navigator, 'bluetooth', {
      value: mockBluetooth, writable: true, configurable: true,
    });

    service = new ImuService();
  });

  it('error$ starts empty', () => {
    expect(service.error$.value).toEqual({});
  });

  it('NotFoundError on requestDevice leaves connected state false and does not throw', async () => {
    mockBluetooth.requestDevice.and.returnValue(
      Promise.reject(Object.assign(new Error('User cancelled'), { name: 'NotFoundError' }))
    );
    await expectAsync(service.connect('left')).toBeResolved();
    expect(service.error$.value['left']).toBeUndefined();
  });

  it('connect() clears error$ for the hand on success', async () => {
    service['error$'].next({ left: 'Connection lost' });
    await service.connect('left');
    expect(service.error$.value['left']).toBeNull();
  });

  it('onDisconnected sets error$ and emits false on leftConnected$ when reconnect fails', async () => {
    await service.connect('left');
    mockDevice.gatt.connect.and.returnValue(Promise.reject(new Error('BT gone')));

    let connected: boolean | undefined;
    service.leftConnected$.subscribe(v => connected = v);

    await (service as any).onDisconnected('left', mockDevice);

    expect(connected).toBe(false);
    expect(service.error$.value['left']).toBe('Connection lost');
  });
});
