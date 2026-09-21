import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Application tracking",
};

export default function AppliedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
