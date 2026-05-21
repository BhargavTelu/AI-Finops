import { SettingsTabs } from "./settings-tabs";

// Provides tab navigation between Integrations, Tag Rules, and Slack.
// Each sub-page retains its own page-level heading.
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <SettingsTabs />
      {children}
    </div>
  );
}
