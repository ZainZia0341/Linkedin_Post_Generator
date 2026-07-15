import { Suspense } from "react";
import { GeneratePostView } from "@/components/GeneratePostView";

export default function GeneratePage() {
  return (
    <Suspense fallback={<div className="page-section">Loading generator...</div>}>
      <GeneratePostView />
    </Suspense>
  );
}
