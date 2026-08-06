// src/app/core/visualisations/charts/bar-chart/bar-chart.component.ts
import { Component, ElementRef, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import * as d3 from 'd3';

interface ChartData {
  activity: string;
  score: number;
}

@Component({
  selector: 'app-bar-chart',
  standalone: true,
  template: `<div class="chart-container"></div>`,
  styles: [`
    .chart-container {
      display: flex;
      justify-content: center;
      align-items: center;
      margin-top: 20px;
    }
    svg {
      font-family: sans-serif;
    }
    .bar {
      transition: fill 0.3s ease;
    }
    .bar:hover {
      fill: #4CAF50;
    }
    .axis-label {
      font-size: 12px;
      fill: #666;
    }
  `]
})
export class BarChartComponent implements OnInit, OnChanges {
  @Input() data: ChartData[] = [];
  @Input() width = 600;
  @Input() height = 400;
  @Input() barColor = 'steelblue';
  @Input() showLabels = true;

  private svg: any;
  private margin = { top: 20, right: 30, bottom: 40, left: 50 };
  private chartWidth: number;
  private chartHeight: number;

  constructor(private elementRef: ElementRef) {
    this.chartWidth = this.width - this.margin.left - this.margin.right;
    this.chartHeight = this.height - this.margin.top - this.margin.bottom;
  }

  ngOnInit(): void {
    this.createSvg();
    if (this.data.length > 0) {
      this.drawBars();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data'] && !changes['data'].firstChange) {
      this.updateChart();
    }
  }

  private createSvg(): void {
    // Clear any existing SVG
    d3.select(this.elementRef.nativeElement.querySelector('.chart-container'))
      .selectAll('*')
      .remove();

    this.svg = d3.select(this.elementRef.nativeElement.querySelector('.chart-container'))
      .append('svg')
      .attr('width', this.width)
      .attr('height', this.height)
      .append('g')
      .attr('transform', `translate(${this.margin.left},${this.margin.top})`);
  }

  private drawBars(): void {
    // Create scales
    const x = d3.scaleBand()
      .domain(this.data.map(d => d.activity))
      .range([0, this.chartWidth])
      .padding(0.2);

    const y = d3.scaleLinear()
      .domain([0, d3.max(this.data, d => d.score) || 100])
      .range([this.chartHeight, 0]);

    // Add X axis
    this.svg.append('g')
      .attr('class', 'x-axis')
      .attr('transform', `translate(0,${this.chartHeight})`)
      .call(d3.axisBottom(x))
      .selectAll('text')
      .attr('transform', 'translate(-10,0)rotate(-45)')
      .style('text-anchor', 'end');

    // Add Y axis
    this.svg.append('g')
      .attr('class', 'y-axis')
      .call(d3.axisLeft(y)
        .ticks(5)
        .tickFormat(d => `${d}%`));

    // Add bars
    this.svg.selectAll('.bar')
      .data(this.data)
      .enter()
      .append('rect')
      .attr('class', 'bar')
      .attr('x', (d: ChartData) => x(d.activity))
      .attr('y', (d: ChartData) => y(d.score))
      .attr('width', x.bandwidth())
      .attr('height', (d: ChartData) => this.chartHeight - y(d.score))
      .attr('fill', this.barColor);

    // Add labels if enabled
    if (this.showLabels) {
      this.svg.selectAll('.label')
        .data(this.data)
        .enter()
        .append('text')
        .attr('class', 'label')
        .attr('x', (d: ChartData) => x(d.activity)! + x.bandwidth() / 2)
        .attr('y', (d: ChartData) => y(d.score) - 5)
        .attr('text-anchor', 'middle')
        .text((d: ChartData) => `${d.score}%`);
    }
  }

  private updateChart(): void {
    const x = d3.scaleBand()
      .domain(this.data.map(d => d.activity))
      .range([0, this.chartWidth])
      .padding(0.2);

    const y = d3.scaleLinear()
      .domain([0, d3.max(this.data, d => d.score) || 100])
      .range([this.chartHeight, 0]);

    // Update bars with animation
    const bars = this.svg.selectAll('.bar')
      .data(this.data);

    // Remove old bars
    bars.exit().remove();

    // Update existing bars
    bars.transition()
      .duration(750)
      .attr('x', (d: ChartData) => x(d.activity))
      .attr('y', (d: ChartData) => y(d.score))
      .attr('width', x.bandwidth())
      .attr('height', (d: ChartData) => this.chartHeight - y(d.score));

    // Add new bars
    bars.enter()
      .append('rect')
      .attr('class', 'bar')
      .attr('x', (d: ChartData) => x(d.activity))
      .attr('y', this.chartHeight)
      .attr('width', x.bandwidth())
      .attr('height', 0)
      .attr('fill', this.barColor)
      .transition()
      .duration(750)
      .attr('y', (d: ChartData) => y(d.score))
      .attr('height', (d: ChartData) => this.chartHeight - y(d.score));

    // Update labels if enabled
    if (this.showLabels) {
      const labels = this.svg.selectAll('.label')
        .data(this.data);

      labels.exit().remove();

      labels.transition()
        .duration(750)
        .attr('x', (d: ChartData) => x(d.activity)! + x.bandwidth() / 2)
        .attr('y', (d: ChartData) => y(d.score) - 5)
        .text((d: ChartData) => `${d.score}%`);

      labels.enter()
        .append('text')
        .attr('class', 'label')
        .attr('x', (d: ChartData) => x(d.activity)! + x.bandwidth() / 2)
        .attr('y', (d: ChartData) => y(d.score) - 5)
        .attr('text-anchor', 'middle')
        .text((d: ChartData) => `${d.score}%`);
    }

    // Update axes
    this.svg.select('.x-axis')
      .transition()
      .duration(750)
      .call(d3.axisBottom(x));

    this.svg.select('.y-axis')
      .transition()
      .duration(750)
      .call(d3.axisLeft(y)
        .ticks(5)
        .tickFormat(d => `${d}%`));
  }
}
