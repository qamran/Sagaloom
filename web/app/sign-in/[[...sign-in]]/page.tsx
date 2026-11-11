import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="flex flex-1 items-start justify-center px-4 py-10">
      <SignIn />
    </main>
  );
}
