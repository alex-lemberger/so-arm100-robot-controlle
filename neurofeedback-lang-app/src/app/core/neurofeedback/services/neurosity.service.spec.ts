// neurosity.service.spec.ts
import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { NeurosityService } from './neurosity.service';
import { Subject } from 'rxjs';

// Mock Neurosity SDK
const mockNotion = {
  getUser: jasmine.createSpy('getUser').and.returnValue(Promise.resolve(null)),
  login: jasmine.createSpy('login').and.returnValue(Promise.resolve()),
  logout: jasmine.createSpy('logout').and.returnValue(Promise.resolve()),
  whenReady: jasmine.createSpy('whenReady').and.returnValue(Promise.resolve()),
  focus: jasmine.createSpy('focus').and.returnValue(new Subject()),
  calm: jasmine.createSpy('calm').and.returnValue(new Subject()),
  status: jasmine.createSpy('status').and.returnValue(Promise.resolve({}))
};

describe('NeurosityService', () => {
  let service: NeurosityService;
  let focusSubject: Subject<any>;
  let calmSubject: Subject<any>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        NeurosityService
      ]
    });

    focusSubject = new Subject();
    calmSubject = new Subject();
    mockNotion.getUser.and.returnValue(Promise.resolve(null));
    mockNotion.login.and.returnValue(Promise.resolve());
    mockNotion.logout.and.returnValue(Promise.resolve());
    mockNotion.whenReady.and.returnValue(Promise.resolve());
    mockNotion.focus.and.returnValue(focusSubject);
    mockNotion.calm.and.returnValue(calmSubject);
    mockNotion.status.and.returnValue(Promise.resolve({}));

    service = TestBed.inject(NeurosityService);
    (service as any).notion = mockNotion;
  });

  afterEach(() => {
    focusSubject.complete();
    calmSubject.complete();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('initial state', () => {
    it('should have initial logged out state', () => {
      service.state$.subscribe(state => {
        expect(state.isLoggedIn).toBeFalse();
        expect(state.error).toBeNull();
      });
    });
  });

  describe('connect', () => {
    it('should update state on successful connect', fakeAsync(() => {
      service.connect({ email: 'test@user.com', password: 'password' }).then(() => {
        expect(mockNotion.login).toHaveBeenCalledWith({ email: 'test@user.com', password: 'password' });
        service.state$.subscribe(state => {
          expect(state.isLoggedIn).toBeTrue();
          expect(state.error).toBeNull();
        });
      });
      tick();
    }));

    it('should handle connect errors', fakeAsync(() => {
      const error = new Error('Invalid credentials');
      mockNotion.login.and.returnValue(Promise.reject(error));

      service.connect({ email: 'wrong@user.com', password: 'wrong' }).catch(err => {
        expect(err.message).toBe('Invalid credentials');
        service.state$.subscribe(state => {
          expect(state.isLoggedIn).toBeFalse();
          expect(state.error).toBe('Invalid credentials');
        });
      });
      tick();
    }));

    it('rejects when called without credentials', async () => {
      await expectAsync(service.connect()).toBeRejectedWithError(
        'Neurosity device requires email/password credentials'
      );
    });
  });

  describe('subscriptions', () => {
    it('should setup focus and calm subscriptions', fakeAsync(() => {
      service['setupSubscriptions']();
      tick();

      const testFocus = { probability: 0.8 };
      const testCalm = { probability: 0.9 };

      focusSubject.next(testFocus);
      calmSubject.next(testCalm);

      expect(service.focus$.value).toBe(0.8);
      expect(service.calm$.value).toBe(0.9);
    }));

    it('should handle subscription errors', async () => {
      await service['setupSubscriptions']();

      focusSubject.error('Focus error');
      calmSubject.error('Calm error');

      expect((service as any)._state.value.error).toContain('monitoring failed');
    });
  });

  describe('disconnect', () => {
    it('should clear state and subscriptions on disconnect', fakeAsync(() => {
      service.connect({ email: 'test@user.com', password: 'password' });
      tick();

      service.disconnect().then(() => {
        expect(mockNotion.logout).toHaveBeenCalled();
        expect(service.focus$.value).toBeNull();
        expect(service.calm$.value).toBeNull();
        service.state$.subscribe(state => {
          expect(state.isLoggedIn).toBeFalse();
        });
      });
      tick();
    }));
  });

  describe('ngOnDestroy', () => {
    it('should complete destroy subject', () => {
      service.ngOnDestroy();
      expect(service['destroy$'].isStopped).toBeTrue();
    });
  });
});
