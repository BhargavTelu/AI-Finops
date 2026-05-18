// M1 milestone: MTD/yesterday totals, 30d line chart, by-model bar chart.
// Empty state shown until first integration is connected.
export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p className="mt-2 text-muted-foreground">
        Connect a provider in Settings → Integrations to see your spend.
      </p>
    </div>
  );
}
