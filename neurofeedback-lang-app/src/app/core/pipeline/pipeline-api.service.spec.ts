import { PipelineApiService } from './pipeline-api.service';

describe('PipelineApiService', () => {
  it('startJob posts kind+args and returns job_id', async () => {
    const svc = new PipelineApiService();
    spyOn(window, 'fetch').and.resolveTo(
      new Response(JSON.stringify({ job_id: 'job-1' }), { status: 200 }),
    );
    const id = await svc.startJob('gen-demos', { n_train: 10 });
    expect(id).toBe('job-1');
  });

  it('getStatus rejects on non-ok response', async () => {
    const svc = new PipelineApiService();
    spyOn(window, 'fetch').and.resolveTo(new Response('nope', { status: 500 }));
    await expectAsync(svc.getStatus()).toBeRejected();
  });
});
