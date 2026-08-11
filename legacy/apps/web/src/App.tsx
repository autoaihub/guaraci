import { useState } from "react";
import { DownloadPage } from "./pages/DownloadPage";
import { OperationHeader } from "./components/OperationHeader";
import { JobHistory } from "./components/JobHistory";
import { LogConsole } from "./components/LogConsole";

export function App() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  return (
    <div className="app">
      <OperationHeader />
      <DownloadPage />
      <JobHistory selectedJobId={selectedJobId} onSelect={setSelectedJobId} />
      <LogConsole jobId={selectedJobId} />
    </div>
  );
}
