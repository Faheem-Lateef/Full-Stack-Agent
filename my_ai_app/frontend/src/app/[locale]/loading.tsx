import { getTranslations } from "next-intl/server";

import { Spinner } from "@/components/ui/spinner";

export default async function Loading() {
  const t = await getTranslations("common");

  return (
    <div role="status" className="flex min-h-[50vh] items-center justify-center gap-3 p-8">
      <Spinner aria-hidden="true" className="h-5 w-5 motion-reduce:animate-none" />
      <span>{t("loading")}</span>
    </div>
  );
}
