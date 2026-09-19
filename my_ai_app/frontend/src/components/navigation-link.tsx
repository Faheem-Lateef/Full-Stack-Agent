"use client";

import Link, { useLinkStatus } from "next/link";
import { useTranslations } from "next-intl";
import type { ComponentProps } from "react";

import { Spinner } from "@/components/ui/spinner";

/** Keep native Next navigation, including keyboard shortcuts and prefetching. */
export function NavigationLink({ children, ...props }: ComponentProps<typeof Link>) {
  return (
    <Link {...props}>
      {children}
      <NavigationProgress />
    </Link>
  );
}

function NavigationProgress() {
  const { pending } = useLinkStatus();
  const t = useTranslations("common");

  if (!pending) return null;

  return (
    <span role="status" className="pointer-events-none ml-2 inline-flex items-center">
      <Spinner aria-hidden="true" className="h-4 w-4 motion-reduce:animate-none" />
      <span className="sr-only">{t("loading")}</span>
    </span>
  );
}
