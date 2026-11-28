import { useEffect } from "react";
import { createPortal } from "react-dom";
import ReactECharts from "echarts-for-react";
import type { QueryResponseData } from "@/stores/chat";
import { withCompactAxis } from "@/lib/reportChart";

type Report = NonNullable<QueryResponseData["workflow_result"]>;

interface PrintableReportProps {
  report: Report;
  datasourceName?: string;
  retrievedAt: number;
  maxRows: number;
  onDone: () => void;
}

const formatCell = (cell: unknown) =>
  typeof cell === "number" ? cell.toLocaleString("en") : String(cell ?? "");

/**
 * A print-only copy of a report. It is drawn off screen, sent to the browser's
 * print window (where the user can choose "Save as PDF"), then removed.
 */
export default function PrintableReport({
  report,
  datasourceName,
  retrievedAt,
  maxRows,
  onDone,
}: PrintableReportProps) {
  useEffect(() => {
    // The page title becomes the suggested PDF file name
    const previousTitle = document.title;
    const day = new Date(retrievedAt).toLocaleDateString("en-CA");
    document.title = `${report.workflow_name} ${day}`;
    document.body.classList.add("printing-report");
    window.addEventListener("afterprint", onDone);
    // Give the charts a moment to draw
    const timer = window.setTimeout(() => window.print(), 500);

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("afterprint", onDone);
      document.body.classList.remove("printing-report");
      document.title = previousTitle;
    };
  }, [report.workflow_name, retrievedAt, onDone]);

  return createPortal(
    <div className="print-root">
      <header className="mb-4 border-b-2 border-gray-800 pb-2">
        <h1 className="text-xl font-bold">{report.workflow_name}</h1>
        <p className="text-xs text-gray-600">
          {datasourceName && <>Data source: {datasourceName} | </>}
          Data retrieved:{" "}
          {new Date(retrievedAt).toLocaleString("en-GB", {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </p>
      </header>

      {report.step_results.map((step, i) => (
        <section key={i} className="mb-6">
          <div className="print-keep">
            <h2 className="mb-2 text-sm font-bold">{step.name}</h2>
            {step.chart_config && (
              <ReactECharts
                option={{
                  ...withCompactAxis(step.chart_config),
                  animation: false,
                }}
                opts={{ renderer: "svg" }}
                style={{ width: 1000, height: 280 }}
              />
            )}
          </div>

          {step.error ? (
            <p className="text-xs text-red-600">{step.error}</p>
          ) : step.rows.length === 0 ? (
            <p className="text-xs text-gray-500">No rows returned</p>
          ) : (
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-gray-400">
                  {step.columns.map((col) => (
                    <th key={col} className="px-2 py-0.5 text-left font-semibold">
                      {col.replaceAll("_", " ")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {step.rows.slice(0, maxRows).map((row, ri) => (
                  <tr key={ri} className="border-b">
                    {row.map((cell, ci) => (
                      <td key={ci} className="px-2 py-0.5">
                        {formatCell(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {step.rows.length > maxRows && (
            <p className="mt-1 text-[10px] text-gray-500">
              Showing {maxRows} of {step.rows.length} rows
            </p>
          )}
        </section>
      ))}
    </div>,
    document.body
  );
}
