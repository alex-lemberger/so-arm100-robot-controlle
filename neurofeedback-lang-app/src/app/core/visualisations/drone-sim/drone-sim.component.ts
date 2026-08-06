import { AfterViewInit, Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { UnityService } from '../../neurofeedback/services/unity.service';


@Component({
  selector: 'app-drone-sim',
  template: `
    <div class="unity-container">
      <canvas #unityCanvas id="unity-game"></canvas>
    </div>
  `,
  styles: [`
    .unity-container {
      width: 80%;
      height: 80vh;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    canvas {
      width: 100%;
      height: 100%;
      background: #231F20;
    }
  `],
  standalone: true
})
export class DroneSimComponent implements OnInit, AfterViewInit {
  @ViewChild('unityCanvas') unityCanvas!: ElementRef;

  constructor(private unityService: UnityService) {}

  ngOnInit() {}

  ngAfterViewInit() {
    this.unityService.loadUnityGame('unity-game');
  }
}
