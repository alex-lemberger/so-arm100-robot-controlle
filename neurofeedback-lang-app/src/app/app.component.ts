import { MatToolbarModule } from '@angular/material/toolbar';
import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Observable, of } from 'rxjs';
import { catchError, map, startWith } from 'rxjs/operators';
import { User } from '@supabase/supabase-js';
import { SupabaseAuthService } from './core/supabase/supabase-auth.service';
import { LoginComponent } from './core/auth/login/login.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatCardModule,
    MatButtonModule,
    MatProgressBarModule,
    LoginComponent,
    MatToolbarModule,
  ],
  template: `
    <mat-progress-bar
      *ngIf="isLoading$ | async"
      mode="indeterminate"
      class="loading-bar">
    </mat-progress-bar>
    <main>
      <ng-container *ngIf="user$ | async; else loginTemplate">
        <router-outlet></router-outlet>
      </ng-container>
      <ng-template #loginTemplate>
        <app-login></app-login>
      </ng-template>
    </main>
  `,
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  user$: Observable<User | null>;
  isLoading$: Observable<boolean>;

  constructor(private authService: SupabaseAuthService) {
    this.user$ = this.authService.user$;
    this.isLoading$ = this.user$.pipe(
      map(() => false),
      startWith(true),
      catchError(() => of(false)),
    );
  }
}