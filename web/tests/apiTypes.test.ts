import { describe, expectTypeOf, it } from "vitest";
import type { components } from "@/lib/api-types.gen";
import type { Entry, Fact, Status, World } from "@/lib/types";

describe("generated API types", () => {
  it("Entry carries the fields the API marks required", () => {
    expectTypeOf<Entry["id"]>().toEqualTypeOf<string>();
    expectTypeOf<Entry["version"]>().toEqualTypeOf<number>();
    expectTypeOf<Entry["facts"]>().toEqualTypeOf<Fact[]>();
  });

  it("Status is the four-way union", () => {
    expectTypeOf<Status>().toEqualTypeOf<"canon" | "myth" | "rumour" | "secret">();
  });
});

describe("types.ts re-exports the generated schemas", () => {
  it("Entry, World and Fact are the generated types", () => {
    expectTypeOf<Entry>().toEqualTypeOf<components["schemas"]["Entry"]>();
    expectTypeOf<World>().toEqualTypeOf<components["schemas"]["World"]>();
    expectTypeOf<Fact>().toEqualTypeOf<components["schemas"]["Fact-Output"]>();
  });
});
