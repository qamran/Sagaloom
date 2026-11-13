import type { Metadata } from "next";
import { Dashboard } from "@/components/Dashboard";

export const metadata: Metadata = { title: "Home · Sagaloom" };

/** Where a signed-in author lands: what waits for them, their worlds, credits and canon at a glance. */
export default function HomeDashboardPage() {
  return <Dashboard />;
}
