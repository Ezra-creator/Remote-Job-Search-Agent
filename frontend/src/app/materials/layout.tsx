import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Application materials",
};

export default function MaterialsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
