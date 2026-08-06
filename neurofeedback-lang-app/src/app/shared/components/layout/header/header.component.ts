import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { FormsModule } from '@angular/forms';
import { SupabaseAuthService } from '../../../../core/supabase/supabase-auth.service';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    CommonModule,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatMenuModule,
    FormsModule,
  ],
  template: `
    <mat-toolbar class="header">
      <div class="logo-wrapper"></div>
      <div class="user-container">
        <button mat-button [matMenuTriggerFor]="userMenu" class="user-button">
          <mat-icon>account_circle</mat-icon>
          {{ authService.currentUser?.email || 'User' }}
        </button>
        <mat-menu #userMenu="matMenu">
          <button mat-menu-item (click)="signOut()">
            <mat-icon>exit_to_app</mat-icon>
            <span>Sign Out</span>
          </button>
        </mat-menu>
      </div>
    </mat-toolbar>
  `,
  styles: [`
    .header { display: flex; align-items: center; padding: 0 24px; background: white;
              border-bottom: 1px solid #EEF2FA; height: 56px; }
    .logo-wrapper { width: 150px; height: 36px; background-image: url('/img/logo.svg');
                    background-repeat: no-repeat; background-size: contain;
                    background-position: left center; }
    .user-container { display: flex; align-items: center; gap: 8px; margin-left: auto; }
    .user-button { display: flex; align-items: center; gap: 8px; }
  `],
})
export class HeaderComponent {
  constructor(public authService: SupabaseAuthService) {}

  async signOut() {
    await this.authService.signOut();
  }
}
