// src/app/modules/capture/services/supabase-capture.service.spec.ts
import { SupabaseCaptureService } from './supabase-capture.service';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';

function makeSupabaseClient(overrides: Partial<any> = {}) {
  const fromResult = {
    insert: jasmine.createSpy('insert').and.returnValue(Promise.resolve({ error: null })),
    update: jasmine.createSpy('update').and.returnValue({ eq: jasmine.createSpy('eq').and.returnValue(Promise.resolve({ error: null })) }),
    delete: jasmine.createSpy('delete').and.returnValue({ eq: jasmine.createSpy('eq').and.returnValue(Promise.resolve({ error: null })) }),
  };
  const storageResult = {
    upload: jasmine.createSpy('upload').and.returnValue(Promise.resolve({ error: null })),
    list: jasmine.createSpy('list').and.returnValue(Promise.resolve({ data: [] })),
    remove: jasmine.createSpy('remove').and.returnValue(Promise.resolve({ error: null })),
  };
  return {
    from: jasmine.createSpy('from').and.returnValue(fromResult),
    storage: {
      from: jasmine.createSpy('storageFrom').and.returnValue(storageResult),
    },
    _fromResult: fromResult,
    _storageResult: storageResult,
    ...overrides,
  };
}

function makeService(clientOverrides?: Partial<any>): { service: SupabaseCaptureService; mockClient: any } {
  const mockClient = makeSupabaseClient(clientOverrides);
  const mockSupabase = { client: mockClient } as unknown as SupabaseClientService;
  const service = new SupabaseCaptureService(mockSupabase);
  return { service, mockClient };
}

describe('SupabaseCaptureService', () => {
  describe('startSession', () => {
    it('inserts a capture row and returns a UUID', async () => {
      const { service, mockClient } = makeService();

      const id = await service.startSession('worker-1', 'welding', 'Weld frame joint', 'shop-01', '1.0');

      expect(mockClient.from).toHaveBeenCalledWith('captures');
      expect(mockClient._fromResult.insert).toHaveBeenCalledWith(
        jasmine.objectContaining({
          worker_id: 'worker-1',
          task_type: 'welding',
          task_label: 'Weld frame joint',
          shop_id: 'shop-01',
          consent_version: '1.0',
          status: 'recording',
          eeg_tick_count: 0,
        }),
      );
      expect(typeof id).toBe('string');
      expect(id.length).toBe(36); // UUID format
    });

    it('throws when Supabase returns an error', async () => {
      const { service, mockClient } = makeService();
      mockClient._fromResult.insert.and.returnValue(Promise.resolve({ error: { message: 'network error' } }));

      await expectAsync(
        service.startSession('w', 'welding', 'label', 'shop', '1.0'),
      ).toBeRejectedWithError('network error');
    });
  });

  describe('writeEegTick', () => {
    it('inserts an eeg_ticks row fire-and-forget', (done) => {
      const { service, mockClient } = makeService();

      service.writeEegTick('session-1', 0.8, 0.6, true, null, null, null);

      setTimeout(() => {
        expect(mockClient.from).toHaveBeenCalledWith('eeg_ticks');
        expect(mockClient._fromResult.insert).toHaveBeenCalledWith(
          jasmine.objectContaining({ session_id: 'session-1', focus: 0.8, calm: 0.6, in_flow: true }),
        );
        done();
      }, 10);
    });
  });

  describe('updateSession', () => {
    it('calls update on captures table with patch', async () => {
      const { service, mockClient } = makeService();

      await service.updateSession('session-1', { status: 'uploading' });

      expect(mockClient.from).toHaveBeenCalledWith('captures');
      expect(mockClient._fromResult.update).toHaveBeenCalledWith({ status: 'uploading' });
    });
  });

  describe('fetchEegTicks', () => {
    function makeEegClient(resolvedValue: { data: any; error: any }) {
      const eqSpy = jasmine.createSpy('eq').and.returnValue(Promise.resolve(resolvedValue));
      const selectSpy = jasmine.createSpy('select').and.returnValue({ eq: eqSpy });
      const fromSpy = jasmine.createSpy('from').and.returnValue({ select: selectSpy });
      const svc = new (SupabaseCaptureService as any)({ client: { from: fromSpy, storage: { from: jasmine.createSpy() } } });
      return { svc, fromSpy, selectSpy, eqSpy };
    }

    it('returns rows with in_flow mapped to inFlow', async () => {
      const rows = [
        { focus: 0.8, calm: 0.6, in_flow: true, load: 0.4, fatigue: 0.2 },
        { focus: 0.5, calm: 0.7, in_flow: false, load: null, fatigue: null },
      ];
      const { svc, fromSpy, selectSpy, eqSpy } = makeEegClient({ data: rows, error: null });

      const result = await svc.fetchEegTicks('sess-1');

      expect(fromSpy).toHaveBeenCalledWith('eeg_ticks');
      expect(selectSpy).toHaveBeenCalledWith('focus, calm, in_flow, load, fatigue');
      expect(eqSpy).toHaveBeenCalledWith('session_id', 'sess-1');
      expect(result).toEqual([
        { focus: 0.8, calm: 0.6, inFlow: true, load: 0.4, fatigue: 0.2 },
        { focus: 0.5, calm: 0.7, inFlow: false, load: null, fatigue: null },
      ]);
    });

    it('throws when Supabase returns an error', async () => {
      const { svc } = makeEegClient({ data: null, error: { message: 'query failed' } });
      await expectAsync(svc.fetchEegTicks('sess-1')).toBeRejectedWithError('query failed');
    });
  });

  describe('deleteSession', () => {
    it('removes storage objects then deletes the session row', async () => {
      const { service, mockClient } = makeService();
      mockClient._storageResult.list.and.returnValue(Promise.resolve({
        data: [{ name: 'video.webm' }, { name: 'imu_left.bin' }],
      }));

      await service.deleteSession('session-1');

      expect(mockClient._storageResult.list).toHaveBeenCalledWith('session-1');
      expect(mockClient._storageResult.remove).toHaveBeenCalledWith([
        'session-1/video.webm',
        'session-1/imu_left.bin',
      ]);
      expect(mockClient._fromResult.delete).toHaveBeenCalled();
    });
  });
});