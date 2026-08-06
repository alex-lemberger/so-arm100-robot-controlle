import { Injectable, signal } from '@angular/core';

/**
 * Shared nav rail state. `pinned` keeps the rail expanded (244px) and shifts the
 * shell content to match; when unpinned the rail collapses to 64px and still
 * hover-expands as an overlay. Consumed by NavigationComponent (toggle + width)
 * and DashboardLayoutComponent (content margin).
 */
@Injectable({ providedIn: 'root' })
export class NavStateService {
  /** Rail width in px, keyed to pinned state (matches CSS --nav-w / --nav-open). */
  static readonly COLLAPSED = 64;
  static readonly EXPANDED = 244;

  readonly pinned = signal(false);

  toggle(): void {
    this.pinned.update(v => !v);
  }
}
