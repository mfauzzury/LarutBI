const compact = new Intl.NumberFormat("en", { notation: "compact" });

type Axis = Record<string, unknown> & { type?: string; axisLabel?: object };

/** Shorten large numbers on the value axis (39215765 becomes 39M). */
export function withCompactAxis(config: Record<string, unknown>) {
  const format = (axis: Axis) =>
    axis.type === "value"
      ? {
          ...axis,
          axisLabel: {
            ...axis.axisLabel,
            formatter: (value: number) => compact.format(value),
          },
        }
      : axis;
  return {
    ...config,
    xAxis: format(config.xAxis as Axis),
    yAxis: format(config.yAxis as Axis),
  };
}
