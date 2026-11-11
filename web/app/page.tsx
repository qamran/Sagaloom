import { auth } from "@clerk/nextjs/server";
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { HomePage } from "@/components/home/HomePage";
import { getPreview } from "@/lib/preview";

export const metadata: Metadata = {
  title: "Sagaloom: a continuity editor for your fictional world",
  description:
    "A continuity editor for your fictional world: you decide, it checks. For authors, fan-fiction writers and solo game masters.",
};

/** `/`: a signed-in author goes to Canon; a signed-out visitor gets the public home page (M5 §5.7). */
export default async function Home() {
  const { userId } = await auth();
  if (userId) redirect("/canon");
  // Fetched here on the web server (the shared secret stays on it); only the data goes to the page.
  return <HomePage preview={await getPreview()} />;
}
