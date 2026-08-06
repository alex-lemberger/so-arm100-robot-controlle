// src/app/shared/pipes/minutes.pipe.ts
import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'minutes',
  standalone: true
})
export class MinutesPipe implements PipeTransform {
  transform(value: number): string {
    const minutes = Math.floor(value / 60);
    const seconds = value % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  }
}
