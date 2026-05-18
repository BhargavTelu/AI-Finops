// M3 milestone: Anomaly log with severity badges.
export default function AnomaliesPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold">Anomalies</h1>
      <p className="mt-2 text-muted-foreground">
        No anomalies detected yet. Stats run nightly after 14 days of data.
      </p>
    </div>
  );
}
