// src/app/modules/capture/services/worker-token.service.ts
import { Injectable } from '@angular/core';

const STORAGE_KEY = 'capture_worker_token';

@Injectable({ providedIn: 'root' })
export class WorkerTokenService {
  getOrCreate(): string {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    const token = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, token);
    return token;
  }

  get(): string | null {
    return localStorage.getItem(STORAGE_KEY);
  }

  clear(): void {
    localStorage.removeItem(STORAGE_KEY);
  }
}