import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SignInPage from "@/app/sign-in/[[...sign-in]]/page";
import SignUpPage from "@/app/sign-up/[[...sign-up]]/page";

const props = vi.hoisted(() => ({ signIn: {} as Record<string, unknown>, signUp: {} as Record<string, unknown> }));
vi.mock("@clerk/nextjs", () => ({
  SignIn: (p: Record<string, unknown>) => {
    props.signIn = p;
    return null;
  },
  SignUp: (p: Record<string, unknown>) => {
    props.signUp = p;
    return null;
  },
}));

describe("sign-in and sign-up pages", () => {
  // Without it, Google signs straight in with the one account the browser holds.
  it("ask Google to show its account chooser", () => {
    render(<SignInPage />);
    render(<SignUpPage />);
    expect(props.signIn.oidcPrompt).toBe("select_account");
    expect(props.signUp.oidcPrompt).toBe("select_account");
  });
});
