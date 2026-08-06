import { Component, ElementRef, OnInit } from '@angular/core';
import * as d3 from 'd3';

@Component({
  selector: 'app-pie-chart',
  standalone: true,
  template: `<div class="chart-container"></div>`,
  styles: [
    `
      .chart-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin-top: 20px;
      }
    `,
  ],
})
export class PieChartComponent implements OnInit {
  private data = [
    { activity: 'Vocabulary', time: 30 },
    { activity: 'Listening', time: 25 },
    { activity: 'Speaking', time: 20 },
    { activity: 'Reading', time: 25 },
  ];

  constructor(private elementRef: ElementRef) {}

  ngOnInit(): void {
    this.createPieChart();
  }

  private createPieChart(): void {
    const element = this.elementRef.nativeElement.querySelector('.chart-container');
    const width = 400;
    const height = 400;
    const radius = Math.min(width, height) / 2;

    const svg = d3
      .select(element)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .append('g')
      .attr('transform', `translate(${width / 2},${height / 2})`);

    const color = d3.scaleOrdinal(d3.schemeCategory10);

    const pie = d3.pie<any>().value((d) => d.time);

    const data_ready = pie(this.data);

    const arc = d3.arc().innerRadius(0).outerRadius(radius);

    svg
      .selectAll('slices')
      .data(data_ready)
      .enter()
      .append('path')
      .attr('d', arc as any)
      .attr('fill', (d) => color(d.data.activity));
  }
}
