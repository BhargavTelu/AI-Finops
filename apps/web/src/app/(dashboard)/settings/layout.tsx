import { SettingsSidebar } from "./settings-tabs";
import { PageHeader } from "@/components/page-header";
import { Separator } from "@/components/ui/separator";

// Settings layout: top PageHeader + left sidebar nav + right content panel.
// Individual sub-pages render their own section-level headings inside the
// content panel - no page-level heading needed in sub-pages.
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Manage your integrations, notification channels, and data configuration."
      />

      <Separator />

      <div className="flex gap-8 lg:gap-12">
        <SettingsSidebar />

        {/* Vertical divider - visible only on lg+ */}
        <Separator orientation="vertical" className="hidden h-auto self-stretch lg:block" />

        <div className="min-w-0 flex-1">
          {children}
        </div>
      </div>
    </div>
  );
}
