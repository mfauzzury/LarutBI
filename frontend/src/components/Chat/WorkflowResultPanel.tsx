import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileDown } from "lucide-react";
import { useChatStore, type QueryResponseData } from "@/stores/chat";
import { api } from "@/lib/api";
import { withCompactAxis } from "@/lib/reportChart";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ChartPanel from "./ChartPanel";
import PrintableReport from "./PrintableReport";

const MAX_TABLE_ROWS = 50;

interface WorkflowResultPanelProps {
  queryResponse: QueryResponseData;
  retrievedAt: number;
}

export default function WorkflowResultPanel({
  queryResponse,
  retrievedAt,
}: WorkflowResultPanelProps) {
  const [printing, setPrinting] = useState(false);
  const stopPrinting = useCallback(() => setPrinting(false), []);
  const datasourceId = useChatStore((s) => s.datasourceId);
  const { data: datasources } = useQuery<{ id: number; name: string }[]>({
    queryKey: ["datasources", "available"],
    queryFn: async () => (await api.get("/api/v1/datasources/available")).data,
  });
  const workflowResult = queryResponse.workflow_result;

  if (!workflowResult) return null;

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 flex items-center gap-2 bg-gray-50 py-2">
        <span className="text-sm font-medium text-gray-700">
          Workflow: {workflowResult.workflow_name}
        </span>
        <Badge variant="secondary" className="text-[10px]">
          {workflowResult.total_execution_ms}ms
        </Badge>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          onClick={() => setPrinting(true)}
        >
          <FileDown size={14} className="mr-1" />
          Save as PDF
        </Button>
      </div>

      {printing && (
        <PrintableReport
          report={workflowResult}
          datasourceName={datasources?.find((d) => d.id === datasourceId)?.name}
          retrievedAt={retrievedAt}
          maxRows={MAX_TABLE_ROWS}
          onDone={stopPrinting}
        />
      )}

      {workflowResult.step_results.map((step, i) => (
        <Card key={i} className={step.error ? "border-red-200" : ""}>
          <CardHeader className="p-3 pb-0">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              {step.name}
              {step.error && (
                <Badge variant="destructive" className="text-[10px]">
                  Error
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-2">
            {step.chart_config && (
              <div className="mb-3">
                <ChartPanel config={withCompactAxis(step.chart_config)} />
              </div>
            )}
            {step.error ? (
              <p className="text-xs text-red-600">{step.error}</p>
            ) : step.rows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b">
                      {step.columns.map((col) => (
                        <th
                          key={col}
                          className="px-2 py-1 text-left font-medium text-gray-500"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {step.rows.slice(0, MAX_TABLE_ROWS).map((row, ri) => (
                      <tr key={ri} className="border-b last:border-0">
                        {(row as unknown[]).map((cell, ci) => (
                          <td key={ci} className="px-2 py-1 text-gray-700">
                            {String(cell ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {step.rows.length > MAX_TABLE_ROWS && (
                  <p className="mt-1 text-[10px] text-gray-400">
                    Showing {MAX_TABLE_ROWS} of {step.rows.length} rows
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs text-gray-400">No rows returned</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
