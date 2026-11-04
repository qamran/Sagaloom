import { CanonList } from "@/components/CanonList";

export default function CanonLayout({ children }: LayoutProps<"/canon">) {
  return (
    <div className="flex min-h-0 flex-1 flex-col md:flex-row">
      <CanonList />
      <main className="min-w-0 flex-1 px-4 py-6 md:px-11 md:py-[30px]">{children}</main>
    </div>
  );
}
