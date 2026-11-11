/**
 * Clerk's sign-in, sign-up and account screens in the app's colours and font (spec §5.6).
 * Clerk derives shades and alpha steps from these colours, so they are the literal values of the tokens
 * in app/globals.css (keep the two in step); the font is the CSS variable next/font sets on <html>.
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: "#6fbfa8", // --accent
    colorPrimaryForeground: "#121514", // --accent-foreground
    colorBackground: "#161a19", // --panel
    colorForeground: "#ece8df", // --foreground
    colorMutedForeground: "#a8ada6", // --muted-foreground
    colorInput: "#1e2422", // --panel-3
    colorInputForeground: "#ece8df", // --foreground
    colorNeutral: "#ece8df", // --foreground: borders and hovers are light-on-dark steps of it
    colorDanger: "#e8785a", // --failed
    fontFamily: "var(--font-inter), system-ui, sans-serif", // --font-sans
    borderRadius: "0.625rem", // --radius
  },
};
