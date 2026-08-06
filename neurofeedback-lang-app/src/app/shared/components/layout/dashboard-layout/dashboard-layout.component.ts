import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HeaderComponent } from '../header/header.component';
import { NavigationComponent } from '../navigation/navigation.component';
import { NavStateService } from '../navigation/nav-state.service';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-dashboard-layout',
  standalone: true,
  imports: [
    CommonModule,
    HeaderComponent,
    NavigationComponent,
    RouterModule
  ],
  template: `
    <app-navigation></app-navigation>
    <div class="shell" [style.margin-left.px]="nav.pinned() ? 244 : 64">
      <app-header></app-header>
      <div class="content">
        <ng-content>
          <router-outlet></router-outlet>
        </ng-content>
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; }

    .shell {
      /* margin-left bound to nav.pinned() — 64px collapsed / 244px pinned open.
         Rail overlays on hover when collapsed; pinning shifts content instead. */
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background: #EEF2F9;
      transition: margin-left .22s cubic-bezier(.4,0,.2,1);
    }

    .content {
      flex: 1;
      padding: 24px;
    }
  `]
})
export class DashboardLayoutComponent {
  protected readonly nav = inject(NavStateService);
}
