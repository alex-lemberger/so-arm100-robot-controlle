import { fakeAsync, tick } from '@angular/core/testing';
import { BrainDevice } from '../brain-device';
import { MockNeurosityService } from './mock-neurosity.service';

const VALID = { email: 'test@example.com', password: 'password123' };

describe('MockNeurosityService', () => {
  it('satisfies the BrainDevice contract', () => {
    const device: BrainDevice = new MockNeurosityService();
    expect(device).toBeTruthy();
    expect(typeof device.connect).toBe('function');
    expect(typeof device.disconnect).toBe('function');
  });

  it('connect() with valid credentials starts focus/calm stream', fakeAsync(() => {
    const device = new MockNeurosityService();
    device.connect(VALID);
    tick(1000); // resolve the simulated login delay
    tick(1000); // first metrics interval tick
    expect(device.focus$.value).not.toBeNull();
    expect(device.calm$.value).not.toBeNull();
    device.disconnect();
    tick(500);
  }));

  it('connect() rejects invalid credentials', fakeAsync(() => {
    const device = new MockNeurosityService();
    let rejected = false;
    device.connect({ email: 'x', password: 'y' }).catch(() => (rejected = true));
    tick(1000);
    expect(rejected).toBeTrue();
  }));

  it('disconnect() nulls focus/calm', fakeAsync(() => {
    const device = new MockNeurosityService();
    device.connect(VALID);
    tick(2000);
    device.disconnect();
    tick(500);
    expect(device.focus$.value).toBeNull();
    expect(device.calm$.value).toBeNull();
  }));

  it('disconnect() stops the stream — values stay null after further ticks', fakeAsync(() => {
    const device = new MockNeurosityService();
    device.connect(VALID);
    tick(2000);
    device.disconnect();
    tick(500);   // disconnect resolves, nulls values
    tick(5000);  // several more interval periods elapse
    expect(device.focus$.value).toBeNull();
    expect(device.calm$.value).toBeNull();
  }));

  it('emits focus and calm within the 0–1 BrainDevice contract', fakeAsync(() => {
    const service = new MockNeurosityService();
    service.connect(VALID);
    tick(1000); // resolve the simulated login delay
    tick(1000); // first metrics interval tick
    const focus = service.focus$.value;
    const calm = service.calm$.value;
    expect(focus).not.toBeNull();
    expect(focus!).toBeGreaterThanOrEqual(0);
    expect(focus!).toBeLessThanOrEqual(1);
    expect(calm!).toBeGreaterThanOrEqual(0);
    expect(calm!).toBeLessThanOrEqual(1);
    service.disconnect();
    tick(500);
  }));
});
