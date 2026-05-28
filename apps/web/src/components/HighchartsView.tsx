import { useEffect, useRef } from "react";
import Highcharts, { type Options } from "highcharts";

type HighchartsViewProps = {
  options: Options;
};

export function HighchartsView({ options }: HighchartsViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Highcharts.Chart | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    chartRef.current = Highcharts.chart(containerRef.current, options);
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [options]);

  return <div ref={containerRef} className="chart-card" />;
}
