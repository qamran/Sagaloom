import { ReviewDetail } from "@/components/ReviewDetail";

/** One thread's pending proposals. The id is in the route, so a refresh or a shared link resumes it. */
export default async function ReviewThreadPage({ params }: PageProps<"/review/[threadId]">) {
  const { threadId } = await params;
  return <ReviewDetail key={threadId} threadId={threadId} />;
}
