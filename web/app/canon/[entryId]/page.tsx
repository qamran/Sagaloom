import { EntryView } from "@/components/EntryView";

export default async function EntryPage({ params }: PageProps<"/canon/[entryId]">) {
  const { entryId } = await params;
  return <EntryView entryId={entryId} />;
}
