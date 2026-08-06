import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseAuthService } from './supabase-auth.service';
import { SupabaseClientService } from './supabase-client.service';

// Karma is broken repo-wide (see CLAUDE.md); these specs are write-only until fixed.
// `mock` is read from environment.useMockData at construction, so each test sets it first.
describe('SupabaseAuthService', () => {
  let originalMock: boolean;
  beforeEach(() => { originalMock = environment.useMockData; });
  afterEach(() => { environment.useMockData = originalMock; });

  function realClientStub(): SupabaseClientService {
    return {
      client: {
        auth: {
          getSession: jasmine.createSpy().and.resolveTo({ data: { session: null } }),
          onAuthStateChange: jasmine.createSpy(),
          signInWithPassword: jasmine.createSpy(),
          signOut: jasmine.createSpy(),
        },
      },
    } as unknown as SupabaseClientService;
  }

  it('mock mode emits a fake user without touching the real client', async () => {
    const stub = realClientStub();
    environment.useMockData = true;
    const svc = new SupabaseAuthService(stub);
    const user = await firstValueFrom(svc.user$);
    expect(user).not.toBeNull();
    expect(svc.currentUser?.email).toBe('local@mock.dev');
    expect((stub.client.auth.getSession as jasmine.Spy)).not.toHaveBeenCalled();
  });

  it('mock signIn sets a session offline (no network call)', async () => {
    const stub = realClientStub();
    environment.useMockData = true;
    const svc = new SupabaseAuthService(stub);
    await svc.signIn('x', 'y');
    expect(svc.currentUser).not.toBeNull();
    expect((stub.client.auth.signInWithPassword as jasmine.Spy)).not.toHaveBeenCalled();
  });

  it('mock signOut clears the session', async () => {
    environment.useMockData = true;
    const svc = new SupabaseAuthService(realClientStub());
    await svc.signOut();
    expect(svc.currentUser).toBeNull();
  });

  it('non-mock mode wires the real client', () => {
    const stub = realClientStub();
    environment.useMockData = false;
    new SupabaseAuthService(stub);
    expect((stub.client.auth.getSession as jasmine.Spy)).toHaveBeenCalled();
    expect((stub.client.auth.onAuthStateChange as jasmine.Spy)).toHaveBeenCalled();
  });
});
