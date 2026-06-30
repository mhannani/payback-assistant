import { Suspense } from "react";
import ProductsPage from "./products-page";

/** The /products route. ProductsPage reads the URL (useSearchParams) for filter state, so it's wrapped
 * in Suspense per Next's requirement. */
export default function Page() {
  return (
    <Suspense>
      <ProductsPage />
    </Suspense>
  );
}
