import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SimControlComponent } from './sim-control.component';
import { SimBridgeService } from '../../../../../core/sim-bridge/sim-bridge.service';
import { signal } from '@angular/core';
import { NO_ERRORS_SCHEMA } from '@angular/core';

function makeBridgeSpy() {
  return {
    status:         signal<any>('disconnected'),
    tick:           signal(0),
    totalTicks:     signal(0),
    currentEegTick: signal(null),
    joints:         signal<number[]>([]),
    launching:      signal(false),
    isCloudSim:     false,
    connect: jasmine.createSpy('connect'),
    pause:   jasmine.createSpy('pause'),
    resume:  jasmine.createSpy('resume'),
    stop:    jasmine.createSpy('stop'),
  };
}

describe('SimControlComponent', () => {
  let fixture: ComponentFixture<SimControlComponent>;
  let bridge: ReturnType<typeof makeBridgeSpy>;

  beforeEach(async () => {
    bridge = makeBridgeSpy();
    await TestBed.configureTestingModule({
      imports: [SimControlComponent],
      schemas: [NO_ERRORS_SCHEMA],
      providers: [{ provide: SimBridgeService, useValue: bridge }],
    }).compileComponents();
    fixture = TestBed.createComponent(SimControlComponent);
    fixture.detectChanges();
  });

  it('shows offline state when disconnected', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Sim offline');
  });

  it('hides playback controls when idle', () => {
    bridge.status.set('idle');
    fixture.detectChanges();
    const btns = fixture.nativeElement.querySelectorAll('[data-playback="true"]');
    expect(btns.length).toBe(0);
  });

  it('shows playback controls when replaying', () => {
    bridge.status.set('replaying');
    bridge.tick.set(10);
    bridge.totalTicks.set(100);
    fixture.detectChanges();
    const btns = fixture.nativeElement.querySelectorAll('[data-playback="true"]');
    expect(btns.length).toBeGreaterThan(0);
  });

  it('shows playback controls when paused', () => {
    bridge.status.set('paused');
    fixture.detectChanges();
    const btns = fixture.nativeElement.querySelectorAll('[data-playback="true"]');
    expect(btns.length).toBeGreaterThan(0);
  });

  it('calls bridge.pause() on pause button click', () => {
    bridge.status.set('replaying');
    bridge.tick.set(10);
    bridge.totalTicks.set(100);
    fixture.detectChanges();
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-pause"]');
    btn?.click();
    expect(bridge.pause).toHaveBeenCalled();
  });

  it('calls bridge.resume() on resume button click', () => {
    bridge.status.set('paused');
    fixture.detectChanges();
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-resume"]');
    btn?.click();
    expect(bridge.resume).toHaveBeenCalled();
  });

  it('calls bridge.stop() on stop button click', () => {
    bridge.status.set('replaying');
    bridge.tick.set(10);
    bridge.totalTicks.set(100);
    fixture.detectChanges();
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-stop"]');
    btn?.click();
    expect(bridge.stop).toHaveBeenCalled();
  });

  it('calls bridge.connect() on reconnect button click', () => {
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-reconnect"]');
    btn?.click();
    expect(bridge.connect).toHaveBeenCalled();
  });
});
