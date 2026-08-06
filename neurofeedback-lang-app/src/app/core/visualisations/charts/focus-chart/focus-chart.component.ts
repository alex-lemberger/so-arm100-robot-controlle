// components/charts/focus-chart/focus-chart.component.ts
import { Component, ElementRef, Input, OnInit, ViewChild } from '@angular/core';
import * as d3 from 'd3';

@Component({
  selector: 'app-focus-chart',
  standalone: true,
  template: `
    <div #chartContainer class="chart-container"></div>
  `,
  styles: [`
    .chart-container {
      width: 100%;
      height: 100%;
    }

    :host {
      display: block;
      width: 100%;
      height: 100%;
    }
  `]
})
export class FocusChartComponent implements OnInit {
  @Input() focus: number | null = null;
  @ViewChild('chartContainer', { static: true }) private chartContainer!: ElementRef;

  private svg!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private line!: d3.Line<number>;
  private data: number[] = [];

  private margin = { top: 20, right: 20, bottom: 30, left: 40 };
  private width = 0;
  private height = 0;
  private maxPoints = 30;

  ngOnInit() {
    this.initializeChart();
  }

  private initializeChart(): void {
    // Get container dimensions
    const element = this.chartContainer.nativeElement;
    this.width = element.clientWidth - this.margin.left - this.margin.right;
    this.height = element.clientHeight - this.margin.top - this.margin.bottom;

    // Create SVG
    this.svg = d3.select(element)
      .append('svg')
        .attr('width', this.width + this.margin.left + this.margin.right)
        .attr('height', this.height + this.margin.top + this.margin.bottom)
      .append('g')
        .attr('transform', `translate(${this.margin.left},${this.margin.top})`);

    // Create scales
    const xScale = d3.scaleLinear()
      .range([0, this.width])
      .domain([0, this.maxPoints - 1]);

    const yScale = d3.scaleLinear()
      .range([this.height, 0])
      .domain([0, 100]);

    // Create line generator
    this.line = d3.line<number>()
      .x((_, i) => xScale(i))
      .y(d => yScale(d))
      .curve(d3.curveMonotoneX);

    // Add X axis
    this.svg.append('g')
      .attr('transform', `translate(0,${this.height})`)
      .call(d3.axisBottom(xScale)
        .ticks(5)
        .tickFormat(d => `${d}s`));

    // Add Y axis
    this.svg.append('g')
      .call(d3.axisLeft(yScale)
        .ticks(5)
        .tickFormat(d => `${d}%`));

    // Add grid lines
    this.svg.append('g')
      .attr('class', 'grid')
      .call(d3.axisLeft(yScale)
        .ticks(5)
        .tickSize(-this.width)
        .tickFormat(() => ''))
      .style('stroke-opacity', 0.1);

    // Add the line path
    this.svg.append('path')
      .attr('class', 'line')
      .attr('fill', 'none')
      .attr('stroke', '#2196F3')
      .attr('stroke-width', 2);
  }

  ngOnChanges(): void {
    if (this.focus !== null && this.svg) {
      // Update data array
      this.data.push(this.focus);
      if (this.data.length > this.maxPoints) {
        this.data.shift();
      }

      // Update the line
      this.svg.select('.line')
        .datum(this.data)
        .attr('d', this.line);
    }
  }
}

