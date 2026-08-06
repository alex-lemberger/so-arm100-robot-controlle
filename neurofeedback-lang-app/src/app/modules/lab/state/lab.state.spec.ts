import { LabState } from './lab.state';

function fakeApi(overrides: Partial<any> = {}): any {
  return {
    getStatus: jasmine.createSpy().and.resolveTo({
      data_dir: '/d', tiers: { raw: { count: 1 }, processed: { count: 0 }, releases: { count: 0 } },
      policy: { present: false }, running_job: null,
    }),
    listJobs: jasmine.createSpy().and.resolveTo([]),
    startJob: jasmine.createSpy().and.resolveTo('job-9'),
    cancelJob: jasmine.createSpy().and.resolveTo(true),
    jobLogs: jasmine.createSpy(),
    ...overrides,
  };
}

describe('LabState', () => {
  it('refresh populates status and marks online', async () => {
    const state = new LabState(fakeApi());
    await state.refresh();
    expect(state.status()?.tiers.raw.count).toBe(1);
    expect(state.connection()).toBe('online');
  });

  it('refresh marks offline when the API throws', async () => {
    const api = fakeApi({ getStatus: jasmine.createSpy().and.rejectWith(new Error('down')) });
    const state = new LabState(api);
    await state.refresh();
    expect(state.connection()).toBe('offline');
  });

  it('run returns the new job id', async () => {
    const state = new LabState(fakeApi());
    expect(await state.run('gen-demos', { n_train: 5 })).toBe('job-9');
  });
});
