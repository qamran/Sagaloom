import { ChatThread } from "@/components/ChatThread";

/** One chat thread. The id is in the route, so a refresh or a shared link resumes it (R5.5, R18.6). */
export default async function ChatThreadPage({ params }: PageProps<"/chat/[threadId]">) {
  const { threadId } = await params;
  return <ChatThread key={threadId} threadId={threadId} />;
}
