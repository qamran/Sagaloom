import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Next.js 16 calls request interception "Proxy" (this file); not to be confused with the API proxy
// route at app/api/proxy/[...path]/route.ts, which this file also guards.
const isPublic = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)", "/api/proxy/public/(.*)"]);
const isApiProxy = createRouteMatcher(["/api/proxy/(.*)"]);

export default clerkMiddleware(
  async (auth, req) => {
    if (isPublic(req)) return;
    const { userId, redirectToSignIn } = await auth();
    if (userId) return;
    // A fetch from the app gets the 401 lib/api.ts turns into a sign-in redirect; a page goes there now.
    if (isApiProxy(req)) {
      return Response.json({ detail: "sign in required" }, { status: 401 });
    }
    return redirectToSignIn({ returnBackUrl: req.url });
  },
  { signInUrl: "/sign-in", signUpUrl: "/sign-up" },
);

export const config = {
  matcher: [
    // Every page, but not Next internals or static files...
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // ...and always the API routes, so auth() works in the API proxy route.
    "/api/(.*)",
  ],
};
