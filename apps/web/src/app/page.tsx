// Landing page at "/" - M4 milestone.
// Scaffolded as a redirect to /dashboard for now.
// Replace with the full marketing landing page in M4.
import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/dashboard");
}
