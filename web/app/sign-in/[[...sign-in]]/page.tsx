import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="flex flex-1 items-start justify-center px-4 py-10">
      {/* Google always shows its account chooser, even with one Google account signed in to the browser. */}
      <SignIn oidcPrompt="select_account" />
    </main>
  );
}
