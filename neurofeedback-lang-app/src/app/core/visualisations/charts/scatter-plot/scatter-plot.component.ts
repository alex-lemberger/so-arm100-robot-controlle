// components/charts/scatter-plot/scatter-plot.component.ts
import { 
  Component, 
  ElementRef, 
  input, 
  ViewChild, 
  AfterViewInit, 
  OnDestroy, 
  HostListener,
  effect,
  signal,
  computed
} from '@angular/core';
import * as d3 from 'd3';

interface DataPoint {
  focus: number;
  calm: number;
  timestamp: Date;
}

@Component({
  selector: 'app-scatter-plot',
  standalone: true,
  template: `
    <div #chartContainer class="chart-container">
      <div #tooltip class="tooltip">
        <div class="tooltip-content"></div>
      </div>
    </div>
  `,
  styles: [`
    .chart-container {
      width: 100%;
      height: 100%;
      position: relative;
    }

    .tooltip {
      position: absolute;
      padding: 8px;
      background: rgba(0, 0, 0, 0.8);
      color: white;
      border-radius: 4px;
      font-size: 12px;
      pointer-events: none;
      transform: translate(-50%, -100%);
      z-index: 100;
      display: none;
    }

    :host {
      display: block;
      width: 100%;
      height: 100%;
    }
  `]
})
export class ScatterPlotComponent implements AfterViewInit, OnDestroy {
  private resizeObserver?: ResizeObserver;
  
  // Modern signal-based inputs
  data = input<DataPoint[]>([]);
  width = input<number>(0);
  height = input<number>(0);
  
  // Internal signals
  private readonly isInitialized = signal(false);
  private readonly containerDimensions = signal({ width: 0, height: 0 });
  
  // Computed signals
  private readonly chartDimensions = computed(() => {
    const container = this.containerDimensions();
    const inputWidth = this.width();
    const inputHeight = this.height();
    
    return {
      width: Math.max(inputWidth || container.width - this.margin.left - this.margin.right, 300),
      height: Math.max(inputHeight || container.height - this.margin.top - this.margin.bottom, 200)
    };
  });
  
  private readonly hasData = computed(() => this.data().length > 0);
  
  private readonly shouldRenderChart = computed(() => 
    this.isInitialized() && this.hasData() && this.chartDimensions().width > 0
  );

  @ViewChild('chartContainer', { static: true }) private chartContainer!: ElementRef;
  @ViewChild('tooltip', { static: true }) private tooltip!: ElementRef;

  private svg!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private xScale!: d3.ScaleLinear<number, number>;
  private yScale!: d3.ScaleLinear<number, number>;
  private readonly margin = { top: 20, right: 30, bottom: 40, left: 50 };

  constructor() {
    // Effect to initialize chart when container is ready
    effect(() => {
      const dimensions = this.chartDimensions();
      if (this.isInitialized() && dimensions.width > 0 && dimensions.height > 0) {
        this.initializeChart();
      }
    });

    // Effect to update chart when data changes
    effect(() => {
      if (this.shouldRenderChart()) {
        this.updateChart();
      }
    });
  }

  ngAfterViewInit() {
    // Update container dimensions and mark as initialized
    setTimeout(() => {
      this.updateContainerDimensions();
      this.setupResizeObserver();
      this.isInitialized.set(true);
    }, 0);
  }

  ngOnDestroy() {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
  }

  private updateContainerDimensions(): void {
    const element = this.chartContainer.nativeElement;
    this.containerDimensions.set({
      width: element.clientWidth,
      height: element.clientHeight
    });
  }

