import { Suspense } from "react";
import { CommentGenerationView } from "@/components/CommentGenerationView";

export default function GenerateCommentPage() {
  return (
    <Suspense fallback={<div className="page-section">Loading comment workspace...</div>}>
      <CommentGenerationView />
    </Suspense>
  );
}
