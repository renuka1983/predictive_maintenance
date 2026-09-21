/**
 * Chart primitives.
 *
 * Shared conventions, applied to every chart here:
 *  - one y-axis only, never a second scale;
 *  - series colours come from the fixed categorical order (never cycled),
 *    and status colours are reserved for state, never for a series;
 *  - recessive grid and axes, thin marks, rounded data-ends on bars;
 *  - a hover tooltip on every plot;
 *  - a legend whenever two or more series share a plot.
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const AXIS = { fontSize: 11, fill: 'var(--text-muted)' };
/* Wide enough for a formatted tick ("$120k", "85.0%") without clipping. */
const AXIS_WIDTH = 60;
const GRID = 'var(--grid)';

/** Tooltip shell shared by every chart so hover looks identical everywhere. */
function ChartTooltip({ active, payload, label, formatter, labelFormatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="tt-label">{labelFormatter ? labelFormatter(label) : label}</div>
      {payload.map((entry) => (
        <div className="tt-row" key={entry.dataKey}>
          <span>{entry.name}</span>
          <span>{formatter ? formatter(entry.value, entry.dataKey) : entry.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="chart-legend">
      {items.map((item) => (
        <span key={item.label}>
          <i style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

/**
 * Stacked bars for parts of a whole over time (e.g. planned vs reactive work
 * orders). Both series share one scale, so stacking is honest.
 */
export function StackedBars({
  data,
  xKey,
  series,
  height = 220,
  valueFormatter,
  labelFormatter,
  axisFormatter,
}) {
  return (
    <>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey={xKey}
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: 'var(--axis)' }}
            tickFormatter={labelFormatter}
          />
          <YAxis
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={AXIS_WIDTH}
            tickFormatter={axisFormatter}
          />
          <Tooltip
            cursor={{ fill: 'var(--grid)', opacity: 0.4 }}
            content={
              <ChartTooltip formatter={valueFormatter} labelFormatter={labelFormatter} />
            }
          />
          {series.map((s, index) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId="stack"
              fill={s.color}
              /* 2px surface gap between stacked segments */
              stroke="var(--surface)"
              strokeWidth={2}
              radius={index === series.length - 1 ? [4, 4, 0, 0] : 0}
              maxBarSize={34}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </>
  );
}

/**
 * Single-series bars. No legend: the chart title names the series.
 * `toneKey` optionally colours each bar by a status token.
 */
export function SimpleBars({
  data,
  xKey,
  valueKey,
  color = 'var(--series-1)',
  height = 220,
  horizontal = false,
  valueFormatter,
  labelFormatter,
  axisFormatter,
  toneFor,
}) {
  const layout = horizontal ? 'vertical' : 'horizontal';
  const tickFormatter = axisFormatter || valueFormatter;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout={layout}
        margin={
          horizontal
            ? { top: 4, right: 16, bottom: 4, left: 8 }
            : { top: 4, right: 8, bottom: 0, left: 0 }
        }
      >
        <CartesianGrid stroke={GRID} horizontal={!horizontal} vertical={horizontal} />
        {horizontal ? (
          <>
            <XAxis
              type="number"
              tick={AXIS}
              tickLine={false}
              axisLine={false}
              tickFormatter={tickFormatter}
            />
            <YAxis
              type="category"
              dataKey={xKey}
              tick={AXIS}
              tickLine={false}
              axisLine={{ stroke: 'var(--axis)' }}
              width={110}
            />
          </>
        ) : (
          <>
            <XAxis
              dataKey={xKey}
              tick={AXIS}
              tickLine={false}
              axisLine={{ stroke: 'var(--axis)' }}
              tickFormatter={labelFormatter}
            />
            <YAxis
              tick={AXIS}
              tickLine={false}
              axisLine={false}
              width={AXIS_WIDTH}
              tickFormatter={tickFormatter}
            />
          </>
        )}
        <Tooltip
          cursor={{ fill: 'var(--grid)', opacity: 0.4 }}
          content={<ChartTooltip formatter={valueFormatter} labelFormatter={labelFormatter} />}
        />
        <Bar
          dataKey={valueKey}
          fill={color}
          radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
          maxBarSize={horizontal ? 18 : 34}
        >
          {toneFor &&
            data.map((row, index) => (
              <Cell key={index} fill={toneFor(row)} />
            ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Single-series line with a crosshair tooltip. */
export function TrendLine({
  data,
  xKey,
  valueKey,
  label,
  color = 'var(--series-1)',
  height = 220,
  valueFormatter,
  labelFormatter,
  axisFormatter,
  area = false,
}) {
  const Chart = area ? AreaChart : LineChart;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <Chart data={data} margin={{ top: 4, right: 10, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`fill-${valueKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={AXIS}
          tickLine={false}
          axisLine={{ stroke: 'var(--axis)' }}
          tickFormatter={labelFormatter}
          minTickGap={24}
        />
        <YAxis
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          width={AXIS_WIDTH}
          domain={['auto', 'auto']}
          tickFormatter={axisFormatter || valueFormatter}
        />
        <Tooltip
          cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
          content={<ChartTooltip formatter={valueFormatter} labelFormatter={labelFormatter} />}
        />
        {area ? (
          <Area
            type="monotone"
            dataKey={valueKey}
            name={label}
            stroke={color}
            strokeWidth={2}
            fill={`url(#fill-${valueKey})`}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }}
          />
        ) : (
          <Line
            type="monotone"
            dataKey={valueKey}
            name={label}
            stroke={color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }}
          />
        )}
      </Chart>
    </ResponsiveContainer>
  );
}
