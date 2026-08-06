import { SimBridgeService, SimReplayPayload } from './sim-bridge.service';

function makeWsMock(): jasmine.SpyObj<WebSocket> & { readyState: number } {
  const ws = jasmine.createSpyObj<WebSocket>('WebSocket', ['send', 'close']);
  (ws as any).readyState = WebSocket.CONNECTING;
  return ws as any;
}

describe('SimBridgeService', () => {
  let service: SimBridgeService;
  let wsMock: ReturnType<typeof makeWsMock>;

  beforeEach(() => {
    wsMock = makeWsMock();
    spyOn(window, 'WebSocket').and.returnValue(wsMock as any);
    service = new SimBridgeService();
    service.connect();
    // Simulate open
    (wsMock as any).readyState = WebSocket.OPEN;
    wsMock.onopen?.({} as Event);
  });

  afterEach(() => service.disconnect());

  it('status is disconnected before connect', () => {
    const fresh = new SimBridgeService();
    expect(fresh.status()).toBe('disconnected');
  });

  it('status becomes idle on open + idle message', () => {
    wsMock.onmessage?.({ data: JSON.stringify({ status: 'idle', tick: 0, totalTicks: 0, q: [], eegTick: null }) } as MessageEvent);
    expect(service.status()).toBe('idle');
  });

  it('status becomes replaying on replaying message', () => {
    wsMock.onmessage?.({ data: JSON.stringify({ status: 'replaying', tick: 5, totalTicks: 100, q: [], eegTick: { focus: 0.8, calm: 0.6, load: 0.3, fatigue: 0.2, inFlow: true } }) } as MessageEvent);
    expect(service.status()).toBe('replaying');
    expect(service.tick()).toBe(5);
    expect(service.totalTicks()).toBe(100);
    expect(service.currentEegTick()?.inFlow).toBeTrue();
  });

  it('transferSession sends replay command with payload', () => {
    const payload: SimReplayPayload = {
      sessionId: 'sess-1',
      taskLabel: 'Plastering',
      durationMs: 5000,
      eegTicks: [{ focus: 0.7, calm: 0.6, load: 0.3, fatigue: 0.2, inFlow: false }],
    };
    service.transferSession(payload);
    expect(wsMock.send).toHaveBeenCalledOnceWith(JSON.stringify({ cmd: 'replay', ...payload }));
  });

  it('pause/resume/stop send correct commands', () => {
    service.pause();
    expect(wsMock.send).toHaveBeenCalledWith(JSON.stringify({ cmd: 'pause' }));
    service.resume();
    expect(wsMock.send).toHaveBeenCalledWith(JSON.stringify({ cmd: 'resume' }));
    service.stop();
    expect(wsMock.send).toHaveBeenCalledWith(JSON.stringify({ cmd: 'stop' }));
  });

  it('status becomes disconnected after WS close', () => {
    wsMock.onclose?.({} as CloseEvent);
    expect(service.status()).toBe('disconnected');
  });

  it('does not send when not open', () => {
    (wsMock as any).readyState = WebSocket.CLOSED;
    service.pause();
    expect(wsMock.send).not.toHaveBeenCalled();
  });

  describe('reconnect', () => {
    let wsMock2: ReturnType<typeof makeWsMock>;

    beforeEach(() => {
      jasmine.clock().install();
      wsMock2 = makeWsMock();
      (window.WebSocket as jasmine.Spy).and.returnValue(wsMock2 as any);
    });

    afterEach(() => {
      jasmine.clock().uninstall();
    });

    it('retries connect after 3s on unexpected close', () => {
      wsMock.onclose?.({} as CloseEvent);
      expect(service.status()).toBe('disconnected');
      // WebSocket was called once in beforeEach; no retry yet
      expect(window.WebSocket).toHaveBeenCalledTimes(1);
      jasmine.clock().tick(3000);
      expect(window.WebSocket).toHaveBeenCalledTimes(2);
    });

    it('stops retrying after max 3 attempts', () => {
      const wsMocks = [makeWsMock(), makeWsMock(), makeWsMock()];
      let callIdx = 0;
      (window.WebSocket as jasmine.Spy).and.callFake(() => {
        const m = wsMocks[callIdx++];
        return m;
      });

      wsMock.onclose?.({} as CloseEvent);
      for (let i = 0; i < 3; i++) {
        jasmine.clock().tick(3000);
        wsMocks[i]?.onclose?.({} as CloseEvent);
      }
      // 3 retries exhausted — no further reconnect after another tick
      const calls = (window.WebSocket as jasmine.Spy).calls.count();
      jasmine.clock().tick(3000);
      expect((window.WebSocket as jasmine.Spy).calls.count()).toBe(calls);
      expect(service.status()).toBe('disconnected');
    });
  });
});
