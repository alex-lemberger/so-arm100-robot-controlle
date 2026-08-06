import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { Observable } from 'rxjs';
import { User } from '@supabase/supabase-js';
import { SupabaseAuthService } from '../../supabase/supabase-auth.service';

@Component({
  selector: 'app-logout-menu',
  standalone: true,
  imports: [CommonModule, MatButtonModule],
  template: `
    <div *ngIf="user$ | async as user">
      <span>Welcome, {{ user?.email }}</span>
      <button mat-button color="warn" (click)="logout()">Logout</button>
    </div>
  `,
  styles: [`span { margin-right: 16px; }`],
})
export class LogoutMenuComponent {
  user$: Observable<User | null>;

  constructor(private authService: SupabaseAuthService) {
    this.user$ = this.authService.user$;
  }

  logout() {
    this.authService.signOut();
  }
}
