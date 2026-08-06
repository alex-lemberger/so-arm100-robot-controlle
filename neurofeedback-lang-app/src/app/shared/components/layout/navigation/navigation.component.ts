import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { RouterModule } from '@angular/router';
import { NavStateService } from './nav-state.service';

interface NavItem { route: string; icon: string; label: string; exact?: boolean; }

/**
 * Fixed rail that expands on hover (64px → 244px) — clinical-tool convention
 * that maximises the data canvas. Pure CSS: the rail overlays content on hover
 * (with a drop shadow) rather than pushing it. Labels fade in; the active route
 * carries an azure tint plus a left accent bar so meaning is never colour-only.
 */
@Component({
  selector: 'app-navigation',
  standalone: true,
  imports: [CommonModule, MatIconModule, RouterModule],
  template: `
    <nav class="rail" [class.rail--pinned]="nav.pinned()" aria-label="Main navigation">
      <!-- Brand -->
      <div class="rail__brand">
        <span class="rail__logo" aria-hidden="true"><mat-icon>sensors</mat-icon></span>
        <span class="rail__brand-text">Handwerk Capture</span>
      </div>

      <!-- Primary items -->
      <div class="rail__items">
        @for (item of items; track item.route) {
          <a class="navi" [routerLink]="item.route"
             routerLinkActive="navi--active"
             [routerLinkActiveOptions]="{ exact: !!item.exact }"
             [attr.aria-label]="item.label">
            <span class="navi__bar" aria-hidden="true"></span>
            <mat-icon class="navi__icon">{{ item.icon }}</mat-icon>
            <span class="navi__label">{{ item.label }}</span>
          </a>
        }
      </div>

      <!-- Footer item -->
      <div class="rail__foot">
        <button type="button" class="navi navi--toggle"
                (click)="nav.toggle()"
                [attr.aria-pressed]="nav.pinned()"
                [attr.aria-label]="nav.pinned() ? 'Collapse navigation' : 'Expand navigation'">
          <mat-icon class="navi__icon">{{ nav.pinned() ? 'menu_open' : 'menu' }}</mat-icon>
          <span class="navi__label">{{ nav.pinned() ? 'Collapse' : 'Expand' }}</span>
        </button>
      </div>
    </nav>
  `,
  styles: [`
    :host {
      --c-azure:       #1565C0;
      --c-azure-mid:   #1976D2;
      --c-azure-tint:  #EEF5FE;
      --c-bg:          #EEF2F9;
      --c-surface:     #FFFFFF;
      --c-border:      #DDE5F2;
      --c-border-soft: #EEF2FA;
      --c-text-1:      #18253F;
      --c-text-2:      #5A6A8E;
      --nav-w:         64px;
      --nav-open:      244px;
      --topbar-h:      56px;
      font-family: 'DM Sans', system-ui, sans-serif;
    }

    .rail {
      position: fixed; left: 0; top: 0; bottom: 0; z-index: 100;
      width: var(--nav-w);
      display: flex; flex-direction: column; padding-bottom: 16px;
      background: var(--c-surface); border-right: 1px solid var(--c-border);
      overflow: hidden;
      transition: width .22s cubic-bezier(.4,0,.2,1), box-shadow .22s;
    }
    .rail:hover {
      width: var(--nav-open);
      box-shadow: 2px 0 16px rgba(24,37,63,.07);
    }
    /* Pinned open via toggle — stays expanded, shell content shifts to match. */
    .rail--pinned { width: var(--nav-open); }
    .rail--pinned .rail__brand-text,
    .rail--pinned .navi__label { opacity: 1; }

    /* ── Brand ── */
    .rail__brand {
      display: flex; align-items: center; gap: 11px;
      height: var(--topbar-h); padding: 0 16px; flex-shrink: 0; overflow: hidden;
      border-bottom: 1px solid var(--c-border-soft);
    }
    .rail__logo {
      width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0;
      display: grid; place-items: center;
      background: linear-gradient(140deg, #1976D2 0%, #1565C0 100%);
      mat-icon { color: #fff; font-size: 17px; width: 17px; height: 17px; }
    }
    .rail__brand-text {
      font-size: 14px; font-weight: 600; letter-spacing: -.2px; white-space: nowrap;
      color: var(--c-text-1); opacity: 0; transition: opacity .12s;
    }
    .rail:hover .rail__brand-text { opacity: 1; }

    /* ── Items ── */
    .rail__items { flex: 1; display: flex; flex-direction: column; gap: 2px; padding: 12px 10px 0; }
    .rail__foot { padding: 0 10px; flex-shrink: 0; }

    .navi {
      position: relative; display: flex; align-items: center; gap: 11px;
      padding: 9px 12px; border-radius: 10px;
      text-decoration: none; white-space: nowrap; overflow: hidden;
      color: var(--c-text-2); font-size: 14px; font-weight: 500;
      transition: background .1s, color .1s;
      &:hover { background: var(--c-bg); color: var(--c-text-1); }
    }
    .navi__icon { flex-shrink: 0; font-size: 20px; width: 20px; height: 20px; }
    .navi__label { opacity: 0; transition: opacity .1s; }
    .rail:hover .navi__label { opacity: 1; }

    .navi__bar {
      position: absolute; left: 0; top: 9px; bottom: 9px; width: 3px;
      border-radius: 0 2px 2px 0; background: var(--c-azure); opacity: 0;
    }
    .navi--active {
      background: var(--c-azure-tint); color: var(--c-azure); font-weight: 600;
      &:hover { background: var(--c-azure-tint); color: var(--c-azure); }
      .navi__bar { opacity: 1; }
      .navi__icon { margin-left: 3px; }
    }

    .navi:focus-visible { outline: 2px solid var(--c-azure-mid); outline-offset: -2px; }

    /* Toggle button — reset native button chrome, reuse .navi layout. */
    .navi--toggle {
      width: 100%; background: transparent; border: 0; cursor: pointer;
      font-family: inherit; text-align: left;
    }

    @media (prefers-reduced-motion: reduce) {
      .rail, .rail__brand-text, .navi, .navi__label { transition: none; }
    }
  `]
})
export class NavigationComponent {
  protected readonly nav = inject(NavStateService);

  readonly items: NavItem[] = [
    { route: '/dashboard', icon: 'dashboard', label: 'Dashboard', exact: true },
    { route: '/exercises', icon: 'school', label: 'Exercises' },
    { route: '/capture', icon: 'sensors', label: 'Capture', exact: true },
    { route: '/demo', icon: 'smart_toy', label: 'Demo', exact: true },
    { route: '/lab', icon: 'precision_manufacturing', label: 'Robot Lab', exact: true },
  ];
}
