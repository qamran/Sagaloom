import { ChatThread } from "@/components/ChatThread";

/** One chat thread. The id is in the route, so a refresh or a shared link resumes it (R5.5, R18.6).
 * `?prompt=` (a Studio "Try it" link) fills the composer; the author still presses send. */
export default async function ChatThreadPage({ params, searchParams }: PageProps<"/chat/[threadId]">) {
  const { threadId } = await params;
  const { prompt } = await searchParams;
  return <ChatThread key={threadId} threadId={threadId} initialPrompt={typeof prompt === "string" ? prompt : null} />;
}
