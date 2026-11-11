import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="flex flex-1 items-start justify-center px-4 py-10">
      <SignUp />
    </main>
  );
}
