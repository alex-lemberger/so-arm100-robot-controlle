import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { SupabaseAuthService } from '../../supabase/supabase-auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatInputModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
  ],
  template: `
    <mat-card class="login-card">
      <h2>Login</h2>
      <form (ngSubmit)="login()">
        <mat-form-field appearance="fill" class="full-width">
          <mat-label>Email</mat-label>
          <input matInput type="email" [(ngModel)]="email" name="email" required />
        </mat-form-field>
        <mat-form-field appearance="fill" class="full-width">
          <mat-label>Password</mat-label>
          <input matInput type="password" [(ngModel)]="password" name="password" required />
        </mat-form-field>
        <button mat-raised-button color="primary" type="submit">Login</button>
      </form>
      <p *ngIf="errorMessage" class="error-message">{{ errorMessage }}</p>
    </mat-card>
  `,
  styles: [`
    .login-card { max-width: 400px; margin: 50px auto; padding: 20px; text-align: center; }
    .full-width { width: 100%; margin-bottom: 20px; }
    .error-message { color: red; margin-top: 10px; }
  `],
})
export class LoginComponent {
  email = '';
  password = '';
  errorMessage: string | null = null;

  constructor(private authService: SupabaseAuthService) {}

  async login() {
    try {
      await this.authService.signIn(this.email, this.password);
    } catch (error: any) {
      this.errorMessage = error.message;
    }
  }
}