  private setupResizeObserver(): void {
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => {
        this.updateContainerDimensions();
      });
      this.resizeObserver.observe(this.chartContainer.nativeElement);
    }
  }

  @HostListener('window:resize', ['$event'])
  onWindowResize() {
    this.updateContainerDimensions();
  }

  private initializeChart(): void {
    const element = this.chartContainer.nativeElement;
    const dimensions = this.chartDimensions();
    
    // Remove existing SVG if any
    d3.select(element).select('svg').remove();

    // Create SVG
    this.svg = d3.select(element)
      .append('svg')
        .attr('width', dimensions.width + this.margin.left + this.margin.right)
        .attr('height', dimensions.height + this.margin.top + this.margin.bottom)
      .append('g')
        .attr('transform', `translate(${this.margin.left},${this.margin.top})`);

    // Create scales
    this.xScale = d3.scaleLinear()
      .range([0, dimensions.width])
      .domain([0, 100]);

    this.yScale = d3.scaleLinear()
      .range([dimensions.height, 0])
      .domain([0, 100]);

    // Add X axis
    this.svg.append('g')
      .attr('transform', `translate(0,${dimensions.height})`)
      .call(d3.axisBottom(this.xScale))
      .call(g => g.append('text')
        .attr('x', dimensions.width / 2)
        .attr('y', 35)
        .attr('fill', 'currentColor')
        .attr('text-anchor', 'middle')
        .text('Focus Level (%)'));

    // Add Y axis
    this.svg.append('g')
      .call(d3.axisLeft(this.yScale))
      .call(g => g.append('text')
        .attr('x', -dimensions.height / 2)
        .attr('y', -40)
        .attr('fill', 'currentColor')
        .attr('text-anchor', 'middle')
        .attr('transform', 'rotate(-90)')
        .text('Calm Level (%)'));

    // Add grid
    this.svg.append('g')
      .attr('class', 'grid')
      .call(d3.axisLeft(this.yScale)
        .tickSize(-dimensions.width)
        .tickFormat(() => ''))
      .style('stroke-opacity', 0.1);

    this.svg.append('g')
      .attr('class', 'grid')
      .attr('transform', `translate(0,${dimensions.height})`)
      .call(d3.axisBottom(this.xScale)
        .tickSize(-dimensions.height)
        .tickFormat(() => ''))
      .style('stroke-opacity', 0.1);
  }

  private updateChart(): void {
    const currentData = this.data();

    if (!this.svg || !this.xScale || !this.yScale) {
      return;
    }

    if (currentData.length === 0) {
      this.svg.selectAll('.point').remove();
      return;
    }

    // Update the chart with D3's data join pattern
    const circles = this.svg.selectAll<SVGCircleElement, DataPoint>('.point')
      .data(currentData, (d: DataPoint) => d.timestamp.getTime().toString());

    // Remove old points
    circles.exit()
      .transition()
      .duration(300)
      .attr('r', 0)
      .style('opacity', 0)
      .remove();

    // Add new points
    const newCircles = circles.enter()
      .append('circle')
      .attr('class', 'point')
      .attr('cx', d => this.xScale(d.focus))
      .attr('cy', d => this.yScale(d.calm))
      .attr('r', 0)
      .style('fill', '#2196F3')
      .style('opacity', 0);

    // Merge new and existing points
    const allCircles = newCircles.merge(circles);

    // Update all points with smooth transitions
    allCircles
      .transition()
      .duration(300)
      .attr('cx', d => this.xScale(d.focus))
      .attr('cy', d => this.yScale(d.calm))
      .attr('r', 5)
      .style('opacity', 0.6);

    // Add interactions (re-apply to handle new elements)
    allCircles
      .on('mouseover', (event, d) => this.showTooltip(event, d))
      .on('mouseout', () => this.hideTooltip());
  }

  private showTooltip(event: MouseEvent, data: DataPoint): void {
    const tooltip = d3.select(this.tooltip.nativeElement);
    tooltip
      .style('display', 'block')
      .style('left', `${event.pageX}px`)
      .style('top', `${event.pageY - 10}px`);

    tooltip.select('.tooltip-content').html(`
      Focus: ${data.focus.toFixed(1)}%<br>
      Calm: ${data.calm.toFixed(1)}%<br>
      Time: ${data.timestamp.toLocaleTimeString()}
    `);
  }

  private hideTooltip(): void {
    d3.select(this.tooltip.nativeElement)
      .style('display', 'none');
  }
}
