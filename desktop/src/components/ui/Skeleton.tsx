import { cn } from "@/lib/cn";

interface SkeletonProps {
  width?: string;
  height?: string;
  className?: string;
}

export function Skeleton({ width, height = "16px", className }: SkeletonProps) {
  return (
    <div
      className={cn("animate-pulse", className)}
      style={{
        width: width || "100%",
        height,
        borderRadius: "var(--radius-sm)",
        background: "var(--surface-sunken)",
      }}
    />
  );
}
