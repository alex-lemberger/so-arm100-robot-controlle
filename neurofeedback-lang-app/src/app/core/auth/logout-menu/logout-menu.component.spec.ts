import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { SupabaseAuthService } from '../../supabase/supabase-auth.service';

import { LogoutMenuComponent } from './logout-menu.component';

describe('LogoutMenuComponent', () => {
  let component: LogoutMenuComponent;
  let fixture: ComponentFixture<LogoutMenuComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LogoutMenuComponent],
      providers: [
        {
          provide: SupabaseAuthService,
          useValue: { user$: of(null), session$: of(null), currentUser: null, signOut: jasmine.createSpy('signOut') },
        },
      ],
    })
    .compileComponents();

    fixture = TestBed.createComponent(LogoutMenuComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
