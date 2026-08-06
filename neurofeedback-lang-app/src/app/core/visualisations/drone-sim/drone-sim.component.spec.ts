import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DroneSimComponent } from './drone-sim.component';

describe('DroneSimComponent', () => {
  let component: DroneSimComponent;
  let fixture: ComponentFixture<DroneSimComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DroneSimComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(DroneSimComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
